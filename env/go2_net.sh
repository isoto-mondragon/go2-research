#!/usr/bin/env bash
# env/go2_net.sh
#
# Gestion del perfil de red Ethernet para el Unitree Go2. Se ejecuta en el HOST.
#
# El perfil se crea con ipv4.never-default e ipv6 deshabilitado, para que
# enchufar el robot NUNCA te deje sin internet ni te secuestre el DNS.
#
# Uso:
#   ./go2_net.sh create <IFACE>   # crear el perfil (se puede hacer SIN robot)
#   ./go2_net.sh up               # activar (requiere cable conectado al robot)
#   ./go2_net.sh down             # desactivar
#   ./go2_net.sh status           # estado del perfil y de la interfaz
#   ./go2_net.sh probe            # diagnostico de conectividad con el robot
#   ./go2_net.sh detect           # sugerir que interfaz esta conectada al robot

set -euo pipefail

CON_NAME="go2-eth"
HOST_IP="192.168.123.222/24"
ROBOT_MAIN="192.168.123.161"    # placa principal del Go2
ROBOT_JETSON="192.168.123.18"   # Jetson de la version EDU

log()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m[ok] %s\033[0m\n' "$*"; }
bad()  { printf '\033[1;31m[x] %s\033[0m\n' "$*"; }

usage() { sed -n '2,20p' "$0"; exit 1; }

cmd="${1:-}"; [[ -n "$cmd" ]] || usage

case "$cmd" in

detect)
    log "Interfaces Ethernet no virtuales"
    ip -br link | awk '$1 !~ /^(lo|wl|docker|podman|veth|virbr|tun|tap|br-)/ {print}'
    echo
    log "Cuales tienen enlace fisico (carrier) ahora mismo"
    found=0
    for i in $(ip -br link | awk '$1 !~ /^(lo|wl|docker|podman|veth|virbr|tun|tap|br-)/ {print $1}'); do
        if [[ "$(cat /sys/class/net/"$i"/carrier 2>/dev/null || echo 0)" == "1" ]]; then
            ok "$i tiene enlace"; found=1
        else
            echo "    $i sin enlace (NO-CARRIER)"
        fi
    done
    (( found )) || warn "Ninguna interfaz con enlace. Conecta el cable al robot encendido."
    ;;

create)
    IFACE="${2:-}"; [[ -n "$IFACE" ]] || { bad "Falta <IFACE>. Usa: $0 detect"; exit 1; }
    [[ -e "/sys/class/net/${IFACE}" ]] || { bad "La interfaz '${IFACE}' no existe"; exit 1; }

    log "Creando perfil '${CON_NAME}' sobre ${IFACE}"
    nmcli con delete "${CON_NAME}" 2>/dev/null || true
    nmcli con add type ethernet ifname "${IFACE}" con-name "${CON_NAME}" \
        ipv4.method manual \
        ipv4.addresses "${HOST_IP}" \
        ipv4.never-default yes \
        ipv6.method disabled \
        connection.autoconnect no
    ok "Perfil creado (autoconnect OFF: se activa a mano con '$0 up')"
    nmcli -f connection.id,ipv4.addresses,ipv4.never-default con show "${CON_NAME}"
    ;;

up)
    log "Activando ${CON_NAME}"
    nmcli con up "${CON_NAME}"
    ip -br addr show "$(nmcli -g connection.interface-name con show "${CON_NAME}")"
    ok "Activo"
    ;;

down)
    nmcli con down "${CON_NAME}" && ok "Desactivado"
    ;;

status)
    nmcli -f NAME,DEVICE,STATE con show --active | grep -E "NAME|${CON_NAME}" || warn "No activo"
    echo
    ip route | grep -E '^default' || warn "Sin ruta por defecto"
    ;;

probe)
    IFACE="$(nmcli -g connection.interface-name con show "${CON_NAME}" 2>/dev/null || true)"
    [[ -n "$IFACE" ]] || { bad "El perfil ${CON_NAME} no existe. Ejecuta '$0 create <IFACE>'"; exit 1; }

    log "1/4  Enlace fisico"
    if [[ "$(cat /sys/class/net/"$IFACE"/carrier 2>/dev/null || echo 0)" == "1" ]]; then
        ok "${IFACE} tiene carrier"
    else
        bad "${IFACE} sin carrier: revisa el cable y que el robot este encendido (dale 45 s)"
        exit 1
    fi

    log "2/4  Direccion IP del host"
    ip -br addr show "$IFACE"

    log "3/4  Ping al robot"
    for ip in "$ROBOT_MAIN" "$ROBOT_JETSON"; do
        if ping -c 3 -W 2 "$ip" >/dev/null 2>&1; then ok "$ip responde"; else bad "$ip no responde"; fi
    done

    log "4/4  Trafico ARP (5 s) - dice si el robot esta hablando aunque no haga ping"
    sudo timeout 5 tcpdump -i "$IFACE" -n arp 2>/dev/null | head -20 || true

    cat <<'EOF'

  Interpretacion:
    ping OK                    -> pasa al smoke test DDS
    ARP si / ping no           -> problema de mascara o de IP; revisa 192.168.123.0/24
    ni ARP ni ping             -> cable, puerto o el robot no ha arrancado del todo
EOF
    ;;

*) usage ;;
esac
