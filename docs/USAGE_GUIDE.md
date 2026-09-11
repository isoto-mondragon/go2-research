# Guía de uso día-a-día — Go2 sim + percepción

Esta guía es la "cheat sheet" para encender el portátil y trabajar. No
explica la instalación (para eso `STUDENT_GUIDE.md`), explica los **comandos
exactos** que necesitas cada día.

---

## 0. Después de encender el PC (cada vez)

### 0.1 Adjuntar la webcam al WSL (usbipd)

En **PowerShell de Windows como administrador** (no normal):
```powershell
usbipd list
# Busca tu webcam (algo tipo "HP HD Camera", "Integrated Camera")
# Apunta su BUSID (1-1, 2-1, etc.)

usbipd attach --wsl --busid 1-1
```

> El `bind` solo se hace **una vez en la vida** del PC (`usbipd bind --busid 1-1`).
> El `attach` hay que hacerlo cada vez que reinicias Windows.

#### Si quieres evitar tener que hacer `attach` cada vez

Opción A — comando en una sola línea con `--auto-attach` (re-adjunta también si desconectas la cámara):
```powershell
usbipd attach --wsl --busid 1-1 --auto-attach
```
Eso queda escuchando indefinidamente, no es ideal para automatizar.

Opción B (recomendada) — automatizar con **Task Scheduler de Windows**:
1. Abre "Programador de tareas" (`taskschd.msc`).
2. Crear tarea (no básica) → pestaña "General":
   - Nombre: `WSL Attach Webcam`
   - "Ejecutar con privilegios más altos" ✓
3. Pestaña "Desencadenadores" → Nuevo → "Al iniciar sesión".
4. Pestaña "Acciones" → Nuevo:
   - Programa: `usbipd.exe` (suele estar en `C:\Program Files\usbipd-win\usbipd.exe`)
   - Argumentos: `attach --wsl --busid 1-1`
5. Aceptar. Reinicia y comprueba.

A partir de ahí, la cámara aparece sola en WSL al iniciar sesión.

### 0.2 Verificar en WSL

```bash
ls /dev/video*
# Esperado: /dev/video0  /dev/video1

# Test rápido
python3 -c "import cv2; cap = cv2.VideoCapture(0, cv2.CAP_V4L2); \
  cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG')); \
  ok, f = cap.read(); print('OK' if ok else 'FAIL', f.shape if ok else '')"
```

Si `OK (480, 640, 3)` → estás listo. Si `FAIL` → mira la sección **Troubleshooting → Cámara congelada**.

---

## 1. Lanzar el simulador (todos los días)

### 1.1 Activar el venv y abrir el simulador

**Terminal A**:
```bash
cd ~/robotics/rl_workspace/unitree_rl_mjlab
source ~/robotics/rl_workspace/.venv_rl/bin/activate

python tools/play_dds.py Unitree-Go2-Flat \
  --checkpoint-file=/mnt/c/Users/isoto/Downloads/model_4100.pt \
  --network=lo
```

Verás:
- `[Go2Simulator] Policy cargada desde ...`
- `[Go2Simulator] Escuchando rt/wirelesscontroller en network=lo`
- `[Go2Simulator] Command clamps: {...}`
- `[Go2Simulator] Abriendo viewer ...`
- Se abre la ventana de MuJoCo con el Go2 quieto de pie.

**Flags útiles** para `play_dds.py`:
- `--checkpoint-file=<path>` (obligatorio): tu `.pt`.
- `--network=lo` (default): interfaz DDS.
- `--no-terminations`: el perro NO se resetea al caerse (útil para debug).
- `--no-debug-cmd`: no imprime el comando recibido (silencia la terminal).
- `--device=cpu` / `--device=cuda:0`: fuerza un device de torch.

### 1.2 Controlar al perro

A partir de aquí, **3 formas** de mover al perro. Usa la que te convenga:

#### A) Teclado (rápido para probar)

**Terminal B**:
```bash
cd ~/robotics/rl_workspace/unitree_rl_mjlab
source ~/robotics/rl_workspace/.venv_rl/bin/activate
python tools/teleop_wireless.py --network=lo --max-lin 1.0 --max-ang 1.0
```

Teclas:
- `w` / `s` → forward / backward (incremental 0.3 por pulsación).
- `a` / `d` → strafe izquierda / derecha.
- `q` / `e` → giro yaw.
- **`Shift+W`/`Shift+S`/`Shift+Q`/`Shift+E`** → valor máximo de golpe.
- `ESPACIO` → para todo.
- `Ctrl+C` → salir.

#### B) Tu propio script Python (programático)

Por ejemplo `mis_movimientos.py`:
```python
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path("~/robotics/rl_workspace/unitree_rl_mjlab").expanduser()))
from tools.go2_controller import Go2Controller

dog = Go2Controller(mode="sim", network="lo")
dog.stand_up()                                # no-op en sim
time.sleep(1)

dog.set_velocity(vx=0.5, vy=0, wz=0)
time.sleep(3)                                 # avanza 3 segundos

dog.set_velocity(vx=0, vy=0, wz=1.0)
time.sleep(2)                                 # gira 2 segundos

dog.set_velocity(vx=0.5, vy=0.3, wz=0)
time.sleep(2)                                 # diagonal

dog.stop()
```

Lánzalo (con el sim de 1.1 ya corriendo) en otra terminal:
```bash
source ~/robotics/rl_workspace/.venv_rl/bin/activate
python mis_movimientos.py
```

#### C) Demo YOLO (percepción + control)

Sigue la sección **2. YOLO** más abajo.

---

## 2. YOLO: percepción + control

### 2.1 Comprobaciones previas

- ✅ Simulador corriendo (sección 1.1).
- ✅ Webcam adjuntada (sección 0.1).
- ✅ `python -c "import cv2; ..."` da `OK`.
- ✅ `ultralytics` instalado: `pip install ultralytics opencv-python`.

### 2.2 Lanzar el demo

**Terminal B** (con el sim de 1.1 corriendo en otra):
```bash
cd ~/robotics/rl_workspace/unitree_rl_mjlab
source ~/robotics/rl_workspace/.venv_rl/bin/activate
python examples/follow_yolo.py
```

Verás:
- `Cargando YOLOv8n...` (10s la primera vez).
- `YOLO listo. target_class_id=0`.
- `Camara: 640x480`.
- `Esperando primer frame procesado por YOLO...`
- `Loop principal a 20Hz. Pulsa 'q' en la ventana para salir.`
- Se abre la ventana `follow_yolo` con el vídeo en vivo, bbox verde si te detecta y `vx`/`wz` arriba.

Detrás de las bambalinas: YOLO corre en un **hilo separado** para que el display no se congele aunque YOLO vaya a 5fps.

### 2.3 Probar el seguimiento

| Acción | Esperado |
|---|---|
| Te alejas de la cámara | Perro avanza (`vx > 0`) |
| Te acercas mucho | Perro retrocede o se para (`vx <= 0`) |
| Te mueves a la derecha del frame | Perro gira a la derecha (`wz < 0`) |
| Te mueves a la izquierda | Perro gira a la izquierda (`wz > 0`) |
| Sales del frame | Perro para |

### 2.4 Ajustes en `examples/follow_yolo.py`

Las constantes al principio del archivo:

| Variable | Qué hace |
|---|---|
| `MODE` | `"sim"` o `"real"` |
| `NETWORK` | `"lo"` para sim, `"enp5s0"` (o tu interfaz) para real |
| `TARGET_CLASS` | clase COCO a seguir: `"person"`, `"bottle"`, `"cup"`, `"cat"`, etc. |
| `CAMERA_INDEX` | índice del `/dev/videoN` (suele ser 0) |
| `MAX_VX`, `MAX_WZ` | velocidades máximas comandadas |
| `TARGET_BBOX_H_PX` | altura "deseada" del bbox. Sube si tu webcam te capta grande |
| `YOLO_IMGSZ` | resolución de inferencia. Baja a 128 si YOLO va muy lento |

### 2.5 Otros tipos de demo

Cambia `TARGET_CLASS` a `"bottle"`, `"cup"`, `"sports ball"`, `"cat"`, etc. (cualquiera de las 80 clases de COCO). Lista completa:
```python
python -c "from ultralytics import YOLO; print(YOLO('yolov8n.pt').names)"
```

---

## 3. Clases encapsuladas (desde tu código)

Tres clases organizan el código por responsabilidad. Para la mayoría de
proyectos solo necesitas `Go2Controller`. Las otras dos están si quieres
indagar/customizar.

### 3.1 `Go2Controller` — la única que necesitas casi siempre

API alta nivel del perro, **misma para sim y real**.

```python
from tools.go2_controller import Go2Controller

dog = Go2Controller(mode="sim", network="lo")
# o:
# dog = Go2Controller(mode="real", network="enp5s0")

dog.set_velocity(vx=0.5, vy=0.0, wz=0.0)   # comando de velocidad (m/s, m/s, rad/s)
dog.stop()                                   # = set_velocity(0, 0, 0)
dog.stand_up()                               # solo afecta a real
dog.sit()                                    # solo afecta a real
```

### 3.2 `Go2Simulator` — encapsula el simulador

Equivalente a `play_dds.py` pero llamable desde Python:
```python
from tools.go2_simulator import Go2Simulator

sim = Go2Simulator(
    checkpoint_file="/mnt/c/Users/isoto/Downloads/model_4100.pt",
    task="Unitree-Go2-Flat",
    network="lo",
    no_terminations=False,   # True: el perro no se resetea al caer
    debug_cmd=True,           # imprime el cmd recibido cada ~0.5s
)
sim.run()  # bloquea hasta cerrar la ventana de MuJoCo
```

Esto es útil si quieres lanzar el sim desde un script de tests, o
configurarlo programáticamente sin pasar por la CLI.

### 3.3 `Go2Policy` — introspectar el modelo entrenado

Útil si quieres saber qué hay dentro de tu `.pt`:
```python
from tools.go2_policy import Go2Policy

pol = Go2Policy(
    checkpoint_file="/mnt/c/Users/isoto/Downloads/model_4100.pt",
    task="Unitree-Go2-Flat",
)
print(pol.summary())
# Imprime obs_dim, action_dim, joint_names, action_scale, etc.

# Inferencia manual (avanzado)
import torch
obs = torch.zeros((1, pol.obs_dim), device=pol.device)
action = pol.predict(obs)
print(action.shape)  # torch.Size([1, 12])
```

---

## 4. Pasar a robot real (cuando lo tengas)

### 4.1 Red

Tu PC en `192.168.123.222/24`. Identifica la interfaz Ethernet:
```bash
ip addr
# Busca algo tipo enp5s0, eno1, eth0
ping 192.168.123.161   # IP típica del Go2
```

### 4.2 Tu código de aplicación cambia 2 líneas

Antes (sim):
```python
dog = Go2Controller(mode="sim", network="lo")
```
Ahora (real):
```python
dog = Go2Controller(mode="real", network="enp5s0")
```

El resto del script funciona idéntico. Sport Mode del robot real ejecuta los `set_velocity`.

### 4.3 Test mínimo seguro (perro suspendido)

```python
import time
from tools.go2_controller import Go2Controller

dog = Go2Controller(mode="real", network="enp5s0")

# 1. Levantarse
dog.stand_up(); time.sleep(3)

# 2. Sentarse
dog.sit(); time.sleep(3)

# 3. Velocidad mínima
dog.stand_up(); time.sleep(2)
dog.set_velocity(vx=0.1, vy=0, wz=0); time.sleep(2)
dog.stop()
```

Si los 3 pasos van bien, ya puedes bajar al suelo y subir velocidades.

> ⚠️ **Primera vez**: SIEMPRE con el perro suspendido en mesa o con arnés. Hasta tener confianza, no en el suelo.

---

## 5. Troubleshooting

### Cámara congelada / "se peta" después de un rato

Causas habituales:
1. **YOLO en CPU es lento** — la ventana parece congelada porque YOLO tarda 200-500ms por frame. El archivo `examples/follow_yolo.py` actual ya tiene YOLO en otro hilo, así que **no debería pasar**. Si aún se congela:
   - Mira el `YOLO: X.X fps` en la esquina superior izquierda de la ventana. Si baja a < 2fps, prueba `YOLO_IMGSZ = 128`.
2. **La cámara perdió la conexión usbipd** — pasa si Windows pasa a suspender, si la USB falla, etc.
   ```bash
   ls /dev/video*    # si NO está -> hay que re-adjuntar
   ```
   Re-adjunta desde Windows (PowerShell admin): `usbipd attach --wsl --busid 1-1`.
3. **Driver de OpenCV bloqueado** — mata el proceso (`Ctrl+C` en la terminal) y reinicia.

### `Permission denied` al abrir `/dev/video0`

Tu usuario no está en el grupo `video`:
```bash
sudo usermod -a -G video $USER
# Cierra y vuelve a abrir la terminal de Ubuntu para que tenga efecto
```

### `play_dds.py` se queja de `Missing from ...`

Olvidaste el task. Comando completo:
```bash
python tools/play_dds.py Unitree-Go2-Flat \
  --checkpoint-file=/ruta/a/model.pt --network=lo
```

### `No module named src.tasks`

Estás ejecutando desde otro directorio. Solución:
```bash
cd ~/robotics/rl_workspace/unitree_rl_mjlab
```

### `No module named unitree_sdk2py`

El SDK Python no está en el venv. Solución:
```bash
source ~/robotics/rl_workspace/.venv_rl/bin/activate
cd ~/robotics/unitree_sdk2_python
pip install -e .
```

### El perro no se mueve / no recibe comandos

1. Mira la terminal de `play_dds.py`. Si ves `[cmd] vx=+X.XX vy=+0.00 wz=+0.00` cambiando cuando pulsas teclas en el teleop → DDS funciona, el problema es la policy (mira el siguiente).
2. Si NO ves cambios en el `[cmd]`:
   - Confirma que las dos terminales usan el **mismo `--network=lo`**.
   - Si reiniciaste alguna, **mata todas y reinicia en orden** (sim primero, luego teleop o tu script).

### El perro gira solo / va hacia atrás solo sin que le mande nada

Si está pasando con `mode="sim"`, suele ser que la policy no es estable
sin comando. Solución: manda `vx=0.1` pequeño constante en lugar de
exactamente `0` — caes en una zona donde la policy está bien entrenada.

---

## 6. Arquitectura de archivos (referencia)

```
~/robotics/rl_workspace/unitree_rl_mjlab/
├── tools/
│   ├── play_dds.py          ← Wrapper CLI de Go2Simulator
│   ├── go2_simulator.py     ← Clase: sim mjlab + DDS + viewer
│   ├── go2_controller.py    ← Clase: API alta para alumnos (USAR ESTA)
│   ├── go2_policy.py        ← Clase: introspeccionar el .pt
│   └── teleop_wireless.py   ← Mando por teclado
├── examples/
│   ├── follow_demo.py       ← Patrón fijo sin percepción
│   └── follow_yolo.py       ← YOLO + webcam + control
├── scripts/
│   ├── train.py             ← Entrenamiento RL en Colab
│   └── play.py              ← Viewer sin DDS (validación)
└── src/                     ← código mjlab/tasks
```

---

## 7. Workflow típico de un día

```
1. PC encendido. Abrir Ubuntu (WSL).
2. (Si no automatizaste) PowerShell admin → usbipd attach --wsl --busid 1-1
3. cd ~/robotics/rl_workspace/unitree_rl_mjlab
4. source ~/robotics/rl_workspace/.venv_rl/bin/activate
5. Terminal A: python tools/play_dds.py Unitree-Go2-Flat \
       --checkpoint-file=/mnt/c/Users/isoto/Downloads/model_4100.pt \
       --network=lo
6. Terminal B (cualquiera de las opciones):
   - Teleop: python tools/teleop_wireless.py --network=lo
   - Tu script: python mi_script.py
   - YOLO demo: python examples/follow_yolo.py
7. Trabajar.
8. Al terminar: Ctrl+C en cada terminal o cerrar la ventana de MuJoCo.
```

Eso es todo. La parte rara (instalar deps, configurar DDS, entrenar policy)
ya está. El día a día es estos 7 pasos.


## Notas del entorno Ubuntu 26.04 + distrobox

- unitree_mujoco: USE_JOYSTICK debe ser 0 en simulate_python/config.py o el hilo de fisica no arranca (el DDS sigue publicando, engañoso).

## Simulacion en Ubuntu 26.04 + distrobox

- `USE_JOYSTICK = 0` en `simulate_python/config.py`, o el hilo de fisica no
  arranca. El DDS sigue publicando estado congelado y parece un fallo de control.
- Un solo `unitree_mujoco` a la vez: `pgrep -fa unitree_mujoco` antes de empezar.
  Dos instancias dan un estado incoherente indistinguible de un fallo de control.
- `VIEWER_DT = 0.05` (20 fps). No tocar `SIMULATE_DT`.
- `run_policy.py --publish-hz 200 --onnx-threads 1` en simulacion.
  Con 500 Hz y onnxruntime multihilo se pierde el 19% de los plazos.
  Para el robot real: 500 Hz, que alli no hay fisica compitiendo.
- Teleop: usar `tools/teleop.py`, que lee el dominio DDS del contrato.
  `src/go2core/comms/teleop_wireless.py` tiene domain 0 cableado y no llega
  a unitree_mujoco (domain 1).
- Levantarse: `--stand-mode direct`. El modo `fsm` es la config del deploy C++
  y sus ganancias rigidas provocan temblor en simulacion.
