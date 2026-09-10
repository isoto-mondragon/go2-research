#!/usr/bin/env bash
# env/init_repo.sh
#
# Genera la estructura completa del repositorio go2-research.
# Idempotente: NUNCA sobrescribe un fichero que ya exista, solo crea los que faltan.
# Se puede volver a ejecutar cuando anadas un caso de uso.
#
# Uso:
#   cd ~/go2-research
#   ./env/init_repo.sh
#   ./env/init_repo.sh --add-usecase uc04_mi_caso     # anadir un caso de uso nuevo

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ok()   { printf '\033[1;32m  + %s\033[0m\n' "$*"; }
skip() { printf '\033[0;90m  = %s (ya existe)\033[0m\n' "$*"; }
log()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

# Escribe $1 con el contenido de stdin SOLO si no existe.
write_if_absent() {
    local path="$1"
    mkdir -p "$(dirname "$path")"
    if [[ -e "$path" ]]; then skip "$path"; cat >/dev/null; else cat > "$path"; ok "$path"; fi
}

new_usecase() {
    local uc="$1"
    log "Caso de uso: ${uc}"
    mkdir -p "usecases/${uc}"/{configs,train,deploy,eval,notebooks}
    for d in train deploy eval notebooks; do touch "usecases/${uc}/${d}/.gitkeep"; done

    write_if_absent "usecases/${uc}/README.md" <<EOF
# ${uc}

## Pregunta de investigacion
<Una frase. Si no cabe en una frase, el caso de uso no esta acotado.>

## Hipotesis
<Que esperas medir y por que seria publicable.>

## Estado
- [ ] Entorno de simulacion
- [ ] Politica entrenada
- [ ] Validada en unitree_mujoco
- [ ] Desplegada en robot real
- [ ] Protocolo de evaluacion cerrado
- [ ] Resultados en \`results/\`

## Blockers
<Que te impide avanzar hoy.>

## Estructura
- \`configs/\`   configuracion versionada. NUNCA hardcodear parametros fuera de aqui.
- \`train/\`     entrenamiento (Colab o local)
- \`deploy/\`    inferencia sobre DDS (sim y real, mismo codigo)
- \`eval/\`      protocolo de evaluacion reproducible
- \`notebooks/\` exploracion. Lo que sobreviva se promueve a train/ o eval/
EOF
}

# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--add-usecase" ]]; then
    [[ -n "${2:-}" ]] || { echo "Falta el nombre. Ej: --add-usecase uc04_terreno"; exit 1; }
    new_usecase "$2"
    echo; echo "Listo. Anade el caso de uso a la tabla del README.md principal."
    exit 0
fi

log "Creando estructura de directorios"
mkdir -p \
    env docs tests tools \
    src/go2core/{control,comms,perception,sim,logging} \
    experiments results/{figures,tables} papers ros2_ws/src
ok "directorios"

# ---------------------------------------------------------------------------
log "Ficheros de configuracion de git"

write_if_absent ".gitignore" <<'EOF'
# --- Python ---
__pycache__/
*.py[cod]
.venv/
venv/
*.egg-info/
.ipynb_checkpoints/
.pytest_cache/

# --- Entornos y credenciales ---
.env
*.pem
*.key

# --- ROS2 / colcon ---
ros2_ws/build/
ros2_ws/install/
ros2_ws/log/

# --- Pesos y datos: van por DVC, NUNCA por git ---
*.pt
*.pth
*.onnx
*.ckpt
*.npz
*.bag
*.db3
*.mcap

# --- Salidas de experimentos ---
# Se versiona la METADATA (manifest.json, config.snapshot.yaml, metrics.csv)
# y se ignora todo lo pesado. Los .dvc SI se versionan.
experiments/**/checkpoints/
experiments/**/rosbag/
experiments/**/video/
!experiments/**/*.dvc

# --- Figuras: se regeneran, no se versionan ---
results/figures/*
!results/figures/.gitkeep

# --- LaTeX ---
papers/**/*.aux
papers/**/*.log
papers/**/*.out
papers/**/*.bbl
papers/**/*.blg
papers/**/*.synctex.gz

# --- Sistema ---
.DS_Store
EOF

write_if_absent ".gitattributes" <<'EOF'
* text=auto eol=lf
*.sh   text eol=lf
*.py   text eol=lf
*.ipynb -diff
*.png  binary
*.jpg  binary
*.mp4  binary
EOF

write_if_absent ".dvcignore" <<'EOF'
__pycache__/
.ipynb_checkpoints/
EOF

touch results/figures/.gitkeep results/tables/.gitkeep tests/.gitkeep

# ---------------------------------------------------------------------------
log "Paquete Python go2core"

write_if_absent "pyproject.toml" <<'EOF'
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "go2core"
version = "0.1.0"
description = "Nucleo compartido para investigacion con Unitree Go2 - DANZ, Mondragon Unibertsitatea"
requires-python = ">=3.10"
dependencies = ["numpy", "pyyaml"]

[project.optional-dependencies]
dev = ["pytest", "ruff"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.ruff]
line-length = 110
EOF

for pkg in "" control comms perception sim logging; do
    write_if_absent "src/go2core/${pkg}/__init__.py" <<'EOF'
EOF
done

write_if_absent "src/go2core/logging/run.py" <<'PYEOF'
"""Identidad y metadatos de un experimento.

Regla del proyecto: ningun resultado sale de una carpeta sin manifest.json.
El run_id incluye el sha de git para que la pregunta "con que codigo saliste
esta figura" se responda mirando el nombre del directorio.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return "unknown"


def git_sha(short: bool = True) -> str:
    args = ["rev-parse"] + (["--short"] if short else []) + ["HEAD"]
    return _git(*args)


def git_dirty() -> bool:
    return bool(_git("status", "--porcelain"))


def make_run_id(tag: str) -> str:
    """<ISO-timestamp>_<sha>_<tag>, p.ej. 2026-09-14T1032_a3f9c21_kd05"""
    stamp = datetime.now().strftime("%Y-%m-%dT%H%M")
    return f"{stamp}_{git_sha()}_{tag}"


def create_run(usecase: str, tag: str, config: dict, extra: dict | None = None) -> Path:
    """Crea experiments/<usecase>/<run_id>/ con manifest.json y snapshot de config."""
    run_id = make_run_id(tag)
    run_dir = REPO_ROOT / "experiments" / usecase / run_id
    (run_dir / "checkpoints").mkdir(parents=True, exist_ok=True)

    manifest = {
        "run_id": run_id,
        "usecase": usecase,
        "tag": tag,
        "created": datetime.now().isoformat(timespec="seconds"),
        "git": {"sha": git_sha(short=False), "dirty": git_dirty()},
        "platform": {
            "python": sys.version.split()[0],
            "os": platform.platform(),
            "machine": platform.machine(),
        },
        # Rellenar desde env/HARDWARE.md cuando se ejecute sobre el robot real.
        "robot": {"model": None, "firmware": None, "serial": None, "lidar": None},
        "config": config,
    }
    if extra:
        manifest.update(extra)

    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    if git_dirty():
        print("  [!] AVISO: hay cambios sin commitear. Este run NO es reproducible.")

    print(f"  run creado: {run_dir.relative_to(REPO_ROOT)}")
    return run_dir
PYEOF

write_if_absent "src/go2core/control/contract.py" <<'PYEOF'
"""Carga del contrato sim2real.

Este modulo debe ser el UNICO punto por el que entrenamiento y despliegue
leen kp, kd, action_scale, orden de articulaciones y frecuencia de control.
Si estos valores se duplican en dos sitios, tarde o temprano divergen y el
sim2real falla por una razon que no es el algoritmo.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def load_contract(path: str | Path) -> dict:
    with open(path) as f:
        c = yaml.safe_load(f)

    required = ["joint_order", "default_angles", "kp", "kd", "action_scale", "ctrl_hz"]
    missing = [k for k in required if k not in c]
    if missing:
        raise ValueError(f"El contrato {path} no define: {missing}")

    n = len(c["joint_order"])
    if n != 12:
        raise ValueError(f"joint_order debe tener 12 entradas, tiene {n}")
    if len(c["default_angles"]) != 12:
        raise ValueError("default_angles debe tener 12 entradas")

    return c
PYEOF

# ---------------------------------------------------------------------------
log "Casos de uso"
new_usecase "uc01_locomotion"
new_usecase "uc02_room_exit"
new_usecase "uc03_energy_aware"

write_if_absent "usecases/uc01_locomotion/configs/robot_go2.yaml" <<'EOF'
# CONTRATO SIM2REAL - Unitree Go2
#
# Fichero unico consumido por train/ Y por deploy/. Si cambias algo aqui,
# cambia en los dos lados a la vez. Esa es toda la gracia.
#
# VERIFICAR contra tu notebook Unitree_RL_MJLAB_clean.ipynb antes de fiarse.

# Orden de motores de unitree_go. NO reordenar: es el orden del firmware.
joint_order:
  [FR_hip, FR_thigh, FR_calf,
   FL_hip, FL_thigh, FL_calf,
   RR_hip, RR_thigh, RR_calf,
   RL_hip, RL_thigh, RL_calf]

# Pose nominal de referencia (rad). La accion de la politica es un delta
# sobre estos angulos, escalado por action_scale.
default_angles: [ 0.1, 0.8, -1.5,
                 -0.1, 0.8, -1.5,
                  0.1, 1.0, -1.5,
                 -0.1, 1.0, -1.5]

# Ganancias PD. Deben ser IDENTICAS a las del entorno de entrenamiento.
kp: 25.0
kd: 0.5

action_scale: 0.25
ctrl_hz: 50           # frecuencia de la politica (el LowCmd va a 500 Hz)

# Orden y escalado de las observaciones. Un error aqui es invisible en
# simulacion propia y catastrofico en el robot.
obs:
  order: [ang_vel, gravity_proj, commands, joint_pos_rel, joint_vel, last_action]
  scales:
    ang_vel: 0.25
    joint_pos: 1.0
    joint_vel: 0.05
  clip: 100.0

# Limites de seguridad aplicados en deploy/, no en train/.
safety:
  tau_max: 23.0
  q_delta_max: 0.6      # rad de desviacion maxima respecto a default_angles
  watchdog_ms: 100      # si lowstate deja de llegar, damping
EOF

# ---------------------------------------------------------------------------
log "Documentacion"

write_if_absent "README.md" <<'EOF'
# go2-research

Infraestructura de investigacion sobre Unitree Go2 EDU.
Grupo DANZ, Escuela Politecnica Superior, Mondragon Unibertsitatea.

## Arranque rapido

```bash
./env/bootstrap_host.sh            # host Ubuntu 26.04
distrobox enter go2-humble
./env/bootstrap_container.sh       # ROS2 Humble + CycloneDDS 0.10.2 + SDK2
```

Simulacion: `source ~/unitree_ros2/setup_sim.sh` (domain 1, interfaz `lo`)
Robot real: `source ~/unitree_ros2/setup_real.sh <IFACE>` (domain 0)

## Casos de uso

| id | tema | estado |
|----|------|--------|
| uc01_locomotion  | locomocion RL y sim2real con recursos de consumo | en curso |
| uc02_room_exit   | navegacion de salida de sala con percepcion minima | planificado |
| uc03_energy_aware| coste de transporte y seleccion de marcha | planificado |

## Reglas del repositorio

1. Ningun parametro de control se hardcodea. Todo vive en `usecases/*/configs/`.
2. Un experimento sin `manifest.json` no existe.
3. Las figuras se generan con `results/make_figures.py`. Nunca se editan a mano.
4. Los pesos y los rosbags van por DVC, nunca por git.
5. Antes de tocar el robot fisico se lee `docs/SAFETY.md`. Sin excepciones.

## Repositorios relacionados

- `go2-perception-stack` (publico): superficie de publicacion, con tags por paper.
- `go2-robotics-workspace-archive` (privado, archivado): backup historico previo.
EOF

write_if_absent "env/HARDWARE.md" <<'EOF'
# Inventario de hardware

Rellenar el dia que llegue el robot. Estos campos van en el manifest.json
de cada experimento y en la seccion de materiales de los papers.

| campo | valor |
|---|---|
| Modelo | Unitree Go2 EDU (¿base o Plus?) |
| Numero de serie | |
| Version de firmware (app: Device > About) | |
| Ordenador embarcado | Jetson Orin Nano (EDU) / Orin NX (EDU Plus) |
| LiDAR | 4D LiDAR L1 (integrado) / Livox Mid-360 / Hesai XT16 |
| Camaras | ojo de pez frontal / + RealSense |
| Brazo D1 | no / si |
| Bateria | 8000 mAh / 15000 mAh |
| Fecha de recepcion | |

## Portatil de desarrollo
HP ProBook 450 G10, i5-1335U, 16 GB RAM, Intel Iris Xe (sin GPU dedicada).
Ubuntu 26.04.1 LTS + contenedor distrobox Ubuntu 22.04 / ROS 2 Humble.

## Interfaz de red usada con el robot
| campo | valor |
|---|---|
| Nombre de la interfaz | |
| Integrada o adaptador USB | |
| IP del host | 192.168.123.222/24 |
| IP del robot | 192.168.123.161 |
EOF

write_if_absent "docs/SAFETY.md" <<'EOF'
# Protocolo de seguridad - Unitree Go2

Obligatorio para cualquier persona del grupo que opere el robot, incluidos
estudiantes de TFG/TFM. No es burocracia: en un grupo de investigacion este
documento vale tanto como el codigo.

## Antes de encender
- [ ] Radio de 2 m libre. Nada fragil, nadie detras del robot.
- [ ] Bateria > 50 %. Por debajo del 30 % el comportamiento de los motores
      cambia y contamina cualquier medida.
- [ ] Mando fisico encendido y EN LA MANO. Es la unica parada de emergencia real.
- [ ] App movil Unitree cerrada y desconectada.

## Antes de enviar cualquier LowCmd
- [ ] Robot tumbado y en modo damping (L2+B).
- [ ] Estado del servicio sport_mode comprobado con MotionSwitcher.CheckMode().
- [ ] Si esta activo: ReleaseMode() y volver a comprobar que queda vacio.
      Publicar LowCmd con sport_mode activo hace que dos controladores peleen
      por los mismos motores. El robot puede dar una patada.

## Secuencia de primer contacto (una sola vez por robot)
1. `env/go2_net.sh probe`
2. `tools/dds_smoketest.py --mode real --iface <IFACE>`   (solo lectura)
3. Comprobacion de sport_mode
4. LowCmd nulo (kp=kd=tau=0): debe aceptarse y el robot NO debe moverse
5. `tools/check_write_path.py --real-robot-i-have-read-safety` con el robot
   suspendido o tumbado de lado
6. Solo entonces: politica de locomocion, con el robot en el suelo

## Si algo va mal
- L2+B en el mando: damping inmediato.
- Cortar el proceso emisor NO detiene al robot por si solo.
- Registrar el incidente en este documento con fecha y causa.

## Registro de incidentes
| fecha | que paso | causa | mitigacion |
|---|---|---|---|
EOF

write_if_absent "results/make_figures.py" <<'PYEOF'
#!/usr/bin/env python3
"""Genera TODAS las figuras del proyecto a partir de experiments/.

Regla: si una figura no se puede regenerar con un comando, no entra en el paper.

Uso:
    python3 results/make_figures.py --usecase uc01_locomotion
"""

import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = REPO_ROOT / "experiments"
FIGURES = REPO_ROOT / "results" / "figures"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--usecase", default=None, help="limitar a un caso de uso")
    args = p.parse_args()

    FIGURES.mkdir(parents=True, exist_ok=True)
    roots = [EXPERIMENTS / args.usecase] if args.usecase else sorted(EXPERIMENTS.glob("uc*"))

    for root in roots:
        if not root.is_dir():
            continue
        runs = sorted(d for d in root.iterdir() if (d / "manifest.json").exists())
        print(f"{root.name}: {len(runs)} runs con manifest")
        # TODO: cargar metrics.csv de cada run y generar las figuras del caso de uso.


if __name__ == "__main__":
    main()
PYEOF

write_if_absent "CITATION.cff" <<'EOF'
cff-version: 1.2.0
title: "go2-research: infraestructura reproducible para investigacion con Unitree Go2"
message: "Si usas este software, citalo asi."
authors:
  - family-names: "Soto Alsua"
    given-names: "Ibon"
    affiliation: "Mondragon Unibertsitatea, Escuela Politecnica Superior (DANZ)"
license: MIT
EOF

log "Estructura creada"
echo
find . -path ./.git -prune -o -type d -print | grep -v '__pycache__' | sort | sed 's|^\./||' | head -40
echo
cat <<'EOF'
Siguiente:
  git init && git add . && git commit -m "chore: estructura inicial del proyecto"
  pip install -e .          (dentro del venv, para que go2core sea importable)
EOF
