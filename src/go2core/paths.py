"""Rutas y configuracion de entorno del proyecto.

UNICO sitio del codigo donde se decide donde esta cada cosa. Antes de este
modulo el proyecto tenia rutas atadas a una maquina concreta
(`/home/ibon/go2-research`, `~/opt/unitree_mujoco`, `~/venvs/go2`) y el nombre
de la interfaz Ethernet escrito en el contrato. Nada de eso funciona en el
ordenador de otra persona ni dentro de un contenedor.

VARIABLES DE ENTORNO
--------------------
    GO2_ROOT    raiz del repositorio. Si no esta, se deduce de __file__.
    GO2_DEPS    donde viven unitree_ros2, unitree_sdk2 y unitree_mujoco.
                En la imagen Docker: /opt/go2. En instalacion manual: ~/opt.
    GO2_MODE    "sim" o "real". Selecciona el bloque `dds` del contrato.
    GO2_IFACE   interfaz de red. Anula la del contrato.
                En sim siempre "lo"; en real, la Ethernet del robot.
    GO2_DOMAIN  domain id DDS. Anula el del contrato.
    GO2_GUI     "novnc", "x11" o "none". Lo usa el entrypoint del contenedor.

Ninguna es obligatoria: sin ellas el modulo deduce valores razonables y el
proyecto sigue funcionando como hasta ahora.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Raiz del repositorio
# ---------------------------------------------------------------------------
# Este fichero esta en <raiz>/src/go2core/paths.py, luego la raiz son tres
# niveles arriba. Se calcula asi para que el repo pueda montarse en cualquier
# ruta: /workspace en el contenedor, ~/go2-research en el portatil.
_DEDUCIDA = Path(__file__).resolve().parents[2]

ROOT = Path(os.environ.get("GO2_ROOT", _DEDUCIDA)).resolve()


def _deps_por_defecto() -> Path:
    """Donde estan las dependencias externas de Unitree."""
    for cand in (Path("/opt/go2"), Path.home() / "opt", Path.home()):
        if (cand / "unitree_mujoco").exists() or (cand / "unitree_ros2").exists():
            return cand
    return Path("/opt/go2")


DEPS = Path(os.environ.get("GO2_DEPS", _deps_por_defecto())).resolve()

# --- dependencias externas ---
UNITREE_ROS2 = DEPS / "unitree_ros2"
UNITREE_SDK2 = DEPS / "unitree_sdk2"
UNITREE_MUJOCO = DEPS / "unitree_mujoco"
SIM_DIR = UNITREE_MUJOCO / "simulate_python"
SIM_CONFIG = SIM_DIR / "config.py"
GO2_ROBOT_DIR = UNITREE_MUJOCO / "unitree_robots" / "go2"

# --- dentro del repositorio ---
SRC = ROOT / "src"
TOOLS = ROOT / "tools"
DOCKER = ROOT / "docker"
EXPERIMENTS = ROOT / "experiments"
RESULTS = ROOT / "results"
USECASES = ROOT / "usecases"
UC01 = USECASES / "uc01_locomotion"
CONTRACT = UC01 / "configs" / "robot_go2.yaml"
SCENE_FLAT = UC01 / "configs" / "scene_flat.xml"


# ---------------------------------------------------------------------------
# Entorno de ejecucion
# ---------------------------------------------------------------------------
def mode() -> str:
    """"sim" o "real"."""
    m = os.environ.get("GO2_MODE", "sim").strip().lower()
    return m if m in ("sim", "real") else "sim"


def iface(default: str | None = None) -> str | None:
    """Interfaz de red. GO2_IFACE manda sobre el contrato."""
    return os.environ.get("GO2_IFACE") or default


def domain(default: int | None = None) -> int | None:
    """Domain id DDS. GO2_DOMAIN manda sobre el contrato."""
    v = os.environ.get("GO2_DOMAIN")
    if v is None:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def in_container() -> bool:
    return Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()


# ---------------------------------------------------------------------------
# Diagnostico
# ---------------------------------------------------------------------------
def check() -> list[str]:
    """Devuelve la lista de problemas encontrados. Vacia si todo esta bien."""
    problemas = []
    if not CONTRACT.exists():
        problemas.append(f"no existe el contrato: {CONTRACT}")
    if not UNITREE_MUJOCO.exists():
        problemas.append(f"no existe unitree_mujoco en {UNITREE_MUJOCO} "
                         "(ajusta GO2_DEPS)")
    if not UNITREE_ROS2.exists():
        problemas.append(f"no existe unitree_ros2 en {UNITREE_ROS2} "
                         "(ajusta GO2_DEPS)")
    try:
        import unitree_sdk2py  # noqa: F401
    except ImportError:
        problemas.append("no se puede importar unitree_sdk2py")
    return problemas


def describe() -> str:
    lines = [
        "Rutas del proyecto",
        f"  GO2_ROOT   {ROOT}" + ("" if "GO2_ROOT" in os.environ else "   (deducida)"),
        f"  GO2_DEPS   {DEPS}" + ("" if "GO2_DEPS" in os.environ else "   (deducida)"),
        f"  contrato   {CONTRACT}",
        f"  simulador  {SIM_DIR}",
        "",
        "Entorno",
        f"  modo       {mode()}",
        f"  interfaz   {iface() or '(del contrato)'}",
        f"  domain     {domain() if domain() is not None else '(del contrato)'}",
        f"  contenedor {'si' if in_container() else 'no'}",
    ]
    p = check()
    lines.append("")
    if p:
        lines.append(f"PROBLEMAS ({len(p)}):")
        lines += [f"  - {x}" for x in p]
    else:
        lines.append("Todo correcto.")
    return "\n".join(lines)


if __name__ == "__main__":
    print(describe())
