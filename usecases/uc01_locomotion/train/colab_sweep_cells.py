"""usecases/uc01_locomotion/train/colab_sweep_cells.py

Celdas de sustitucion para Unitree_RL_MJLAB_clean.ipynb, para convertirlo en
el banco de pruebas del barrido de presupuesto de computo.

NO se ejecuta en local. Es el texto que se copia a Colab, versionado aqui para
que el notebook del barrido sea reproducible y citable.

QUE CAMBIA RESPECTO AL NOTEBOOK ORIGINAL
----------------------------------------
  celda 4  -> se fija el commit del repo. Sin esto, si Unitree actualiza
              unitree_rl_mjlab a mitad del barrido, los 12 runs dejan de ser
              comparables entre si.
  celda 14 -> parada por PRESUPUESTO DE TIEMPO, no manual, y semilla explicita.
              La pregunta del experimento es cuanto rinde una hora de T4, asi
              que el tiempo tiene que ser exacto y automatico.
  celda 17 -> exporta SOLO el run de esta sesion (filtrado por tiempo de
              inicio), renombra deploy.yaml a deploy_params.yaml como espera
              tools/import_run.py, y escribe train_meta.json con la procedencia.

DISENO DEL BARRIDO
------------------
  4 presupuestos x 3 semillas = 12 entrenamientos
  15, 30, 60 y 120 minutos de T4 gratuita; semillas 1, 2 y 3
  total aproximado: 11 h de GPU

  Se eligen 15-120 min en vez de 30-240 porque las sesiones de T4 gratuita se
  cortan con frecuencia por encima de las 2 h. El rango sigue cubriendo un
  orden de magnitud, que es lo que importa para la curva.

COMO USARLO
-----------
  1. Sustituir las celdas indicadas en Colab.
  2. Para cada run: cambiar SEED y BUDGET_MIN en la celda de parametros,
     Runtime > Restart, y ejecutar todo.
  3. Descargar el zip y pasarlo por tools/import_run.py.
"""

# =============================================================================
# CELDA NUEVA - insertar como celda 1, ANTES de todo lo demas
# =============================================================================
CELDA_PARAMETROS = r'''
# ===== PARAMETROS DEL RUN =====
# Lo unico que se toca entre entrenamientos del barrido.

SEED        = 1          # 1, 2 o 3
BUDGET_MIN  = 30         # 15, 30, 60 o 120
NUM_ENVS    = 4096       # constante en todo el barrido
TASK        = "Unitree-Go2-Flat"

# Commit de unitree_rl_mjlab. Fijarlo es lo que hace comparables los 12 runs.
# Para obtenerlo la primera vez:
#   !git -C /content/unitree_rl_mjlab rev-parse HEAD
REPO_COMMIT = "PONER_AQUI_EL_SHA"

TAG = f"t4_{BUDGET_MIN}m_seed{SEED}"
print(f"run: {TAG} | {NUM_ENVS} envs | commit {REPO_COMMIT[:8]}")
'''


# =============================================================================
# CELDA 4 - SUSTITUIR
# =============================================================================
CELDA_4_CLONAR = r'''
%cd /content
!rm -rf unitree_rl_mjlab
!git clone https://github.com/unitreerobotics/unitree_rl_mjlab.git
%cd /content/unitree_rl_mjlab

# Fijar el commit. La primera vez, dejar REPO_COMMIT vacio, ejecutar, y copiar
# el SHA que imprime al final a la celda de parametros.
if REPO_COMMIT and REPO_COMMIT != "PONER_AQUI_EL_SHA":
    !git checkout -q {REPO_COMMIT}
    print(f"repo fijado en {REPO_COMMIT}")
else:
    print("AVISO: repo sin fijar. Copia el SHA de abajo a REPO_COMMIT.")

!git rev-parse HEAD

!curl -LsSf https://astral.sh/uv/install.sh | sh
import os
os.environ['PATH'] = '/root/.local/bin:/usr/local/bin:' + os.environ['PATH']
!uv --version
'''


# =============================================================================
# CELDA 14 (MODO A) - SUSTITUIR
# =============================================================================
CELDA_14_ENTRENAR = r'''
# ===== ENTRENAMIENTO CON PRESUPUESTO DE TIEMPO =====
import subprocess, os, threading, time, signal, json, re

os.environ['WANDB_MODE'] = 'disabled'
os.environ['WANDB_DISABLED'] = 'true'

env = os.environ.copy()
env['PYTHONPATH'] = '/content/unitree_rl_mjlab'
env['WANDB_MODE'] = 'disabled'
env['WANDB_DISABLED'] = 'true'
env['PYTHONHASHSEED'] = str(SEED)

LOG_FILE = '/tmp/train_output.log'
RUN_START = time.time()   # lo usa la celda de exportacion para filtrar

# --- deteccion de flags disponibles -------------------------------------
# Los nombres de los flags dependen de la version de mjlab/tyro. En vez de
# adivinarlos, se leen del --help y solo se pasan los que existen. Si alguno
# no aparece, se avisa: un barrido sin semilla no tiene barras de error.
help_txt = subprocess.run(
    ['python', 'scripts/train.py', TASK, '--help'],
    cwd='/content/unitree_rl_mjlab', env=env,
    capture_output=True, text=True, timeout=300,
).stdout

def pick(*candidatos):
    for c in candidatos:
        if c in help_txt:
            return c
    return None

flag_seed = pick('--agent.seed', '--seed', '--env.seed')
flag_save = pick('--agent.save-interval', '--agent.save_interval', '--save-interval')

args = ['python', 'scripts/train.py', TASK, f'--env.scene.num-envs={NUM_ENVS}']

if flag_seed:
    args.append(f'{flag_seed}={SEED}')
    print(f"semilla: {flag_seed}={SEED}")
else:
    print("AVISO GRAVE: no hay flag de semilla. Las 3 repeticiones seran")
    print("identicas y las barras de error del paper serian falsas.")
    print("Flags con 'seed' en el help:")
    for ln in help_txt.split('\n'):
        if 'seed' in ln.lower():
            print('   ', ln.strip())

# Con presupuestos cortos, guardar cada 100 iteraciones puede dejar el ultimo
# checkpoint muy atrasado respecto al tiempo gastado. Se acorta el intervalo.
save_interval = 25 if BUDGET_MIN <= 30 else 50
if flag_save:
    args.append(f'{flag_save}={save_interval}')
    print(f"save_interval: {save_interval}")
else:
    print("AVISO: no se puede ajustar save_interval; el checkpoint final")
    print("podria corresponder a menos tiempo del presupuestado.")

print(f"\ncomando: {' '.join(args)}")
print(f"presupuesto: {BUDGET_MIN} min\n")

proc = subprocess.Popen(
    args, cwd='/content/unitree_rl_mjlab', env=env,
    stdout=open(LOG_FILE, 'w', buffering=1), stderr=subprocess.STDOUT,
)
print(f"arrancado (PID={proc.pid})")

# --- parada automatica al agotar el presupuesto -------------------------
def _budget_watchdog():
    deadline = RUN_START + BUDGET_MIN * 60
    while proc.poll() is None and time.time() < deadline:
        time.sleep(5)
    if proc.poll() is None:
        elapsed = (time.time() - RUN_START) / 60
        print(f"\n{'='*60}")
        print(f"PRESUPUESTO AGOTADO tras {elapsed:.1f} min. Parando.")
        proc.send_signal(signal.SIGINT)     # para que rsl_rl guarde
        time.sleep(30)
        if proc.poll() is None:
            proc.terminate()
            time.sleep(10)
        if proc.poll() is None:
            proc.kill()
        print("entrenamiento detenido")

threading.Thread(target=_budget_watchdog, daemon=True).start()

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
    total = (time.time() - RUN_START) / 60
    print(f"\n{'='*60}")
    print(f"terminado (exit={rc}) tras {total:.1f} min de {BUDGET_MIN} presupuestados")

threading.Thread(target=_tail, daemon=True).start()
'''


# =============================================================================
# CELDA 17 - SUSTITUIR
# =============================================================================
CELDA_17_EXPORTAR = r'''
# ===== EMPAQUETADO PARA import_run.py =====
import glob, shutil, os, time, json, re, subprocess

# Solo ficheros creados DESPUES del inicio de este run. Sin este filtro, en un
# barrido se coge el ONNX de un entrenamiento anterior con otro presupuesto.
onnx_files = [
    f for f in glob.glob('/content/drive/MyDrive/go2_rl/logs/**/policy.onnx', recursive=True)
    if os.path.getmtime(f) > RUN_START
]
onnx_files.sort(key=os.path.getmtime)

if not onnx_files:
    raise RuntimeError(
        "Ningun policy.onnx posterior al inicio del run.\n"
        "Causas: el presupuesto fue demasiado corto para llegar al primer "
        "save_interval, o el entrenamiento fallo. Revisa /tmp/train_output.log."
    )

latest_onnx = onnx_files[-1]
latest_dir = os.path.dirname(latest_onnx)
print(f"{len(onnx_files)} ONNX de este run. Usando: {latest_onnx}")

dest = f'/content/drive/MyDrive/go2_rl/exports/run_{TAG}'
if os.path.exists(dest):
    shutil.rmtree(dest)
os.makedirs(dest)

for fname in ('policy.onnx', 'policy.onnx.data'):
    src = os.path.join(latest_dir, fname)
    if os.path.exists(src):
        shutil.copy(src, dest)
        print(f"  {fname}")

# import_run.py espera exactamente este nombre.
deploy_yaml = os.path.join(latest_dir, 'params', 'deploy.yaml')
if os.path.exists(deploy_yaml):
    shutil.copy(deploy_yaml, f'{dest}/deploy_params.yaml')
    print("  deploy_params.yaml  (renombrado desde deploy.yaml)")
else:
    raise RuntimeError(
        "No hay params/deploy.yaml. Sin el, el run NO es desplegable: no se "
        "sabe el orden de articulaciones ni el action_scale."
    )

for src_rel, dst in (('params/agent.yaml', 'agent.yaml'),
                     ('params/env.yaml', 'env.yaml')):
    src = os.path.join(latest_dir, src_rel)
    if os.path.exists(src):
        shutil.copy(src, f'{dest}/{dst}')
        print(f"  {dst}")

pts = sorted(glob.glob(f'{latest_dir}/model_*.pt'),
             key=lambda p: int(re.sub(r'\D', '', os.path.basename(p)) or 0))
if pts:
    shutil.copy(pts[-1], dest)
    print(f"  {os.path.basename(pts[-1])}")

# --- metadatos de procedencia ------------------------------------------
log_txt = open('/tmp/train_output.log', errors='ignore').read()
its = re.findall(r'Learning iteration\s+(\d+)', log_txt)
steps = re.findall(r'Total timesteps:\s*([\d\.]+)', log_txt)
sha = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd='/content/unitree_rl_mjlab',
                     capture_output=True, text=True).stdout.strip()

meta = {
    "tag": TAG,
    "seed": SEED,
    "budget_min": BUDGET_MIN,
    "elapsed_min": round((time.time() - RUN_START) / 60, 2),
    "num_envs": NUM_ENVS,
    "task": TASK,
    "gpu": "colab-t4-free",
    "repo": "unitreerobotics/unitree_rl_mjlab",
    "repo_commit": sha,
    "iteraciones": int(its[-1]) if its else None,
    "timesteps": steps[-1] if steps else None,
    "save_interval": save_interval,
    "checkpoint_onnx": os.path.basename(latest_onnx),
    "log_dir": latest_dir,
}
with open(f'{dest}/train_meta.json', 'w') as f:
    json.dump(meta, f, indent=2)

# Cola del log, por si hace falta depurar despues
with open(f'{dest}/train_tail.log', 'w') as f:
    f.write(log_txt[-200000:])

print(f"\n{'='*60}")
print(json.dumps(meta, indent=2))

zip_path = f'/content/run_{TAG}'
shutil.make_archive(zip_path, 'zip', dest)
print(f"\nzip: {zip_path}.zip")

from google.colab import files
files.download(f'{zip_path}.zip')

print("\nEn el portatil:")
print(f"  unzip ~/Downloads/run_{TAG}.zip -d ~/Downloads/run_{TAG}")
print(f"  python3 tools/import_run.py ~/Downloads/run_{TAG} \\")
print(f"      --tag {TAG} --budget-min {BUDGET_MIN} --seed {SEED}")
'''


if __name__ == "__main__":
    print(__doc__)
    for nombre, celda in [
        ("CELDA NUEVA (parametros, insertar como celda 1)", CELDA_PARAMETROS),
        ("CELDA 4 (clonar, sustituir)", CELDA_4_CLONAR),
        ("CELDA 14 (entrenar, sustituir)", CELDA_14_ENTRENAR),
        ("CELDA 17 (exportar, sustituir)", CELDA_17_EXPORTAR),
    ]:
        print("\n" + "=" * 78)
        print(nombre)
        print("=" * 78)
        print(celda)
