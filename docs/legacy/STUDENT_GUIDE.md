# Guía de prácticas — Unitree Go2 + RL (mjlab)

Esta guía te lleva desde un Windows recién instalado hasta hacer correr una
policy RL sobre el Unitree Go2, primero en **simulador** y luego en el
**robot real**. La práctica está pensada para que te centres en la capa de
**aplicación** (percepción, navegación, decisión), no en RL ni control de
bajo nivel.

---

## 0. Conceptos clave (lee antes de tocar nada)

### Dos niveles de control en el Go2

| Nivel | Qué hace | Cuándo usarlo |
|---|---|---|
| **Alto (Sport Mode)** | `set_velocity(vx, vy, wz)`, `stand_up()`, `sit()` | 99% de proyectos: percepción + control. |
| **Bajo (LowCmd/RL)** | Manda 12 torques a los motores. | Solo para investigar nuevas marchas. |

> En el robot real el nivel alto es **Sport Mode**, código de Unitree ya
> entrenado y robustísimo. En el simulador es una **policy de RL** que
> emula Sport Mode. La API que tú usas es la misma en ambos casos.

### Arquitectura del proyecto

```
┌─────────────────────────────────────────────┐
│ TU CÓDIGO (perception + lógica)             │
│  - cámara → YOLO/MediaPipe                  │
│  - calcular (vx, vy, wz)                    │
│  - dog.set_velocity(vx, vy, wz)             │
└──────────────────┬──────────────────────────┘
                   │ misma API
       ┌───────────┴───────────┐
       ▼                       ▼
┌──────────────┐         ┌──────────────┐
│  mode="sim"  │         │ mode="real"  │
│              │         │              │
│ play_dds.py  │         │ SportClient  │
│ (mjlab + RL) │         │ (Go2 firmware│
│              │         │  oficial)    │
└──────────────┘         └──────────────┘
```

---

## 1. Instalación (solo la primera vez)

### 1.1 WSL2 + Ubuntu 22.04

En PowerShell **como administrador**:
```powershell
wsl --install -d Ubuntu-22.04
```
Reinicia. Abre Ubuntu y crea usuario.

### 1.2 Paquetes del sistema

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential cmake git pkg-config python3-pip python3-venv
```

### 1.3 CycloneDDS + Unitree SDK2 (para hablar con sim y robot)

```bash
mkdir -p ~/robotics && cd ~/robotics

# CycloneDDS
git clone https://github.com/eclipse-cyclonedds/cyclonedds.git
cd cyclonedds
mkdir build && cd build
cmake .. -DCMAKE_INSTALL_PREFIX=../install -DBUILD_DDSPERF=ON
cmake --build . --target install -- -j$(nproc)
cd ~/robotics

# Unitree SDK2 (C++)
git clone https://github.com/unitreerobotics/unitree_sdk2.git
cd unitree_sdk2
mkdir build && cd build
sudo cmake .. -DCMAKE_INSTALL_PREFIX=/opt/unitree_robotics
sudo make install
cd ~/robotics

# Unitree SDK2 Python (lo que usaremos para sim y real)
git clone https://github.com/unitreerobotics/unitree_sdk2_python.git
```

### 1.4 Clonar `unitree_rl_mjlab` y crear venv

```bash
mkdir -p ~/robotics/rl_workspace && cd ~/robotics/rl_workspace
git clone https://github.com/unitreerobotics/unitree_rl_mjlab.git
cd unitree_rl_mjlab

# Crear venv
python3 -m venv ~/robotics/rl_workspace/.venv_rl
source ~/robotics/rl_workspace/.venv_rl/bin/activate
pip install -U pip

# Instalar deps con fixes obligatorios
pip install -e .
pip install --force-reinstall \
  "mujoco-warp @ git+https://github.com/google-deepmind/mujoco_warp@40ef9d6acf2584e89cac615fcbf0cb18e05b2c97"
pip install --force-reinstall "warp-lang==1.12.1"

# Instalar unitree_sdk2_python en este venv
cd ~/robotics/unitree_sdk2_python
pip install -e .

# Volver al repo
cd ~/robotics/rl_workspace/unitree_rl_mjlab
```

Verifica:
```bash
python -c "import torch, mujoco, mjlab; print('OK')"
python -c "import unitree_sdk2py; print('SDK Python OK')"
```

---

## 2. Obtener una policy entrenada

Tienes dos opciones:

### Opción A — Entrenar la tuya (Colab, gratis)

Abre `Unitree_RL_MJLAB_clean.ipynb` en Google Colab con runtime T4.
Ejecuta secciones 1–5 (instalación + TensorBoard), después la sección 6
(Modo A — entrenar desde cero). Para cuando `Train/mean_reward > 65`
(~3000–5000 iteraciones, 1.5–2h).

La sección 7 te empaqueta los archivos en
`Drive/MyDrive/go2_rl/exports/go2_velocity_v<fecha>/`. Descárgate
`model_XXXX.pt` (es lo único que necesitas).

### Opción B — Usar una pre-entrenada

Si quieres saltarte el training, descarga del repo de un compañero o
de HuggingFace. Cualquier `.pt` de mjlab para Unitree-Go2-Flat sirve.

---

## 3. Probar en simulador

### 3.1 Lanzar el simulador

**Terminal 1**:
```bash
source ~/robotics/rl_workspace/.venv_rl/bin/activate
cd ~/robotics/rl_workspace/unitree_rl_mjlab

python tools/play_dds.py Unitree-Go2-Flat \
  --checkpoint-file=/ruta/a/tu/model_XXXX.pt \
  --network=lo
```

Verás un viewer de MuJoCo con el Go2 quieto de pie. La terminal
imprime el comando que recibe (`[cmd] vx=+0.00 vy=+0.00 wz=+0.00`).

### 3.2 Controlarlo con el teclado (rápido para probar)

**Terminal 2**:
```bash
source ~/robotics/rl_workspace/.venv_rl/bin/activate
cd ~/robotics/rl_workspace/unitree_rl_mjlab
python tools/teleop_wireless.py --network=lo --max-lin 1.0 --max-ang 1.0
```

Controles:
- `W` / `S` → forward / backward (incremental, 0.3 por pulsación).
- `A` / `D` → strafe lateral.
- `Q` / `E` → giro yaw.
- `Shift+W` / `Shift+S` / `Shift+Q` etc. → valor máximo de golpe.
- `ESPACIO` → stop.
- `Ctrl+C` → salir.

### 3.3 Controlarlo desde tu código

Ejemplo mínimo (`my_first_demo.py`):

```python
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path("~/robotics/rl_workspace/unitree_rl_mjlab").expanduser()))
from tools.go2_controller import Go2Controller

dog = Go2Controller(mode="sim", network="lo")

dog.set_velocity(vx=0.5, vy=0.0, wz=0.0); time.sleep(3)  # avanza
dog.set_velocity(vx=0.0, vy=0.0, wz=0.8); time.sleep(2)  # gira
dog.set_velocity(vx=0.5, vy=0.3, wz=0.0); time.sleep(2)  # diagonal
dog.stop()
```

Lánzalo (con `play_dds.py` ya corriendo en otra terminal):
```bash
python my_first_demo.py
```

---

## 4. Proyectos típicos

### 4.1 Track A: Perception + control (recomendado)

Usa cámara (webcam de tu portátil o cámara on-board del Go2 real), detección
de objetos (YOLO, MediaPipe, color matching), y manda velocidad al perro.

Ver [examples/follow_yolo.py](rl_workspace/unitree_rl_mjlab/examples/follow_yolo.py)
para un esqueleto con YOLOv8.

### 4.2 Track B: Navegación con RL alto nivel

Si quieres RL pero a nivel de planificación (NO de locomoción): entrena
una policy de navegación donde:
- Observaciones: posición del perro, mapa de obstáculos, objetivo.
- Acciones: `(vx, vy, wz)` directamente.
- El "ejecutor" de bajo nivel es `Go2Controller`.

Esto se entrena en minutos, no horas, porque la locomoción no se aprende —
se llama como subrutina.

### 4.3 Track C: Comportamientos predefinidos

Encadenar `set_velocity()` con sleeps para hacer coreografías, patrullas,
o secuencias de movimiento básicas. Sin percepción, solo robótica
demostrativa.

---

## 5. Deploy en el robot real

> ⚠️ Antes de ponerlo en el suelo: **suspende el Go2 con arnés/mesa**.
> Las primeras pruebas siempre con el perro elevado.

### 5.1 Setup físico

1. Enciende el Go2 y espera a que termine el arranque (~30s).
2. El perro debería estar en **Sport Mode** por defecto (de pie tras unos segundos).
3. Conecta tu PC al perro por Ethernet directo o por wifi (si está en la misma red).

### 5.2 Red

Si conectas por Ethernet directo, configura tu interfaz:
- IP: `192.168.123.222`
- Máscara: `255.255.255.0`

Encuentra el nombre de tu interfaz Ethernet:
```bash
ifconfig
# busca algo tipo enp5s0, eno1, eth0...
```

Ping al perro:
```bash
ping 192.168.123.161   # IP típica del Go2
```

### 5.3 Cambiar a modo "real"

Tu código de aplicación cambia **una sola línea**:

```python
# Antes (sim):
dog = Go2Controller(mode="sim", network="lo")

# Ahora (real):
dog = Go2Controller(mode="real", network="enp5s0")  # tu interfaz
```

Y todos los `dog.set_velocity(...)`, `dog.stand_up()`, etc. funcionan igual,
pero ahora hablan con el perro físico.

### 5.4 Test seguro inicial

```python
from tools.go2_controller import Go2Controller
import time

dog = Go2Controller(mode="real", network="enp5s0")

# Test 1: levantar/sentar (sin moverse). Robot suspendido.
dog.stand_up(); time.sleep(3)
dog.sit(); time.sleep(3)

# Test 2: velocidad muy baja. Aún suspendido.
dog.stand_up(); time.sleep(2)
dog.set_velocity(vx=0.1, vy=0, wz=0); time.sleep(2)
dog.stop()

# Si Test 1 y 2 van bien, ya puedes bajar al suelo y probar mayor velocidad.
```

---

## 6. Estructura de archivos del proyecto

```
~/robotics/rl_workspace/unitree_rl_mjlab/
├── tools/
│   ├── play_dds.py          ← simulador (mjlab + RL + DDS)
│   ├── go2_controller.py    ← API alta para tu código
│   └── teleop_wireless.py   ← teleop por teclado para probar
├── examples/
│   ├── follow_demo.py       ← demo patrón sin percepción
│   └── follow_yolo.py       ← demo con webcam + YOLOv8
├── scripts/
│   ├── train.py             ← entrenar tu policy
│   └── play.py              ← visualizar policy (sin DDS)
└── src/                     ← código de mjlab/tasks
```

---

## 7. Resolución de problemas

| Síntoma | Causa | Fix |
|---|---|---|
| `No module named src.tasks` | No estás en el directorio del repo | `cd ~/robotics/rl_workspace/unitree_rl_mjlab` |
| `No module named unitree_sdk2py` | SDK Python no instalado en venv | `cd ~/robotics/unitree_sdk2_python && pip install -e .` |
| `ModuleNotFoundError: torch` | Estás en otro venv | `source ~/robotics/rl_workspace/.venv_rl/bin/activate` |
| `FileNotFoundError: model_XXXX.pt` | Path incorrecto | Usa ruta absoluta. WSL ve Windows en `/mnt/c/Users/...` |
| El simulador no abre ventana | WSL sin display | WSL2 + Windows 11 lo tiene. Si no: `export MUJOCO_GL=egl` |
| Perro no responde al teleop | Olvido cuál terminal está activa | Comprueba `[cmd]` en play_dds: si cambia con tu tecla, va |
| `tile_cholesky / fill_mode` error | Versión de mujoco-warp incorrecta | Reinstala con el commit pinned (paso 1.4) |

---

## 8. Referencias

- mjlab: <https://github.com/mujocolab/mjlab>
- unitree_rl_mjlab: <https://github.com/unitreerobotics/unitree_rl_mjlab>
- Unitree SDK2 (C++): <https://github.com/unitreerobotics/unitree_sdk2>
- Unitree SDK2 Python: <https://github.com/unitreerobotics/unitree_sdk2_python>
- Tutorial Sport Mode: <https://support.unitree.com/home/en/developer>
