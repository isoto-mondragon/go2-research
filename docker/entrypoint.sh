#!/usr/bin/env bash
# docker/entrypoint.sh
#
# Se ejecuta al arrancar el contenedor:
#   1. Sourcea ROS 2 y el workspace de CycloneDDS
#   2. Configura DDS segun GO2_MODE (sim -> domain 1 por lo;
#      real -> domain 0 por la interfaz Ethernet)
#   3. Arranca el escritorio virtual segun GO2_GUI
#
# VARIABLES
#   GO2_MODE   sim | real
#   GO2_IFACE  interfaz de red (obligatoria en real)
#   GO2_DOMAIN domain id DDS
#   GO2_GUI    novnc | x11 | none
#   GO2_RES    resolucion del escritorio, p.ej. 1024x768x16
#
# SOBRE EL RENDIMIENTO
#   El visor dibuja por software (llvmpipe) porque no hay GPU garantizada en la
#   maquina anfitriona. Eso cuesta CPU, y transmitirlo por VNC cuesta mas.
#   Tres palancas, de mayor a menor efecto:
#     - GO2_GUI=none      para experimentos: no se codifica nada
#     - cliente VNC nativo en el puerto 5900, mas rapido que el navegador
#     - GO2_RES mas baja   menos pixeles que codificar
#   La fisica y el bucle de control NO se ven afectados: van en hilos aparte.

set -euo pipefail

GO2_MODE="${GO2_MODE:-sim}"
GO2_GUI="${GO2_GUI:-none}"
GO2_RES="${GO2_RES:-1280x800x24}"
GO2_DEPS="${GO2_DEPS:-/opt/go2}"
GO2_ROOT="${GO2_ROOT:-/workspace}"

# ---------------------------------------------------------------------------
# 1. ROS 2 y CycloneDDS
# ---------------------------------------------------------------------------
set +u
source /opt/ros/humble/setup.bash
source "${GO2_DEPS}/unitree_ros2/cyclonedds_ws/install/setup.bash"
set -u

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export PYTHONPATH="${GO2_ROOT}/src:${PYTHONPATH:-}"

# ---------------------------------------------------------------------------
# 2. DDS segun el modo
# ---------------------------------------------------------------------------
if [[ "${GO2_MODE}" == "real" ]]; then
    GO2_IFACE="${GO2_IFACE:-}"
    if [[ -z "${GO2_IFACE}" ]]; then
        echo "ERROR: GO2_MODE=real requiere GO2_IFACE con el nombre de la"
        echo "       interfaz Ethernet conectada al robot."
        echo
        echo "Interfaces disponibles en este contenedor:"
        ip -br link | awk '$1 != "lo" {print "  " $1 "  " $2}'
        echo
        echo "Si solo ves 'lo' y interfaces virtuales, el contenedor NO esta"
        echo "usando la red del anfitrion. El robot real necesita"
        echo "network_mode: host, que solo funciona de verdad en Linux."
        exit 1
    fi
    export ROS_DOMAIN_ID="${GO2_DOMAIN:-0}"
else
    GO2_IFACE="${GO2_IFACE:-lo}"
    export ROS_DOMAIN_ID="${GO2_DOMAIN:-1}"
fi
export GO2_IFACE GO2_MODE GO2_DEPS GO2_ROOT

export CYCLONEDDS_URI="<CycloneDDS><Domain><General><Interfaces><NetworkInterface name=\"${GO2_IFACE}\" priority=\"default\" multicast=\"default\" /></Interfaces></General></Domain></CycloneDDS>"

# ---------------------------------------------------------------------------
# 3. Escritorio virtual
# ---------------------------------------------------------------------------
if [[ "${GO2_GUI}" == "novnc" ]]; then
    export DISPLAY=":99"
    export LIBGL_ALWAYS_SOFTWARE=1
    export MUJOCO_GL=glfw

    Xvfb :99 -screen 0 "${GO2_RES}" -nolisten tcp >/tmp/xvfb.log 2>&1 &
    for _ in $(seq 1 40); do
        xdpyinfo -display :99 >/dev/null 2>&1 && break
        sleep 0.25
    done

    # -ncache_cr mejora notablemente el desplazamiento de ventanas sobre VNC.
    x11vnc -display :99 -forever -shared -nopw -quiet \
           -ncache 10 -ncache_cr \
           -rfbport 5900 >/tmp/x11vnc.log 2>&1 &
    websockify --web=/usr/share/novnc 6080 localhost:5900 \
           >/tmp/novnc.log 2>&1 &

    echo "escritorio virtual listo (${GO2_RES})"
    echo "  navegador     : http://localhost:6080/vnc.html"
    echo "  cliente VNC   : localhost:5900   (mas rapido, sin contrasena)"

elif [[ "${GO2_GUI}" == "x11" ]]; then
    export LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-0}"
    echo "GUI por X11 del anfitrion (DISPLAY=${DISPLAY:-no definido})"

else
    # Sin escritorio. El simulador necesita un display igualmente para crear su
    # ventana, pero nadie la codifica ni la transmite: es lo mas rapido para
    # experimentos largos.
    export DISPLAY=":99"
    export LIBGL_ALWAYS_SOFTWARE=1
    export MUJOCO_GL=glfw
    if command -v Xvfb >/dev/null 2>&1; then
        Xvfb :99 -screen 0 640x480x16 -nolisten tcp >/tmp/xvfb.log 2>&1 &
        for _ in $(seq 1 40); do
            xdpyinfo -display :99 >/dev/null 2>&1 && break
            sleep 0.25
        done
    fi
fi

# ---------------------------------------------------------------------------
# 4. Resumen
# ---------------------------------------------------------------------------
cat <<EOF

  Entorno Go2 listo
    modo      : ${GO2_MODE}
    domain    : ${ROS_DOMAIN_ID}
    interfaz  : ${GO2_IFACE}
    GUI       : ${GO2_GUI}
    repo      : ${GO2_ROOT}
    deps      : ${GO2_DEPS}

  Comprobacion rapida:
    python3 -m go2core.paths

EOF

if [[ ! -f "${GO2_ROOT}/usecases/uc01_locomotion/configs/robot_go2.yaml" ]]; then
    echo "  AVISO: no se encuentra el repositorio en ${GO2_ROOT}."
    echo "  Revisa que el volumen este montado en docker-compose.yml."
    echo
fi

exec "$@"
