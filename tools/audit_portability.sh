#!/usr/bin/env bash
# tools/audit_portability.sh
#
# Busca en el repositorio todo lo que ata el proyecto a ESTA maquina y que
# impediria que funcionase en el ordenador de otra persona.
#
# Se ejecuta antes de dockerizar: meter en una imagen un proyecto con rutas
# absolutas y nombres de interfaz cableados no arregla el problema, lo
# encapsula.
#
# No modifica nada. Solo informa.
#
# Uso:
#   cd ~/go2-research && ./tools/audit_portability.sh

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

EXCLUDES=(--exclude-dir=.git --exclude-dir=.dvc --exclude-dir=__pycache__
          --exclude-dir=node_modules --exclude-dir=build --exclude-dir=install
          --exclude=*.ipynb --exclude=*.csv --exclude=*.json --exclude=*.log
          --exclude=audit_*.txt)

total=0

sec() { printf '\n\033[1;34m=== %s ===\033[0m\n' "$*"; }
hit() {
    local n
    n=$(grep -rIn "${EXCLUDES[@]}" -e "$1" . 2>/dev/null | grep -v '^\./tools/audit_portability.sh' | wc -l)
    total=$((total + n))
    if [[ $n -gt 0 ]]; then
        printf '\033[1;33m  [%2d] %s\033[0m\n' "$n" "$2"
        grep -rIn "${EXCLUDES[@]}" -e "$1" . 2>/dev/null \
            | grep -v '^\./tools/audit_portability.sh' | head -8 \
            | sed 's/^/       /'
        [[ $n -gt 8 ]] && echo "       ... y $((n - 8)) mas"
    else
        printf '\033[0;32m  [ 0] %s\033[0m\n' "$2"
    fi
}

echo "AUDITORIA DE PORTABILIDAD - $(date -Iseconds)"
echo "repositorio: $(pwd)"

sec "1. Rutas absolutas del usuario"
hit '/home/ibon'            'ruta absoluta /home/ibon'
hit '~/go2-research'        'ruta ~/go2-research (deberia ser $GO2 o relativa)'
hit '~/opt/unitree'         'ruta ~/opt/unitree* (ubicacion de dependencias)'
hit '~/venvs/go2'           'ruta del venv cableada'
hit '~/robotics'            'ruta ~/robotics (heredada del workspace WSL2)'
hit '/content/'             'rutas de Colab (normal en notebooks, revisar en .py)'
hit '~/Descargas\|~/Downloads' 'carpeta de descargas del usuario'

sec "2. Configuracion de red cableada"
hit 'enp3s0'                'nombre de interfaz Ethernet'
hit '192\.168\.123\.'       'IPs de la red del robot (correcto en el contrato, no en codigo)'

sec "3. Entorno de ejecucion"
hit 'distrobox'             'referencias a distrobox (no existira en Docker)'
hit 'go2sim\|go2real\|go2 '  'alias personales del .bashrc'

sec "4. Dependencias externas al repositorio"
hit 'unitree_ros2'          'unitree_ros2 (se clona fuera del repo)'
hit 'unitree_mujoco'        'unitree_mujoco (se clona fuera del repo)'
hit 'unitree_sdk2'          'unitree_sdk2 (se clona fuera del repo)'

sec "5. Ficheros de configuracion modificados a mano"
echo "  Cambios aplicados a ~/opt/unitree_mujoco/simulate_python/config.py"
echo "  que NO estan versionados y se perderian en otra maquina:"
CFG="$HOME/opt/unitree_mujoco/simulate_python/config.py"
if [[ -f "$CFG" ]]; then
    grep -nE '^(ROBOT_SCENE|USE_JOYSTICK|VIEWER_DT|DOMAIN_ID|INTERFACE|ROBOT) *=' "$CFG" \
        | sed 's/^/       /'
    printf '\033[1;33m       ^ estos valores deben quedar en el repo o en la imagen\033[0m\n'
else
    echo "       (no se encuentra config.py; ejecuta desde el contenedor)"
fi

sec "6. Escena plana"
if [[ -f usecases/uc01_locomotion/configs/scene_flat.xml ]]; then
    printf '\033[0;32m  [ok] scene_flat.xml esta versionado en el repo\033[0m\n'
else
    printf '\033[1;33m  [!!] scene_flat.xml NO esta en el repo: se perderia\033[0m\n'
    total=$((total + 1))
fi

sec "7. Ficheros que asumen GPU o arquitectura"
hit 'cuda\|CUDA'            'referencias a CUDA'
hit 'nvidia'                'referencias a NVIDIA'

sec "RESUMEN"
echo "  incidencias encontradas: $total"
cat <<'EOF'

  Que hacer con cada tipo:

  rutas absolutas   -> variable de entorno GO2_ROOT, con la raiz del repo
                       calculada desde __file__ en los .py
  interfaz de red   -> variable GO2_IFACE, leida del entorno y no del contrato
  dependencias      -> instalarlas en la imagen Docker, en rutas fijas y
                       conocidas (/opt/go2/...)
  config.py del sim -> versionar el fichero en el repo y copiarlo en la imagen,
                       o pasar los valores por variables de entorno
  distrobox/alias   -> sustituir por el entrypoint del contenedor

  Lo que ya esta bien y no hay que tocar:
  - las IPs 192.168.123.x DENTRO del contrato (son del robot, no de la maquina)
  - las rutas /content de los notebooks (son de Colab)
EOF
