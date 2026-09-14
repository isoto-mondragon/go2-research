#!/usr/bin/env python3
"""Construye Unitree_RL_MJLAB_sweep.ipynb.

El notebook se genera desde este script en vez de editarse a mano, para que
quede versionado como texto legible en git y para poder regenerarlo cuando
cambie el diseno del barrido.

    python3 tools/build_colab_notebook.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "usecases/uc01_locomotion/notebooks/Unitree_RL_MJLAB_sweep.ipynb"


def _lines(text: str) -> list[str]:
    """Trocea en lineas CONSERVANDO el salto final de cada una.

    nbformat guarda `source` como lista de lineas, y cada elemento debe
    terminar en "\\n" salvo el ultimo. Sin esos saltos, Colab concatena todo
    el codigo en una sola linea y la celda revienta con SyntaxError.
    """
    ls = text.split("\n")
    return [l + "\n" for l in ls[:-1]] + [ls[-1]]


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {},
            "source": _lines(text.strip())}


def code(text: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": _lines(text.strip("\n"))}


cells = []

# ---------------------------------------------------------------------------
cells.append(md(r"""
# Entrenamiento Go2 en Colab: barrido de presupuesto de computo

Entrena `Unitree-Go2-Flat` con `unitree_rl_mjlab`, exporta a ONNX y empaqueta
el resultado para desplegarlo en `go2-research`.

## Que hace este notebook distinto del original

1. **Presupuesto de tiempo, no parada manual.** La pregunta del experimento es
   cuanto rinde una hora de T4, asi que el tiempo tiene que ser exacto.
2. **Semilla explicita.** Sin ella las repeticiones son identicas y las barras
   de error serian falsas.
3. **Versiones fijadas.** Commit del repo y versiones de mujoco, mujoco-warp y
   warp-lang. Con dependencias flotantes, dos runs no son comparables.
4. **Exporta lo que necesita el despliegue**, incluido `deploy_params.yaml`.

## Diseno del barrido

4 presupuestos x 3 semillas = 12 entrenamientos:

| presupuesto | semillas |
|---|---|
| 5 min | 1, 2, 3 |
| 15 min | 1, 2, 3 |
| 30 min | 1, 2, 3 |
| 60 min | 1, 2, 3 |
| 120 min | 1, 2, 3 |

Unas 11.5 h de T4 en total, en 15 runs.

El entrenamiento completo estima unas 7 h 30 con 4096 entornos en T4 gratuita,
asi que el barrido cubre del 1 % al 27 % de ese total.

El punto de 5 min se anade despues de ver que una politica de 15 min ya sigue
comandos razonablemente bien: el tramo interesante de la curva esta por debajo
de lo previsto, y sin ese punto se corre el riesgo de medir cuatro veces la
meseta y concluir que el computo no importa.

Las sesiones de T4 gratuita se cortan a menudo por encima de 2 h, por eso el
techo esta en 120 min y no mas arriba.

## Para cada run

1. Cambiar `SEED` y `BUDGET_MIN` en la celda de parametros.
2. Entorno de ejecucion > Reiniciar entorno de ejecucion.
3. Ejecutar todo.
4. Descargar el zip y pasarlo por `tools/import_run.py` en el portatil.
"""))

# ---------------------------------------------------------------------------
cells.append(md("## 0. Parametros del run"))

cells.append(code(r"""
# ===== LO UNICO QUE SE TOCA ENTRE RUNS =====
SEED       = 1          # 1, 2 o 3
BUDGET_MIN = 15         # 5, 15, 30, 60 o 120

# Constantes del barrido
NUM_ENVS = 4096
TASK     = "Unitree-Go2-Flat"

# ===== VERSIONES FIJADAS =====
# Conjunto verificado el 2026-09-14. NO tocar durante el barrido: si cambian,
# los runs dejan de ser comparables entre si.
# Justificacion completa en ../train/ENTORNO_FIJADO.md
REPO_COMMIT      = "1425b15f73bd4095f0df53709d7c389c3eb9e790"
PIN_MUJOCO       = "3.7.0"    # ultima con mjENBL_MULTICCD; la 3.8.0 lo elimina
PIN_MUJOCO_WARP  = "3.5.0"    # de PyPI. NO instalar desde git: la rama
                              # principal exige warp-lang>=1.15 y eso rompe mjlab
PIN_WARP         = "1.12.1"   # mjlab 1.2.0 usa wp.context.runtime, retirado en 1.13

TAG = f"t4_{BUDGET_MIN}m_seed{SEED}"
print(f"run: {TAG}")
print(f"  presupuesto : {BUDGET_MIN} min de T4")
print(f"  semilla     : {SEED}")
print(f"  entornos    : {NUM_ENVS}")
print(f"  repo commit : {REPO_COMMIT or 'SIN FIJAR (primera vez)'}")
"""))

# ---------------------------------------------------------------------------
cells.append(md(r"""
## 1. GPU y Drive

Si `nvidia-smi` falla, el entorno no tiene GPU: Entorno de ejecucion >
Cambiar tipo de entorno > T4 > Guardar > Conectar.
"""))

cells.append(code(r"""
!nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv

from google.colab import drive
drive.mount('/content/drive')

import os
DRIVE_ROOT = '/content/drive/MyDrive/go2_rl'
os.makedirs(f'{DRIVE_ROOT}/logs', exist_ok=True)
os.makedirs(f'{DRIVE_ROOT}/exports', exist_ok=True)
print('Drive OK ->', DRIVE_ROOT)
"""))

# ---------------------------------------------------------------------------
cells.append(md(r"""
## 2. Clonar el repositorio

Con `REPO_COMMIT` fijado, todos los runs del barrido usan exactamente el mismo
codigo. La primera vez se deja a `None` y se copia el SHA que imprime.
"""))

cells.append(code(r"""
%cd /content
!rm -rf unitree_rl_mjlab
!git clone --quiet https://github.com/unitreerobotics/unitree_rl_mjlab.git
%cd /content/unitree_rl_mjlab

if REPO_COMMIT:
    !git checkout -q {REPO_COMMIT}
    print(f"repo fijado en {REPO_COMMIT}")
else:
    print("AVISO: repo SIN FIJAR. Copia el SHA de abajo a REPO_COMMIT.")

import subprocess
REPO_SHA = subprocess.run(['git', 'rev-parse', 'HEAD'],
                          capture_output=True, text=True).stdout.strip()
print(f"\nSHA: {REPO_SHA}")

!curl -LsSf https://astral.sh/uv/install.sh | sh
import os
os.environ['PATH'] = '/root/.local/bin:/usr/local/bin:' + os.environ['PATH']
!uv --version
"""))

# ---------------------------------------------------------------------------
cells.append(md(r"""
## 3. Dependencias

### El conjunto de versiones esta FIJADO

| paquete | version | motivo |
|---|---|---|
| `mujoco` | 3.7.0 | ultima que conserva `mjENBL_MULTICCD` |
| `mujoco-warp` | 3.5.0 | de PyPI, NO desde git |
| `warp-lang` | 1.12.1 | `mjlab 1.2.0` usa `wp.context.runtime`, retirado en 1.13 |
| `mjlab` | 1.2.0 | lo fija el repo |

`mjlab 1.2.0` declara `mujoco>=3.5.0` **sin techo**. Con resolucion libre se
instala `mujoco 3.13.0` y `mujoco-warp 3.5.0` revienta con:

    AttributeError: type object 'mujoco._enums.mjtEnableBit'
                    has no attribute 'mjENBL_MULTICCD'

Ese simbolo se retiro de MuJoCo en la 3.8.0 (2026-04-24).

Instalar `mujoco-warp` desde git esquiva ese error, pero la rama principal
exige `warp-lang>=1.15`, que rompe `mjlab 1.2.0`. Ese es el circulo. Se sale
**bajando mujoco a 3.7.0**, no subiendo mujoco-warp.

### Que cambio respecto al notebook original

El original aplicaba tres "fixes" que hoy son obsoletos y dos de ellos rompen
la instalacion:

1. ~~`mujoco-warp` desde git~~ - ya no hace falta. Cuando se escribio ese fix,
   `mujoco-warp` no estaba en PyPI. Desde junio de 2026 si esta, y `mjlab`
   lo fija con `mujoco-warp~=3.11.0`. Instalar la rama principal por encima
   rompe ese pin.
2. ~~`warp-lang==1.12.1`~~ - **esto es lo que rompia**. `mjlab 1.6.0` exige
   `warp-lang>=1.14.0` y `mujoco-warp>=3.11` exige `>=1.14`. Forzar la 1.12.1
   (abril de 2026) da:

       TypeError: kernel() got an unexpected keyword argument 'grid_stride'

3. `uv pip install -e . --no-deps` - **este si sigue haciendo falta**, para
   que `import src.tasks` encuentre los entornos del repo.

La instruccion correcta hoy es dejar que el resolutor elija el conjunto
coherente, y despues fijar lo que haya elegido.
"""))

cells.append(code(r"""
%cd /content/unitree_rl_mjlab

# 1. Resolucion normal: mjlab arrastra mujoco, mujoco-warp y warp-lang
#    en versiones compatibles entre si.
!uv pip install --system --quiet .

# 2. Pines explicitos, solo si ya se fijaron en la celda de parametros.
_pins = []
if PIN_MUJOCO:      _pins.append(f"mujoco=={PIN_MUJOCO}")
if PIN_MUJOCO_WARP: _pins.append(f"mujoco-warp=={PIN_MUJOCO_WARP}")
if PIN_WARP:        _pins.append(f"warp-lang=={PIN_WARP}")
if _pins:
    print("aplicando pines:", _pins)
    # --reinstall es imprescindible: sin el, uv ve que ya hay un mujoco
    # instalado y no lo BAJA a la version fijada.
    !uv pip install --system --quiet --reinstall {" ".join(_pins)}
else:
    print("AVISO: sin pines. El resolutor libre instala mujoco 3.13 y")
    print("mujoco-warp 3.5.0 falla con mjENBL_MULTICCD. Ver ENTORNO_FIJADO.md")

# 3. Modo editable sin dependencias, para que import src.tasks funcione.
!uv pip install --system --quiet -e . --no-deps

print("\n===== VERSIONES INSTALADAS =====")
import importlib.metadata as md
VERSIONS = {}
for p in ("mujoco", "mujoco-warp", "warp-lang", "mjlab", "rsl-rl-lib", "torch", "numpy"):
    try:
        VERSIONS[p] = md.version(p)
    except Exception:
        VERSIONS[p] = None
    print(f"  {p:<14} {VERSIONS[p]}")

print("\nCopia estos valores a la celda de parametros:")
print(f"  PIN_MUJOCO       = {VERSIONS['mujoco']!r}")
print(f"  PIN_MUJOCO_WARP  = {VERSIONS['mujoco-warp']!r}")
print(f"  PIN_WARP         = {VERSIONS['warp-lang']!r}")
print(f"  REPO_COMMIT      = {REPO_SHA!r}")
"""))

# ---------------------------------------------------------------------------
cells.append(md(r"""
## 4. Verificacion

Los cuatro checks tienen que pasar. Si alguno falla, parar aqui: un
entrenamiento lanzado sobre un entorno roto gasta GPU para nada.
"""))

cells.append(code(r"""
import subprocess, sys

CHECKS = [
    ("mujoco",      "import mujoco; print(mujoco.__version__)"),
    ("mujoco_warp", "import mujoco_warp; print(getattr(mujoco_warp,'__version__','?'))"),
    ("warp",        "import warp as wp; print(wp.__version__)"),
    ("torch cuda",  "import torch; print(torch.__version__, 'cuda', torch.cuda.is_available())"),
    ("src.tasks",   "import src.tasks; print('registrado')"),
]

fallos = []
for nombre, snippet in CHECKS:
    r = subprocess.run([sys.executable, "-c", snippet],
                       cwd="/content/unitree_rl_mjlab",
                       capture_output=True, text=True)
    if r.returncode == 0:
        print(f"  [ok] {nombre:<12} {r.stdout.strip()}")
    else:
        ultima = r.stderr.strip().split("\n")[-1][:160]
        print(f"  [XX] {nombre:<12} {ultima}")
        fallos.append((nombre, r.stderr))

print()
if fallos:
    print(f"{len(fallos)} check(s) fallan. NO sigas.")
    print("\nTraceback completo del primero:\n")
    print(fallos[0][1][-3000:])
else:
    print("Entorno correcto.")
"""))

cells.append(code(r"""
%cd /content/unitree_rl_mjlab
!python scripts/list_envs.py 2>&1 | grep -i go2
"""))

# ---------------------------------------------------------------------------
cells.append(md(r"""
## 5. Enlazar `logs/` a Drive

Asi los checkpoints y los eventos de TensorBoard sobreviven a las
desconexiones de Colab.
"""))

cells.append(code(r"""
!rm -rf /content/unitree_rl_mjlab/logs
!ln -s /content/drive/MyDrive/go2_rl/logs /content/unitree_rl_mjlab/logs
!ls /content/unitree_rl_mjlab/logs/rsl_rl/go2_velocity/ 2>/dev/null | tail -5 || echo 'Drive vacio (primer entrenamiento)'
"""))

cells.append(md(r"""
### Limpiar runs antiguos (opcional)

No hace falta para el barrido: el empaquetado detecta el directorio creado por
**este** run comparando el listado antes y despues de entrenar. Ejecutar solo
si el Drive se llena.
"""))

cells.append(code(r"""
# Descomentar para borrar TODOS los runs anteriores.
# !rm -rf "/content/drive/MyDrive/go2_rl/logs/rsl_rl/go2_velocity/"*
print("nada borrado (celda comentada a proposito)")
"""))

# ---------------------------------------------------------------------------
cells.append(md(r"""
## 6. TensorBoard

Se arranca antes del entrenamiento para que capture los eventos desde el
primer momento. Drive es lento, asi que se sincroniza a `/tmp` cada 20 s y
TensorBoard lee de ahi.
"""))

cells.append(code(r"""
import threading, subprocess, os, time

LOCAL_LOGS = '/tmp/tb_logs'
DRIVE_LOGS = '/content/drive/MyDrive/go2_rl/logs'
os.makedirs(LOCAL_LOGS, exist_ok=True)

subprocess.run(['rsync', '-a', f'{DRIVE_LOGS}/', f'{LOCAL_LOGS}/'], check=False)
print('sync inicial OK')

_stop_flag = {'stop': False}
def _sync_loop():
    while not _stop_flag['stop']:
        try:
            subprocess.run(['rsync', '-a', '--quiet',
                            f'{DRIVE_LOGS}/', f'{LOCAL_LOGS}/'],
                           timeout=30, check=False)
        except Exception as e:
            print('sync error:', e)
        time.sleep(20)

threading.Thread(target=_sync_loop, daemon=True).start()
print('sync continuo cada 20 s')

!pkill -f tensorboard 2>/dev/null
time.sleep(2)

%reload_ext tensorboard
%tensorboard --logdir /tmp/tb_logs --reload_interval 30 --port 6006
"""))

# ---------------------------------------------------------------------------
cells.append(md(r"""
## 7. Entrenamiento

Arranca en segundo plano y **se para solo** al agotar `BUDGET_MIN`. No hay que
pulsar stop: eso es justo lo que hace que el presupuesto sea exacto.

### El mensaje final NO se ve, y es normal

Colab cierra el stdout de la celda cuando termina su codigo sincrono. Como
aqui el proceso y los hilos de seguimiento van en segundo plano, la celda
recibe el tick verde a los pocos segundos y **todo lo que impriman los hilos
despues se pierde**: el mensaje `terminado (exit=0)` no llega a verse nunca.

El entrenamiento si corre. Para seguirlo, en una celda aparte:

    !tail -n 40 /tmp/train_output.log
    !ps aux | grep train.py | grep -v grep

La celda de empaquetado detecta el final por si misma, asi que basta con
esperar los `BUDGET_MIN` y ejecutarla.

### Deteccion de flags

Los nombres de los flags (`--agent.seed`, `--agent.save-interval`) cambian
entre versiones de mjlab y tyro, asi que se leen del `--help` en vez de
suponerlos. Si no aparece el de la semilla, la celda avisa en grande: un
barrido sin semilla no tiene barras de error.
"""))

cells.append(code(r"""
import subprocess, os, threading, time, signal, glob

env = os.environ.copy()
env['PYTHONPATH']      = '/content/unitree_rl_mjlab'
env['WANDB_MODE']      = 'disabled'
env['WANDB_DISABLED']  = 'true'
env['PYTHONHASHSEED']  = str(SEED)

LOG_FILE  = '/tmp/train_output.log'
RUNS_GLOB = '/content/drive/MyDrive/go2_rl/logs/rsl_rl/*/*'

# Listado ANTES de entrenar. El directorio nuevo sera el de este run, y asi el
# empaquetado no puede confundirse de entrenamiento.
RUNS_BEFORE = set(glob.glob(RUNS_GLOB))
RUN_START   = time.time()
print(f"directorios de log previos: {len(RUNS_BEFORE)}")

# --- deteccion de flags -------------------------------------------------
print("\nleyendo --help para detectar los flags disponibles...")
help_txt = subprocess.run(
    ['python', 'scripts/train.py', TASK, '--help'],
    cwd='/content/unitree_rl_mjlab', env=env,
    capture_output=True, text=True, timeout=900,
).stdout

def pick(*cands):
    for c in cands:
        if c in help_txt:
            return c
    return None

flag_seed = pick('--agent.seed', '--seed', '--env.seed')
flag_save = pick('--agent.save-interval', '--agent.save_interval', '--save-interval')

args = ['python', 'scripts/train.py', TASK, f'--env.scene.num-envs={NUM_ENVS}']

if flag_seed:
    args.append(f'{flag_seed}={SEED}')
    print(f"  semilla: {flag_seed}={SEED}")
else:
    print("  AVISO GRAVE: no hay flag de semilla.")
    print("  Las 3 repeticiones de cada presupuesto serian identicas.")
    for ln in help_txt.split('\n'):
        if 'seed' in ln.lower():
            print('    ', ln.strip())

# Con presupuestos cortos, guardar cada 100 iteraciones puede dejar el ultimo
# checkpoint muy por detras del tiempo realmente gastado.
save_interval = 25 if BUDGET_MIN <= 30 else 50
if flag_save:
    args.append(f'{flag_save}={save_interval}')
    print(f"  save_interval: {save_interval}")
else:
    print("  AVISO: no se puede ajustar save_interval; el checkpoint final")
    print("  podria corresponder a menos tiempo del presupuestado.")

print(f"\ncomando: {' '.join(args)}")
print(f"presupuesto: {BUDGET_MIN} min\n" + "="*60)

proc = subprocess.Popen(args, cwd='/content/unitree_rl_mjlab', env=env,
                        stdout=open(LOG_FILE, 'w', buffering=1),
                        stderr=subprocess.STDOUT)
print(f"arrancado (PID={proc.pid})")

# --- parada automatica --------------------------------------------------
def _watchdog():
    deadline = RUN_START + BUDGET_MIN * 60
    while proc.poll() is None and time.time() < deadline:
        time.sleep(5)
    if proc.poll() is None:
        print(f"\n{'='*60}")
        print(f"PRESUPUESTO AGOTADO ({BUDGET_MIN} min). Parando...")
        proc.send_signal(signal.SIGINT)   # deja que rsl_rl guarde
        time.sleep(30)
        if proc.poll() is None:
            proc.terminate(); time.sleep(10)
        if proc.poll() is None:
            proc.kill()
        print("detenido")

threading.Thread(target=_watchdog, daemon=True).start()

# --- seguimiento en vivo ------------------------------------------------
def _tail():
    with open(LOG_FILE) as f:
        while proc.poll() is None:
            line = f.readline()
            if line:
                print(line, end='', flush=True)
            else:
                time.sleep(0.3)
        for line in f:
            print(line, end='', flush=True)
    rc = proc.wait()
    print(f"\n{'='*60}")
    print(f"terminado (exit={rc}) tras {(time.time()-RUN_START)/60:.1f} min "
          f"de {BUDGET_MIN} presupuestados")

threading.Thread(target=_tail, daemon=True).start()
"""))

# ---------------------------------------------------------------------------
cells.append(md(r"""
## 8. Empaquetar

Ejecutar **cuando la celda anterior haya impreso `terminado`**.

Coge el directorio de log creado por este run (no el mas reciente del Drive,
que podria ser otro entrenamiento), renombra `deploy.yaml` a
`deploy_params.yaml` como espera `tools/import_run.py`, y anade
`train_meta.json` con toda la procedencia.
"""))

cells.append(code(r"""
import glob, shutil, os, time, json, re, subprocess

runs_after = set(glob.glob(RUNS_GLOB))
nuevos = sorted(runs_after - RUNS_BEFORE, key=os.path.getmtime)

if nuevos:
    run_dir = nuevos[-1]
    print(f"directorio de ESTE run: {run_dir}")
else:
    cands = [d for d in runs_after if os.path.getmtime(d) > RUN_START]
    if not cands:
        raise RuntimeError(
            "No se ha creado ningun directorio de log. El entrenamiento fallo "
            "antes de empezar. Revisa /tmp/train_output.log."
        )
    run_dir = sorted(cands, key=os.path.getmtime)[-1]
    print(f"AVISO: sin directorio nuevo; usando el mas reciente: {run_dir}")

onnx = os.path.join(run_dir, 'policy.onnx')
if not os.path.exists(onnx):
    raise RuntimeError(
        f"No hay policy.onnx en {run_dir}.\n"
        f"El presupuesto de {BUDGET_MIN} min no llego al primer save_interval "
        f"({save_interval} iteraciones). Sube el presupuesto o baja el intervalo."
    )

dest = f'/content/drive/MyDrive/go2_rl/exports/run_{TAG}'
if os.path.exists(dest):
    shutil.rmtree(dest)
os.makedirs(dest)

for fname in ('policy.onnx', 'policy.onnx.data'):
    src = os.path.join(run_dir, fname)
    if os.path.exists(src):
        shutil.copy(src, dest); print(f"  {fname}")

# scripts/train.py SOLO vuelca params/env.yaml y params/agent.yaml. NUNCA
# escribe deploy.yaml. El contrato de despliegue describe la TAREA (orden de
# articulaciones, ganancias, action_scale, las 47 observaciones), no el
# entrenamiento, y viene en el propio repositorio. Las politicas del barrido
# comparten tarea, luego comparten contrato: entre ellas solo cambian los pesos.
#
# NO sustituir por env.yaml: tiene otra estructura y el run pareceria valido
# sin serlo.
DEPLOY_YAML = ('/content/unitree_rl_mjlab/deploy/robots/go2/'
               'config/policy/velocity/v0/params/deploy.yaml')
if not os.path.exists(DEPLOY_YAML):
    raise RuntimeError(f"No existe el contrato de la tarea en {DEPLOY_YAML}")
shutil.copy(DEPLOY_YAML, f'{dest}/deploy_params.yaml')
print("  deploy_params.yaml  (contrato de la tarea, desde el repo)")

FSM_YAML = '/content/unitree_rl_mjlab/deploy/robots/go2/config/config.yaml'
if os.path.exists(FSM_YAML):
    shutil.copy(FSM_YAML, f'{dest}/fsm_config.yaml')
    print("  fsm_config.yaml")

for rel, dst in (('params/agent.yaml', 'agent.yaml'),
                 ('params/env.yaml', 'env.yaml')):
    src = os.path.join(run_dir, rel)
    if os.path.exists(src):
        shutil.copy(src, f'{dest}/{dst}'); print(f"  {dst}")

pts = sorted(glob.glob(f'{run_dir}/model_*.pt'),
             key=lambda p: int(re.sub(r'\D', '', os.path.basename(p)) or 0))
if pts:
    shutil.copy(pts[-1], dest); print(f"  {os.path.basename(pts[-1])}")

# --- procedencia --------------------------------------------------------
log_txt = open(LOG_FILE, errors='ignore').read()
its   = re.findall(r'Learning iteration\s+(\d+)', log_txt)
steps = re.findall(r'Total timesteps:\s*([\d\.]+)', log_txt)
fps   = re.findall(r'Total fps:\s*([\d\.]+)', log_txt)

meta = {
    "tag": TAG,
    "seed": SEED,
    "budget_min": BUDGET_MIN,
    "elapsed_min": round((time.time() - RUN_START) / 60, 2),
    "num_envs": NUM_ENVS,
    "task": TASK,
    "gpu": "colab-t4-free",
    "repo": "unitreerobotics/unitree_rl_mjlab",
    "repo_commit": REPO_SHA,
    "versions": VERSIONS,
    "seed_flag": flag_seed,
    "save_interval": save_interval,
    "iteraciones": int(its[-1]) if its else None,
    "timesteps": steps[-1] if steps else None,
    "fps": fps[-1] if fps else None,
    "log_dir": run_dir,
    "deploy_yaml_origen": DEPLOY_YAML,
    "fecha": time.strftime('%Y-%m-%dT%H:%M:%S'),
}
with open(f'{dest}/train_meta.json', 'w') as f:
    json.dump(meta, f, indent=2)
with open(f'{dest}/train_tail.log', 'w') as f:
    f.write(log_txt[-200000:])

print(f"\n{'='*60}")
print(json.dumps(meta, indent=2))

zip_base = f'/content/run_{TAG}'
shutil.make_archive(zip_base, 'zip', dest)
print(f"\nzip: {zip_base}.zip "
      f"({os.path.getsize(zip_base + '.zip')/1024/1024:.1f} MB)")

from google.colab import files
files.download(f'{zip_base}.zip')
"""))

# ---------------------------------------------------------------------------
cells.append(md(r"""
## 9. En el portatil

```bash
distrobox enter go2-humble
go2sim

mkdir -p ~/Downloads/run_TAG
unzip ~/Downloads/run_TAG.zip -d ~/Downloads/run_TAG

python3 tools/import_run.py ~/Downloads/run_TAG \
    --tag TAG --budget-min BUDGET --seed SEED
```

`import_run.py` verifica que el ONNX y el `deploy_params.yaml` cuadran, crea
`experiments/uc01_locomotion/<run_id>/` con su `manifest.json` e imprime los
comandos de DVC y de evaluacion.

Despues, con el simulador arrancado:

```bash
python3 usecases/uc01_locomotion/eval/eval_sim.py \
    --policy experiments/uc01_locomotion/<run_id>/checkpoints/policy.onnx \
    --rollouts 3 --out experiments/uc01_locomotion/<run_id>/
```
"""))

# ---------------------------------------------------------------------------
nb = {
    "cells": cells,
    "metadata": {
        "accelerator": "GPU",
        "colab": {"provenance": [], "gpuType": "T4"},
        "kernelspec": {"display_name": "Python 3", "name": "python3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 0,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(nb, indent=1, ensure_ascii=False))
print(f"escrito: {OUT}")
print(f"{len(cells)} celdas "
      f"({sum(1 for c in cells if c['cell_type'] == 'code')} de codigo)")
