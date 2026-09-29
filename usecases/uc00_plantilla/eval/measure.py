#!/usr/bin/env python3
"""usecases/uc00_plantilla/eval/measure.py

Mide un experimento ya registrado y anota el resultado en su manifest.json.

    deploy/main.py --log   ->  experiments/<uc>/<run_id>/{manifest.json, metrics.csv}
    eval/measure.py        ->  lee metrics.csv y escribe "resultados" en el manifest

Separar medir de ejecutar permite recalcular las metricas sin volver a mover
el robot, y que el resultado quede pegado al manifest con el sha de git del
codigo que lo produjo.

REGLA DEL PROYECTO: sin manifest.json con sha de git, el experimento no es
trazable y este script se niega a medirlo.

Uso:
    python3 usecases/uc00_plantilla/eval/measure.py                  # el ultimo
    python3 usecases/uc00_plantilla/eval/measure.py --run experiments/<uc>/<run_id>
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from go2core import paths  # noqa: E402

UC = Path(__file__).resolve().parents[1]
USECASE = UC.name


def ultimo_run() -> Path:
    # Los nombres empiezan por timestamp ISO, asi que el orden alfabetico es
    # el cronologico.
    runs = sorted(d for d in (paths.EXPERIMENTS / USECASE).glob("*")
                  if (d / "manifest.json").exists())
    if not runs:
        raise SystemExit(f"No hay experimentos en experiments/{USECASE}/. "
                         f"Ejecuta antes deploy/main.py con --log.")
    return runs[-1]


def cargar(run: Path) -> tuple[dict, dict[str, np.ndarray]]:
    manifest_path = run / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"{run} no tiene manifest.json: no es trazable.")
    manifest = json.loads(manifest_path.read_text())
    sha = (manifest.get("git") or {}).get("sha")
    if not sha or sha == "unknown":
        raise SystemExit("El manifest no tiene sha de git: no es trazable.")

    with open(run / "metrics.csv") as fh:
        filas = list(csv.DictReader(fh))
    if not filas:
        raise SystemExit("metrics.csv esta vacio: el experimento no llego a "
                         "ejecutar ningun paso.")
    cols = {k: np.asarray([float(f[k]) for f in filas]) for k in filas[0]}
    return manifest, cols


def medir(cols: dict[str, np.ndarray]) -> dict:
    """TODO: sustituye o amplia estas metricas por las de tu caso de uso."""
    t = cols["t"]
    v = np.hypot(cols["vx"], cols["vy"])
    return {
        "pasos": int(len(t)),
        "duracion_s": round(float(t[-1] - t[0]), 2),
        "vel_lineal_media_ms": round(float(v.mean()), 3),
        "vel_lineal_max_ms": round(float(v.max()), 3),
        "wz_max_rads": round(float(np.abs(cols["wz"]).max()), 3),
        "inclinacion_max_deg": round(float(np.degrees(cols["inclinacion_rad"].max())), 1),
        # En simulacion la bateria y la temperatura son 0: no es un fallo.
        "bateria_final_pct": float(cols["bateria_pct"][-1]),
        "temp_max_c": float(cols["temp_max_c"].max()),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", default=None, help="carpeta del experimento (por defecto, el ultimo)")
    args = p.parse_args()

    run = Path(args.run).resolve() if args.run else ultimo_run()
    manifest, cols = cargar(run)
    resultados = medir(cols)

    manifest["resultados"] = resultados
    (run / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False))

    print(f"experimento: {run.name}")
    print(f"git sha    : {manifest['git']['sha'][:7]}"
          f"{'  (con cambios sin commitear: no reproducible)' if manifest['git'].get('dirty') else ''}")
    for k, v in resultados.items():
        print(f"  {k:<22} {v}")
    print(f"\nanotado en {run / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
