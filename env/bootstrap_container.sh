#!/usr/bin/env bash
# env/bootstrap_container.sh
#
# Instala DENTRO del contenedor distrobox 'go2-humble' (Ubuntu 22.04):
#   - ROS 2 Humble
#   - CycloneDDS 0.10.2 + rmw_cyclonedds (version que usa el robot Unitree)
#   - unitree_ros2 (mensajes unitree_go / unitree_api)
#   - unitree_sdk2 (C++) y unitree_sdk2_python
#   - unitree_mujoco (simulador que habla el MISMO DDS que el robot real)
#   - venv con torch CPU, mujoco, ultralytics
#
# NO requiere el robot fisico. Al terminar puedes ensayar el 100% del
# checklist de comunicacion contra unitree_mujoco.
#
# Uso (desde dentro del contenedor):
#   distrobox enter go2-humble
#   ~/go2-research/env/bootstrap_container.sh

set -euo pipefail

ROS_DISTRO="humble"
SRC_DIR="${HOME}/opt"
VENV_DIR="${HOME}/venvs/go2"
NPROC=$(( $(nproc) > 4 ? 4 : $(nproc) ))   # i5-1335U + 16GB: no pasarse con -j

log()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m[ok] %s\033[0m\n' "$*"; }

# ---------------------------------------------------------------------------
# 0. Comprobaciones
# ---------------------------------------------------------------------------
log "Comprobaciones previas"

if [[ ! -f /run/.containerenv && ! -f /.dockerenv ]]; then
    echo "ERROR: esto debe ejecutarse DENTRO del contenedor distrobox." >&2
    echo "Haz primero: distrobox enter go2-humble" >&2
    exit 1
fi

. /etc/os-release
[[ "${VERSION_ID}" == "22.04" ]] || warn "Se esperaba Ubuntu 22.04, detectado ${VERSION_ID}"

# GOTCHA nº1 de todo el proceso: si ROS2 esta sourceado, la compilacion de
# cyclonedds falla de forma confusa. Abortamos pronto y claro.
if [[ -n "${AMENT_PREFIX_PATH:-}" || -n "${ROS_DISTRO_SOURCED:-}" ]]; then
    echo "ERROR: hay un entorno ROS2 sourceado en esta shell." >&2
    echo "Abre una shell limpia (sin source de setup.bash en .bashrc) y reintenta." >&2
    exit 1
fi

mkdir -p "${SRC_DIR}"

# ---------------------------------------------------------------------------
# 1. Base + locale
# ---------------------------------------------------------------------------
log "Base del sistema y locale"
sudo apt-get update
sudo apt-get install -y locales curl gnupg lsb-release software-properties-common \
    git build-essential cmake python3-pip python3-venv \
    libyaml-cpp-dev libglfw3-dev libxinerama-dev libxcursor-dev libxi-dev
sudo locale-gen en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
sudo add-apt-repository -y universe

# ---------------------------------------------------------------------------
# 2. ROS 2 Humble
# ---------------------------------------------------------------------------
log "Instalando ROS 2 ${ROS_DISTRO}"

if [[ ! -d "/opt/ros/${ROS_DISTRO}" ]]; then
    # Metodo actual: paquete ros2-apt-source. El metodo antiguo (apt-key +
    # linea deb manual) esta deprecado.
    ROS_APT_SOURCE_VERSION=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest \
        | grep -F '"tag_name"' | awk -F\" '{print $4}')
    echo "ros-apt-source version: ${ROS_APT_SOURCE_VERSION}"
    curl -fsSL -o /var/tmp/ros2-apt-source.deb \
        "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.$(. /etc/os-release && echo "$VERSION_CODENAME")_all.deb"
    sudo apt-get install -y /var/tmp/ros2-apt-source.deb
    sudo apt-get update
fi

sudo apt-get install -y \
    "ros-${ROS_DISTRO}-desktop" \
    ros-dev-tools \
    "ros-${ROS_DISTRO}-rmw-cyclonedds-cpp" \
    "ros-${ROS_DISTRO}-rosidl-generator-dds-idl" \
    python3-colcon-common-extensions

ok "ROS 2 ${ROS_DISTRO} instalado"

# ---------------------------------------------------------------------------
# 3. unitree_ros2 + CycloneDDS 0.10.2
# ---------------------------------------------------------------------------
# El robot Unitree usa CycloneDDS 0.10.2. Hay que compilar rmw_cyclonedds
# contra esa version concreta, no contra la de apt.
log "unitree_ros2 + CycloneDDS 0.10.2"

if [[ ! -d "${HOME}/unitree_ros2" ]]; then
    git clone https://github.com/unitreerobotics/unitree_ros2 "${HOME}/unitree_ros2"
fi

cd "${HOME}/unitree_ros2/cyclonedds_ws/src"
[[ -d rmw_cyclonedds ]] || git clone https://github.com/ros2/rmw_cyclonedds -b "${ROS_DISTRO}"
[[ -d cyclonedds   ]]   || git clone https://github.com/eclipse-cyclonedds/cyclonedds -b releases/0.10.x

cd "${HOME}/unitree_ros2/cyclonedds_ws"

# PASO 1: cyclonedds SIN ROS2 sourceado (ya validado arriba)
log "Compilando cyclonedds (sin ROS2 en el entorno)"
colcon build --packages-select cyclonedds --cmake-args -DCMAKE_BUILD_TYPE=Release

# PASO 2: el resto, YA con ROS2 sourceado
log "Compilando rmw_cyclonedds y mensajes unitree"
set +u; source "/opt/ros/${ROS_DISTRO}/setup.bash"; set -u
colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release

ok "unitree_ros2 compilado"

# ---------------------------------------------------------------------------
# 4. Scripts de entorno: sim vs real
# ---------------------------------------------------------------------------
# Esta es la pieza que hace que mode="sim"/"real" de go2_controller.py sea
# solo un cambio de (domain_id, interfaz).
#
#   SIM  -> domain 1, interfaz "lo"   (convencion de unitree_mujoco)
#   REAL -> domain 0, interfaz <IFACE> (el robot usa domain 0 por defecto)
log "Generando setup_sim.sh y setup_real.sh"

cat > "${HOME}/unitree_ros2/setup_sim.sh" <<EOF
#!/bin/bash
# Entorno para SIMULACION (unitree_mujoco sobre loopback)
source /opt/ros/${ROS_DISTRO}/setup.bash
source \$HOME/unitree_ros2/cyclonedds_ws/install/setup.bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID=1
export GO2_MODE=sim
export GO2_IFACE=lo
export CYCLONEDDS_URI='<CycloneDDS><Domain><General><Interfaces>
    <NetworkInterface name="lo" priority="default" multicast="default" />
</Interfaces></General></Domain></CycloneDDS>'
echo "[go2] modo SIM  | domain 1 | iface lo"
EOF

cat > "${HOME}/unitree_ros2/setup_real.sh" <<EOF
#!/bin/bash
# Entorno para ROBOT REAL. Uso: source setup_real.sh <IFACE>
# El nombre de la interfaz NO se hardcodea: se detecta o se pasa por argumento.
GO2_IFACE="\${1:-\${GO2_IFACE:-}}"
if [ -z "\$GO2_IFACE" ]; then
    echo "ERROR: indica la interfaz. Ej: source setup_real.sh enp0s31f6" >&2
    return 1 2>/dev/null || exit 1
fi
source /opt/ros/${ROS_DISTRO}/setup.bash
source \$HOME/unitree_ros2/cyclonedds_ws/install/setup.bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID=0
export GO2_MODE=real
export GO2_IFACE
export CYCLONEDDS_URI="<CycloneDDS><Domain><General><Interfaces>
    <NetworkInterface name=\"\${GO2_IFACE}\" priority=\"default\" multicast=\"default\" />
</Interfaces></General></Domain></CycloneDDS>"
echo "[go2] modo REAL | domain 0 | iface \${GO2_IFACE}"
EOF

chmod +x "${HOME}/unitree_ros2/setup_sim.sh" "${HOME}/unitree_ros2/setup_real.sh"
ok "setup_sim.sh / setup_real.sh generados"

# ---------------------------------------------------------------------------
# 5. unitree_sdk2 (C++) y unitree_sdk2_python
# ---------------------------------------------------------------------------
log "unitree_sdk2 (C++)"
if [[ ! -d "${SRC_DIR}/unitree_sdk2" ]]; then
    git clone https://github.com/unitreerobotics/unitree_sdk2 "${SRC_DIR}/unitree_sdk2"
fi
cd "${SRC_DIR}/unitree_sdk2"
sudo ./install.sh                      # instala en /opt/unitree_robotics
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j"${NPROC}"
ok "unitree_sdk2 compilado"

# ---------------------------------------------------------------------------
# 6. venv de Python
# ---------------------------------------------------------------------------
# Un unico venv con --system-site-packages: en despliegue real necesitas
# torch (inferencia de la policy) y rclpy/unitree_sdk2py (DDS) en el MISMO
# proceso. Separarlos obliga a un puente IPC que no aporta nada.
log "Creando venv ${VENV_DIR}"
python3 -m venv --system-site-packages "${VENV_DIR}"
set +u; source "${VENV_DIR}/bin/activate"; set -u
pip install --upgrade pip wheel

log "Instalando torch (CPU), mujoco, ultralytics"
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install mujoco ultralytics numpy scipy pyyaml matplotlib pandas opencv-python-headless

log "unitree_sdk2_python"
if [[ ! -d "${SRC_DIR}/unitree_sdk2_python" ]]; then
    git clone https://github.com/unitreerobotics/unitree_sdk2_python "${SRC_DIR}/unitree_sdk2_python"
fi
cd "${SRC_DIR}/unitree_sdk2_python"
pip install -e .
ok "unitree_sdk2_python instalado"

# ---------------------------------------------------------------------------
# 7. unitree_mujoco: el sustituto del robot fisico
# ---------------------------------------------------------------------------
# Publica rt/lowstate y consume rt/lowcmd exactamente igual que el robot real,
# pero sobre loopback. Permite ensayar TODO el checklist de comunicacion antes
# de que llegue el hardware.
log "unitree_mujoco (simulador con interfaz DDS identica al robot)"
if [[ ! -d "${SRC_DIR}/unitree_mujoco" ]]; then
    git clone https://github.com/unitreerobotics/unitree_mujoco "${SRC_DIR}/unitree_mujoco"
fi

# Usamos el simulador Python: no requiere compilar MuJoCo desde fuente y
# reutiliza el paquete pip que acabamos de instalar.
CFG="${SRC_DIR}/unitree_mujoco/simulate_python/config.py"
if [[ -f "${CFG}" ]]; then
    grep -E '^(ROBOT|DOMAIN_ID|INTERFACE)' "${CFG}" || true
    echo
    echo "  Comprueba que config.py tiene: ROBOT='go2', DOMAIN_ID=1, INTERFACE='lo'"
fi
ok "unitree_mujoco disponible en ${SRC_DIR}/unitree_mujoco"

# ---------------------------------------------------------------------------
# 8. Resumen
# ---------------------------------------------------------------------------
log "Fase contenedor completada"
cat <<EOF

  Prueba de humo (dos terminales, ambas dentro del contenedor):

    Terminal 1 - arrancar el "robot" simulado:
      source ${VENV_DIR}/bin/activate
      cd ${SRC_DIR}/unitree_mujoco/simulate_python
      python3 unitree_mujoco.py

    Terminal 2 - leer su estado como si fuera el robot real:
      source \$HOME/unitree_ros2/setup_sim.sh
      source ${VENV_DIR}/bin/activate
      ros2 topic list
      ros2 topic hz /lowstate
      python3 ~/go2-research/tools/dds_smoketest.py --mode sim

  El dia que llegue el robot, lo unico que cambia es:
      source \$HOME/unitree_ros2/setup_real.sh <IFACE>
      python3 ~/go2-research/tools/dds_smoketest.py --mode real --iface <IFACE>

EOF
