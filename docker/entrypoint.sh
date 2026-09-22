#!/usr/bin/env bash
# docker/entrypoint.sh
#
#   1. Sourcea ROS 2 y el workspace de CycloneDDS
#   2. Configura DDS segun GO2_MODE
#   3. Arranca el escritorio virtual segun GO2_GUI
#
# VARIABLES
#   GO2_MODE   sim | real
#   GO2_IFACE  interfaz de red (obligatoria en real)
#   GO2_DOMAIN domain id DDS
#   GO2_GUI    novnc | x11 | none
#   GO2_RES    resolucion, p.ej. 1024x768x16
#
# POR QUE Xvnc Y NO Xvfb + x11vnc
# -------------------------------
# Medido en el portatil de desarrollo:
#   - llvmpipe (render por software) da >1000 FPS con glxgears
#   - el visor se sentia pesado igualmente
# Luego el cuello NO era el renderizado, era la transmision.
#
# x11vnc funciona SONDEANDO el framebuffer: compara la pantalla consigo misma
# muchas veces por segundo para detectar cambios. Con una escena 3D que cambia
# entera en cada fotograma, es el peor caso posible.
#
# Xvnc (TigerVNC) es servidor X y servidor VNC a la vez: dibuja directamente en
# el framebuffer VNC, sin sondeo ni copia intermedia. Un proceso menos y el
# cuello eliminado.
#
# SOBRE LA ACELERACION POR HARDWARE
# ---------------------------------
# No se puede. Ni Xvfb ni Xvnc soportan DRI, asi que aunque se comparta
# /dev/dri, mesa cae a llvmpipe. Comprobado: 1067 FPS "con hardware" frente a
# 1166 FPS con software forzado, y `Accelerated: no` en los dos casos.
#
# La unica via a GL por hardware en Linux es el perfil `dev`, que usa el
# servidor X del anfitrion y por tanto su GPU, sin VNC de por medio.

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

# Ningun servidor X de los que usamos soporta DRI, asi que el renderizado es
# siempre por software dentro del contenedor. Fijarlo explicitamente evita que
# mesa pierda tiempo intentando abrir dispositivos que no puede usar.
export LIBGL_ALWAYS_SOFTWARE=1
export MUJOCO_GL=glfw
export GALLIUM_DRIVER=llvmpipe

# Frecuencia de refresco del visor. MEDIDO: MuJoCo renderiza esta escena a
# unos 188 FPS en este contenedor, asi que el limite lo pone este valor, no el
# renderizado. 50 fps cuestan el 26 % de un nucleo.
#   GO2_VIEWER_FPS=60   maquina holgada
#   GO2_VIEWER_FPS=50   por defecto
#   GO2_VIEWER_FPS=20   maquina justa o experimentos largos
if [[ -n "${GO2_VIEWER_FPS:-}" ]]; then
    _cfg="${GO2_DEPS}/unitree_mujoco/simulate_python/config.py"
    if [[ -w "${_cfg}" ]]; then
        _dt=$(python3 -c "print(f'{1.0/${GO2_VIEWER_FPS}:.4f}')")
        sed -i "s|^VIEWER_DT *=.*|VIEWER_DT = ${_dt}|" "${_cfg}"
        echo "visor a ${GO2_VIEWER_FPS} fps (VIEWER_DT = ${_dt})"
    fi
fi

_esperar_display() {
    for _ in $(seq 1 60); do
        xdpyinfo -display "$1" >/dev/null 2>&1 && return 0
        sleep 0.25
    done
    return 1
}

# ---------------------------------------------------------------------------
# 3. Escritorio virtual
# ---------------------------------------------------------------------------
if [[ "${GO2_GUI}" == "novnc" ]]; then
    export DISPLAY=":99"
    GEOM="${GO2_RES%x*}"          # 1280x800x24 -> 1280x800
    DEPTH="${GO2_RES##*x}"        # 1280x800x24 -> 24

    if xdpyinfo -display :99 >/dev/null 2>&1; then
        echo "display :99 ya en uso; omitiendo Xvnc"
    elif command -v Xvnc >/dev/null 2>&1; then
        Xvnc :99 -geometry "${GEOM}" -depth "${DEPTH}" \
             -SecurityTypes None -AlwaysShared -AcceptKeyEvents \
             -AcceptPointerEvents -AcceptSetDesktopSize \
             -rfbport 5900 -desktop "Go2" >/tmp/xvnc.log 2>&1 &
        MOTOR_GUI="Xvnc (TigerVNC)"
    else
        # Respaldo por si la imagen no trae TigerVNC.
        # -noshm es OBLIGATORIO en contenedor: Docker aisla los segmentos IPC y
        # el ShmAttach de x11vnc falla con BadAccess, matando el proceso en
        # silencio. El navegador solo muestra "Failed to connect to server".
        Xvfb :99 -screen 0 "${GO2_RES}" -nolisten tcp >/tmp/xvfb.log 2>&1 &
        _esperar_display :99 || echo "AVISO: Xvfb no arranco, ver /tmp/xvfb.log"
        x11vnc -display :99 -forever -shared -nopw -quiet \
               -noshm -rfbport 5900 >/tmp/x11vnc.log 2>&1 &
        MOTOR_GUI="Xvfb + x11vnc (respaldo)"
    fi

    if ! _esperar_display :99; then
        echo
        echo "ERROR: el servidor X no ha arrancado. Ultimas lineas del log:"
        tail -15 /tmp/xvnc.log /tmp/xvfb.log 2>/dev/null | sed 's/^/    /'
        echo
    fi

    websockify --web=/usr/share/novnc 6080 localhost:5900 \
               >/tmp/novnc.log 2>&1 &

    echo "escritorio virtual listo (${GEOM}, ${DEPTH} bits) via ${MOTOR_GUI}"
    echo "  navegador   : http://localhost:6080/vnc.html"
    echo "  cliente VNC : localhost:5900   (mas rapido, sin contrasena)"

elif [[ "${GO2_GUI}" == "x11" ]]; then
    # Aqui SI hay aceleracion por hardware: el renderizado lo hace el servidor
    # X del anfitrion, con su GPU, y no hay VNC de por medio. Es la opcion mas
    # rapida en Linux.
    unset LIBGL_ALWAYS_SOFTWARE GALLIUM_DRIVER
    echo "GUI por X11 del anfitrion (DISPLAY=${DISPLAY:-no definido})"
    echo "  usa la GPU del anfitrion y no pasa por VNC: la opcion mas rapida"

else
    # Sin escritorio visible. El simulador necesita un display para crear su
    # ventana, pero nadie la codifica ni la transmite.
    export DISPLAY=":99"
    if [[ "${GO2_NO_XVFB:-0}" == "1" ]]; then
        : # este contenedor no arranca servidor X a proposito
    elif xdpyinfo -display :99 >/dev/null 2>&1; then
        echo "display :99 ya en uso por otro contenedor; se reutiliza"
    elif command -v Xvfb >/dev/null 2>&1; then
        Xvfb :99 -screen 0 640x480x16 -nolisten tcp >/tmp/xvfb.log 2>&1 &
        _esperar_display :99 || true
    fi
fi

# ---------------------------------------------------------------------------
# 4. Resumen
# ---------------------------------------------------------------------------
REND=""
if command -v glxinfo >/dev/null 2>&1 && [[ -n "${DISPLAY:-}" ]] \
   && xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; then
    REND="$(glxinfo -B 2>/dev/null | grep -i 'OpenGL renderer' | sed 's/^ *//')"
fi

cat <<EOF

  Entorno Go2 listo
    modo      : ${GO2_MODE}
    domain    : ${ROS_DOMAIN_ID}
    interfaz  : ${GO2_IFACE}
    GUI       : ${GO2_GUI}
    ${REND:+$REND}
    repo      : ${GO2_ROOT}
    deps      : ${GO2_DEPS}

  Comprobacion rapida:  python3 -m go2core.paths

EOF

if [[ "${GO2_GUI}" == "novnc" ]]; then
    cat <<'EOF'
  El visor renderiza por software: ningun servidor X virtual soporta DRI, asi
  que la GPU no se puede usar desde el contenedor. No afecta a la fisica ni al
  bucle de control, que usan menos del 10 % de su plazo.

  Mas rapido, en Linux, usando la GPU del anfitrion:
      ./go2 dev shell
  Mas rapido para experimentos, sin dibujar nada:
      ./go2 sim headless

EOF
fi

if [[ ! -f "${GO2_ROOT}/usecases/uc01_locomotion/configs/robot_go2.yaml" ]]; then
    echo "  AVISO: no se encuentra el repositorio en ${GO2_ROOT}."
    echo "  Revisa que el volumen este montado en docker-compose.yml."
    echo
fi

exec "$@"
