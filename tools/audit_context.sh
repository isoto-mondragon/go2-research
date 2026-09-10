#!/usr/bin/env bash
# tools/audit_context.sh
#
# Recoge el estado completo del entorno en un unico fichero de texto.
# Ejecutar en el HOST: consulta el contenedor por si mismo.
# No modifica nada. No descarga blobs del repo archivado.
#
# Uso:
#   cd ~/go2-research && ./tools/audit_context.sh
#   (luego sube el fichero que indique al final)

set -uo pipefail

REPO="${HOME}/go2-research"
CONTAINER="go2-humble"
GH_USER="isoto-mondragon"
OUT="${REPO}/audit_$(date +%Y%m%d_%H%M).txt"

exec > >(tee "$OUT") 2>&1

sec() { printf '\n\n========== %s ==========\n' "$*"; }
sub() { printf '\n--- %s ---\n' "$*"; }
run() { printf '\n$ %s\n' "$*"; eval "$@" 2>&1 | head -60; }
cnt() { printf '\n[contenedor] $ %s\n' "$*"; distrobox enter "$CONTAINER" -- bash -lc "$*" 2>&1 | head -60; }

echo "AUDITORIA DE ENTORNO go2-research"
echo "fecha: $(date -Iseconds)"
echo "usuario: $(whoami)@$(hostname)"

# ===========================================================================
sec "1. HOST"
run "cat /etc/os-release | head -3"
run "uname -r"
run "free -h | head -2"
run "df -h ${HOME} | tail -1"
run "findmnt -no FSTYPE,SIZE /tmp"

sub "sysctl CycloneDDS"
run "sysctl net.core.rmem_max net.core.wmem_max net.ipv4.ipfrag_time net.ipv4.ipfrag_high_thresh"
run "cat /etc/sysctl.d/60-cyclonedds.conf"

sub "Red"
run "ip -br link"
run "ip -br addr"
run "nmcli -t -f NAME,DEVICE,TYPE,AUTOCONNECT con show"
run "nmcli -f connection.id,connection.interface-name,ipv4.method,ipv4.addresses,ipv4.never-default con show go2-eth"

sub "Contenedores"
run "distrobox version"
run "distrobox list"
run "podman info --format '{{.Host.Security.Rootless}} {{.Version.Version}}'"
run "podman ps -a --format '{{.Names}} {{.Image}} {{.Status}}'"

sub "SSH / GitHub"
run "ssh-add -l"
run "ssh -T git@github.com"

# ===========================================================================
sec "2. CONTENEDOR (${CONTAINER})"
cnt "cat /etc/os-release | head -3"
cnt "python3 --version; which python3"

sub "Red vista desde el contenedor (debe coincidir con el host)"
cnt "ip -br addr"

sub "ROS 2"
cnt "ls /opt/ros/"
cnt "dpkg -l | grep -E 'ros-humble-(desktop|rmw-cyclonedds|rosidl-generator-dds)' | awk '{print \$2, \$3}'"

sub "unitree_ros2 / CycloneDDS"
cnt "ls ~/unitree_ros2/"
cnt "ls ~/unitree_ros2/cyclonedds_ws/install/ 2>/dev/null | head -20"
cnt "cat ~/unitree_ros2/setup_sim.sh"
cnt "cat ~/unitree_ros2/setup_real.sh"

sub "unitree_sdk2 y unitree_mujoco"
cnt "ls ~/opt/"
cnt "ls /opt/unitree_robotics/ 2>/dev/null"
cnt "ls ~/opt/unitree_sdk2/build/bin 2>/dev/null | head"
cnt "grep -E '^(ROBOT|DOMAIN_ID|INTERFACE|USE_JOYSTICK|SIMULATE_DT|VIEWER_DT|ENABLE_ELASTIC_BAND)' ~/opt/unitree_mujoco/simulate_python/config.py"
cnt "ls ~/opt/unitree_mujoco/unitree_robots/go2/"
cnt "ls ~/opt/unitree_mujoco/example/python/ 2>/dev/null"

sub "Entorno Python"
cnt "source ~/venvs/go2/bin/activate && pip list 2>/dev/null | grep -iE 'torch|mujoco|ultralytics|numpy|scipy|cyclonedds|unitree|dvc|opencv|pyyaml|matplotlib|pandas'"
cnt "source ~/venvs/go2/bin/activate && python3 -c 'import torch, mujoco; print(\"torch\", torch.__version__, \"| mujoco\", mujoco.__version__)'"
cnt "source ~/venvs/go2/bin/activate && python3 -c 'import go2core; print(\"go2core OK:\", go2core.__file__)'"

# ===========================================================================
sec "3. REPO go2-research"
cd "$REPO" || exit 1
run "git log --oneline -10"
run "git remote -v"
run "git status --short"
run "du -sh .git"
run "git ls-files | wc -l"

sub "Arbol (2 niveles)"
run "find . -path ./.git -prune -o -type d -print | grep -v __pycache__ | sort | head -50"

sub "Ficheros versionados"
run "git ls-files"

sub "Contrato sim2real"
run "cat usecases/uc01_locomotion/configs/robot_go2.yaml"

sub "Presencia de artefactos clave"
for f in src/go2core/control/go2_controller.py \
         usecases/uc01_locomotion/notebooks \
         docs/USAGE_GUIDE.md docs/STUDENT_GUIDE.md \
         experiments; do
    printf '  %-55s %s\n' "$f" "$([ -e "$f" ] && echo PRESENTE || echo FALTA)"
done
run "ls -la usecases/uc01_locomotion/notebooks/ 2>/dev/null"
run "find experiments -name manifest.json"

sub "DVC"
run "which dvc && dvc status -c 2>&1 | head -5 || echo 'DVC no instalado'"

# ===========================================================================
sec "4. REPO ARCHIVADO (listado sin descargar blobs)"
TMP=$(mktemp -d)
FOUND=""
for name in go2-robotics-workspace-archive go2-robotics-workspace; do
    if git ls-remote "git@github.com:${GH_USER}/${name}.git" HEAD >/dev/null 2>&1; then
        FOUND="$name"; break
    fi
done

if [[ -z "$FOUND" ]]; then
    echo "No se ha podido acceder a ningun repo de workspace. Nombres probados:"
    echo "  ${GH_USER}/go2-robotics-workspace-archive"
    echo "  ${GH_USER}/go2-robotics-workspace"
else
    echo "Repo encontrado: ${GH_USER}/${FOUND}"
    # --filter=blob:none descarga arboles y commits pero NO el contenido.
    git clone --filter=blob:none --no-checkout --depth 1 \
        "git@github.com:${GH_USER}/${FOUND}.git" "$TMP/arch" 2>&1 | tail -3

    if [[ -d "$TMP/arch" ]]; then
        cd "$TMP/arch"
        sub "Ficheros de codigo y documentacion (sin binarios)"
        git ls-tree -r --name-only HEAD | grep -vE '\.(pt|pth|onnx|ckpt|npz|bag|db3|mp4|png|jpg|so|a|o)$' | head -120
        sub "Total de ficheros"
        git ls-tree -r --name-only HEAD | wc -l
        sub "Candidatos a migrar"
        git ls-tree -r --name-only HEAD | grep -iE 'controller|follow_yolo|\.ipynb$|GUIDE\.md$|requirements|README' | head -30
        sub "Binarios pesados (se quedan en el archivo)"
        git ls-tree -r --name-only HEAD | grep -E '\.(pt|pth|onnx|ckpt|npz|bag|db3|mp4)$' | head -30
        cd "$REPO"
    fi
fi
rm -rf "$TMP"

# ===========================================================================
sec "5. PUBLICO go2-perception-stack"
if git ls-remote "git@github.com:${GH_USER}/go2-perception-stack.git" HEAD >/dev/null 2>&1; then
    TMP2=$(mktemp -d)
    git clone --filter=blob:none --no-checkout --depth 1 \
        "git@github.com:${GH_USER}/go2-perception-stack.git" "$TMP2/p" 2>&1 | tail -2
    [[ -d "$TMP2/p" ]] && (cd "$TMP2/p" && git ls-tree -r --name-only HEAD | head -40)
    rm -rf "$TMP2"
else
    echo "No accesible."
fi

# ===========================================================================
sec "FIN"
echo
echo "Informe guardado en: $OUT"
echo "Subelo a la conversacion."
