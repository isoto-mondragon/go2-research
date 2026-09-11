#!/usr/bin/env python3
"""tools/import_run.py

Importa una politica entrenada en Colab al repositorio como experimento
trazable, y verifica que es desplegable ANTES de darla por buena.

Un entrenamiento que no pasa por aqui no es un experimento: es un fichero.

Que hace:
  1. Comprueba que la carpeta de origen trae policy.onnx y deploy_params.yaml
  2. Verifica que la dimension de entrada del ONNX cuadra con las
     observaciones declaradas en deploy_params.yaml
  3. Crea experiments/<usecase>/<run_id>/ con run_id = fecha_sha_etiqueta
  4. Escribe manifest.json con procedencia, presupuesto de computo y semilla
  5. Copia el contrato vigente como config.snapshot.yaml
  6. Deja los pesos listos para `dvc add`

Uso:
    python3 tools/import_run.py ~/Downloads/colab_run_t4_2h_seed1 \\
        --tag t4_2h_seed1 --budget-min 120 --seed 1

    # despues, lo que imprime al final:
    dvc add experiments/uc01_locomotion/<run_id>/checkpoints
    git add ... && git commit && dvc push
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))


def git(*a: str) -> str:
    try:
        return subprocess.check_output(["git", *a], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return "unknown"


def expected_obs_dim(params: dict) -> int | None:
    """Suma las dimensiones declaradas en el bloque observations de mjlab."""
    obs = params.get("observations")
    if not isinstance(obs, dict):
        return None
    total = 0
    for _, spec in obs.items():
        scale = spec.get("scale")
        n = len(scale) if isinstance(scale, list) else 1
        total += n * int(spec.get("history_length", 1) or 1)
    return total


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("source", help="carpeta con policy.onnx y deploy_params.yaml")
    p.add_argument("--usecase", default="uc01_locomotion")
    p.add_argument("--tag", required=True, help="etiqueta corta, ej. t4_2h_seed1")
    p.add_argument("--budget-min", type=float, default=None,
                   help="minutos de GPU del entrenamiento")
    p.add_argument("--gpu", default="colab-t4-free")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--steps", type=int, default=None, help="pasos de entrenamiento")
    p.add_argument("--notes", default="")
    args = p.parse_args()

    src = Path(args.source).expanduser()
    onnx = src / "policy.onnx"
    params_f = src / "deploy_params.yaml"

    for f in (onnx, params_f):
        if not f.exists():
            print(f"FALTA: {f}")
            print("\nUn run importable necesita los dos ficheros. Si el notebook de")
            print("Colab no exporta deploy_params.yaml, el run NO es desplegable:")
            print("sin el no se sabe el orden de articulaciones ni el action_scale.")
            return 2

    params = yaml.safe_load(params_f.read_text())

    # --- verificacion: el ONNX y los params tienen que cuadrar ---
    try:
        import onnxruntime as ort
        sess = ort.InferenceSession(str(onnx), providers=["CPUExecutionProvider"])
        in_shape = sess.get_inputs()[0].shape
        out_shape = sess.get_outputs()[0].shape
        obs_dim = int(in_shape[-1])
        act_dim = int(out_shape[-1])
    except Exception as e:
        print(f"No se puede abrir el ONNX: {e}")
        return 2

    declared = expected_obs_dim(params)
    print(f"ONNX      : obs[{obs_dim}] -> actions[{act_dim}]")
    print(f"params    : observations suman {declared}")
    if act_dim != 12:
        print(f"AVISO: la salida tiene {act_dim} dims, se esperaban 12")
    if declared is not None and declared != obs_dim:
        print(f"\nINCOHERENTE: el ONNX espera {obs_dim} y deploy_params declara {declared}.")
        print("No se importa. Revisa el export del notebook.")
        return 3
    print("coherencia ONNX <-> deploy_params: OK\n")

    # --- crear el run ---
    sha = git("rev-parse", "--short", "HEAD")
    run_id = f"{datetime.now().strftime('%Y-%m-%dT%H%M')}_{sha}_{args.tag}"
    run_dir = REPO_ROOT / "experiments" / args.usecase / run_id
    (run_dir / "checkpoints").mkdir(parents=True, exist_ok=True)

    shutil.copy2(onnx, run_dir / "checkpoints" / "policy.onnx")
    shutil.copy2(params_f, run_dir / "deploy_params.yaml")
    for extra in ("metrics.csv", "train_log.csv", "reward_curve.png", "config.yaml"):
        if (src / extra).exists():
            shutil.copy2(src / extra, run_dir / extra)

    contract = REPO_ROOT / "usecases" / args.usecase / "configs" / "robot_go2.yaml"
    if contract.exists():
        shutil.copy2(contract, run_dir / "config.snapshot.yaml")

    manifest = {
        "run_id": run_id,
        "usecase": args.usecase,
        "tag": args.tag,
        "created": datetime.now().isoformat(timespec="seconds"),
        "git": {"sha": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))},
        "training": {
            "platform": args.gpu,
            "budget_minutes": args.budget_min,
            "seed": args.seed,
            "steps": args.steps,
            "framework": "unitree_rl_mjlab + mujoco_playground",
        },
        "policy": {"format": "onnx", "obs_dim": obs_dim, "action_dim": act_dim},
        "evaluation": {
            "sim": {"done": False, "notes": ""},
            "real": {"done": False, "notes": ""},
        },
        "notes": args.notes,
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    rel = run_dir.relative_to(REPO_ROOT)
    print(f"run creado: {rel}")
    if manifest["git"]["dirty"]:
        print("AVISO: hay cambios sin commitear. Este run no es reproducible tal cual.")
    print("\nSiguiente:")
    print(f"  dvc add {rel}/checkpoints")
    print(f"  git add {rel} && git commit -m 'exp: importar {args.tag}'")
    print("  dvc push")
    print("\nPara evaluarlo:")
    print(f"  python3 usecases/{args.usecase}/deploy/run_policy.py --mode sim \\")
    print(f"      --policy {rel}/checkpoints/policy.onnx --auto --duration 60 \\")
    print(f"      --log {rel}/metrics_sim.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
