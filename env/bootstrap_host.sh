#!/usr/bin/env bash
# env/bootstrap_host.sh
#
# Prepara el HOST (Ubuntu 26.04 LTS "Resolute Raccoon") para desarrollo Go2.
# El host NO instala ROS2 ni el SDK de Unitree: solo contenedores, red y kernel.
#
# Idempotente: se puede ejecutar varias veces sin romper nada.
# NO requiere el robot fisico.
#
# Uso:
#   ./bootstrap_host.sh
#   ./bootstrap_host.sh --skip-container     # solo host, sin crear el contenedor
#
# Autor: Ibon Soto Alsua - DANZ, Mondragon Unibertsitatea

set -euo pipefail

CONTAINER_NAME="go2-humble"
CONTAINER_IMAGE="docker.io/library/ubuntu:22.04"
CONTAINER_HOME="${HOME}/containers/${CONTAINER_NAME}"
WORKSPACE_DIR="${HOME}/go2-research"
SKIP_CONTAINER=0

[[ "${1:-}" == "--skip-container" ]] && SKIP_CONTAINER=1

log()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m[ok] %s\033[0m\n' "$*"; }

# ---------------------------------------------------------------------------
# 0. Comprobaciones previas
# ---------------------------------------------------------------------------
log "Comprobaciones previas"

if [[ $EUID -eq 0 ]]; then
    echo "No ejecutes este script como root. Usa tu usuario normal; pedira sudo." >&2
    exit 1
fi

. /etc/os-release
echo "Sistema: ${PRETTY_NAME}"
if [[ "${VERSION_ID}" != "26.04" ]]; then
    warn "Este script se escribio para Ubuntu 26.04. Detectado ${VERSION_ID}. Continuo, pero revisa."
fi

FREE_GB=$(df -BG --output=avail "${HOME}" | tail -1 | tr -dc '0-9')
echo "Espacio libre en \$HOME: ${FREE_GB} GB"
if (( FREE_GB < 60 )); then
    warn "Menos de 60 GB libres. ROS2 desktop + torch + checkpoints se quedan cortos."
fi

# Ubuntu 26.04 monta /tmp como tmpfs. Con 16 GB de RAM, compilar ahi es mala idea.
if findmnt -no FSTYPE /tmp | grep -q tmpfs; then
    warn "/tmp es tmpfs (por defecto en 26.04). NO compiles nada grande en /tmp."
fi

# ---------------------------------------------------------------------------
# 1. Paquetes del host
# ---------------------------------------------------------------------------
log "Instalando paquetes base del host"
sudo apt-get update
sudo apt-get install -y \
    podman distrobox uidmap slirp4netns fuse-overlayfs \
    git curl ca-certificates build-essential \
    network-manager iproute2 tcpdump ethtool

ok "Paquetes instalados"

echo "distrobox: $(distrobox version 2>/dev/null || echo 'ERROR')"
echo "podman rootless: $(podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null || echo 'ERROR')"

# ---------------------------------------------------------------------------
# 2. Tuning de kernel para CycloneDDS
# ---------------------------------------------------------------------------
# Imprescindible para /lowstate a 500 Hz y para pointclouds del LiDAR.
# Un contenedor rootless NO puede aplicar esto: tiene que estar en el host.
log "Aplicando tuning de red para CycloneDDS"

sudo tee /etc/sysctl.d/60-cyclonedds.conf >/dev/null <<'EOF'
# Buffers de recepcion para CycloneDDS / Unitree SDK2
net.core.rmem_max=8388608
net.core.rmem_default=8388608
net.core.wmem_max=8388608
# Reensamblado de fragmentos IP para mensajes grandes (pointclouds)
net.ipv4.ipfrag_time=3
net.ipv4.ipfrag_high_thresh=134217728
EOF

sudo sysctl --system >/dev/null
echo "rmem_max = $(sysctl -n net.core.rmem_max)"
ok "sysctl aplicado y persistente"

# ---------------------------------------------------------------------------
# 3. Inventario de interfaces de red
# ---------------------------------------------------------------------------
# Se hace AHORA, sin robot: la interfaz existe aunque no haya cable conectado.
log "Inventario de interfaces de red"

ip -br link
echo
echo "Interfaces Ethernet candidatas (excluye lo, wlan, virtuales):"
ip -br link | awk '$1 !~ /^(lo|wl|docker|podman|veth|virbr|tun|tap)/ {print "  - " $1 "  (" $2 ")"}'

cat <<'EOF'

  NOTA: la interfaz que uses con el Go2 debe decidirse AHORA.
  - Si vas a usar el puerto Ethernet integrado del ProBook -> nombre tipo enp0s31f6 / eno1
  - Si vas a usar un adaptador USB-C a Ethernet -> nombre tipo enx<mac>, y CAMBIA
    si enchufas el adaptador en otro puerto USB. Conectalo ya y anota el nombre.

  Guarda el nombre elegido en env/go2_net.env y usalo en todos los scripts.
EOF

# ---------------------------------------------------------------------------
# 4. Contenedor de desarrollo
# ---------------------------------------------------------------------------
if [[ $SKIP_CONTAINER -eq 1 ]]; then
    warn "--skip-container: no se crea el contenedor"
else
    log "Creando contenedor distrobox '${CONTAINER_NAME}' (Ubuntu 22.04)"

    mkdir -p "${CONTAINER_HOME}" "${WORKSPACE_DIR}"

    if distrobox list | grep -qw "${CONTAINER_NAME}"; then
        warn "El contenedor '${CONTAINER_NAME}' ya existe. No se recrea."
    else
        # --home separado: evita que los dotfiles y los site-packages de
        # Python 3.13 del host colisionen con los de Python 3.10 del contenedor.
        # --volume: el repo de trabajo vive en el host y se ve igual desde dentro.
        distrobox create \
            --name "${CONTAINER_NAME}" \
            --image "${CONTAINER_IMAGE}" \
            --home "${CONTAINER_HOME}" \
            --volume "${WORKSPACE_DIR}:${WORKSPACE_DIR}:rw" \
            --yes
        ok "Contenedor creado"
    fi

    log "Verificando que el contenedor comparte el namespace de red del host"
    echo "--- HOST ---"
    ip -br addr | head -20
    echo "--- CONTENEDOR ---"
    distrobox enter "${CONTAINER_NAME}" -- ip -br addr | head -20

    cat <<'EOF'

  VERIFICACION CRITICA: las dos listas de arriba deben ser IDENTICAS.
  Si el contenedor solo ve 'lo' o una IP 10.0.2.x, distrobox esta aislando
  la red y la comunicacion DDS por Ethernet con el robot NO funcionara.
  En ese caso recrea el contenedor anadiendo:
      --additional-flags "--network host"

EOF
fi

# ---------------------------------------------------------------------------
# 5. Resumen
# ---------------------------------------------------------------------------
log "Fase host completada"
cat <<EOF

  Siguiente paso:
      distrobox enter ${CONTAINER_NAME}
      ${WORKSPACE_DIR}/env/bootstrap_container.sh

  Pendiente para el dia que llegue el robot:
      ./env/go2_net.sh up <IFACE>

EOF
