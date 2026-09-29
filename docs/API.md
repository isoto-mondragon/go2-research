# Chuleta de la API

Para cada cosa que puedes hacer, la línea exacta. Sin teoría.

> **Si solo quieres hacer un caso de uso, no leas esto:** copia
> [`usecases/uc00_plantilla`](../usecases/uc00_plantilla/LEEME.md) y abre `mi_caso.py`.
> Este documento es para entender cómo funciona por dentro.

Todo se ejecuta **dentro de la caja** (`./go2 dev shell`). Al principio de tu
script:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))   # ajusta el número a tu profundidad
from go2core import paths
from go2core.control import contract as ct
```

---

## 1. Leer el estado del robot

**Cuándo:** siempre que quieras saber cómo está el robot sin moverlo. Se lee de
`rt/lowstate`, con un suscriptor que **no publica nada** (es seguro junto a
Sport Mode).

```python
from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_
ChannelFactoryInitialize(domain, iface)          # UNA sola vez por proceso
ultimo = {}
ChannelSubscriber("rt/lowstate", LowState_).Init(lambda m: ultimo.update(m=m), 10)
# espera a que llegue el primero: while "m" not in ultimo: time.sleep(0.02)
m = ultimo["m"]
```

La clase `Telemetria` de `uc00_plantilla/deploy/main.py` (solo para copiarla, no para editarla) ya envuelve esto con
un método por lectura; cópiala.

Una vez tienes `m`:

| qué | línea | sim | real |
|---|---|:-:|:-:|
| posición de articulación (rad), orden **motor** | `m.motor_state[i].q` | sí | sí |
| velocidad de articulación (rad/s) | `m.motor_state[i].dq` | sí | sí |
| par estimado (Nm) | `m.motor_state[i].tau_est` | sí | sí |
| cuaternión del tronco (w,x,y,z) | `m.imu_state.quaternion` | sí | sí |
| giroscopio (rad/s) | `m.imu_state.gyroscope` | sí | sí |
| acelerómetro (m/s²) | `m.imu_state.accelerometer` | sí | sí |
| temperatura de motor (°C) | `m.motor_state[i].temperature` | **0** | sí |
| fuerza en los pies (4) | `m.foot_force` | **0** | sí |
| batería, carga (%) | `m.bms_state.soc` | **0** | sí |
| batería, voltaje y corriente | `m.power_v`, `m.power_a` | **0** | sí |

`i` va de 0 a 11 en orden motor (ver [sección 3](#3-el-contrato)). En
simulación no hay `bms_state`, `foot_force` ni temperatura: salen a cero, no es
un fallo. No decidas nada con ellos en sim.

**Inclinación y altura** no vienen en `lowstate`; se derivan:

```python
import math
_, x, y, _ = m.imu_state.quaternion
inclinacion = math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * (x * x + y * y))))   # rad; 0 = plano
q = [m.motor_state[i].q for i in range(12)]
muslo, rodilla = q[1::3], q[2::3]     # los 4 muslos y las 4 rodillas
altura = sum(0.213 * math.cos(a) + 0.213 * math.cos(a + b) for a, b in zip(muslo, rodilla)) / 4   # ~0.3 de pie, ~0.1 tumbado
```

`altura` es un **indicador** (extensión media de las patas), no metros reales:
en `lowstate` no hay odometría. Con `LowLevel` ya lo tienes hecho:
`ll.tilt_rad()`, `ll.height_proxy()`, `ll.joint_q()`, `ll.joint_dq()`,
`ll.joint_tau()`, `ll.gyro()`, `ll.quaternion()`, `ll.projected_gravity()`.
Pero `LowLevel.start()` **publica** LowCmd; no lo uses solo para leer.

**Posición real del tronco** (odometría): topic `rt/sportmodestate`, mensaje
`SportModeState_`, campo `.position`. Solo existe con Sport Mode activo; en
simulación puede no estar. `uc03_energy/eval/measure_cot.py` (`VerdadTerreno`) lo
trata como opcional.

---

## 2. Mover el robot

**Hay dos niveles y son EXCLUYENTES.** Nunca uses los dos a la vez: dos
controladores peleando por los mismos motores tumban al robot.

| nivel | clase | cuándo | robot real | simulación |
|---|---|---|:-:|:-:|
| alto (velocidades) | `SportClient` | navegación, seguimiento, medir consumo | sí | **no existe** |
| bajo (articulaciones) | `LowLevel` | tu propia política RL | sí | sí |

`unitree_mujoco` no emula Sport Mode: **en simulación la única forma de mover
el robot es la política RL** (`usecases/uc01_locomotion/deploy/run_policy.py --teleop`),
y tu script solo publica velocidades en `rt/wirelesscontroller`.

### Robot real, alto nivel

**Cuándo:** casi siempre. Sport Mode camina por ti.

```python
from unitree_sdk2py.go2.sport.sport_client import SportClient
ChannelFactoryInitialize(domain, iface)          # UNA sola vez
sport = SportClient(); sport.SetTimeout(10.0); sport.Init()
sport.StandUp(); time.sleep(3); sport.BalanceStand(); time.sleep(2)
sport.Move(0.3, 0.0, 0.0)                        # vx m/s, vy m/s, wz rad/s; repítelo ~20 Hz
sport.StopMove()                                 # SIEMPRE al terminar (try/finally)
```

Otros: `sport.Sit()`, `sport.StandDown()`, `sport.Damp()` (amortigua).
**Sport Mode ignora las órdenes por debajo de unos 0.2 m/s**: el robot se queda
quieto o va a tirones. No es un fallo; sube la orden al mínimo o pon cero.

### Simulación, velocidades

**Cuándo:** para probar tu lógica antes del robot. Necesita el simulador y
`run_policy.py --mode sim --teleop` arrancados.

```python
from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelPublisher
from unitree_sdk2py.idl.unitree_go.msg.dds_ import WirelessController_
ChannelFactoryInitialize(1, "lo")                # dominio 1 en sim (dds.sim del contrato)
pub = ChannelPublisher("rt/wirelesscontroller", WirelessController_); pub.Init()
msg = WirelessController_(lx=0.0, ly=0.0, rx=0.0, ry=0.0, keys=0)
msg.ly, msg.lx, msg.rx = vx, vy, wz              # ly = vx, lx = vy, rx = wz
pub.Write(msg)
```

Son `SalidaSimulador` y `SalidaRobot` de uc04 (y de la plantilla): cópialas en
vez de reescribir esto.

> **Sobre `Go2Controller` en el robot real.** Comprobado con el robot: usar `Go2Controller` en uc04 no movía el robot, y llamar a `SportClient` directamente sí. La causa probable es que falta `BalanceStand()` en la secuencia de arranque: `SportClient` necesita `StandUp()` → `BalanceStand()` antes de que `Move()` tenga efecto. Por eso los ejemplos usan `SportClient` directamente, con la secuencia completa. **PENDIENTE** de verificar con el robot si `Go2Controller` funciona añadiendo `BalanceStand()`. (En el código, `Go2Controller` en `mode="real"` sí llama a `SportClient`; solo `mode="sim"` publica en `rt/wirelesscontroller`.) Además, su `domain_id` por
> defecto es 0 y el de la simulación es 1: pásale el del contrato.

```python
from go2core.control.go2_controller import Go2Controller
dog = Go2Controller(mode="sim", network="lo", domain_id=1)   # simulador; en real, ver la nota de arriba
dog.set_velocity(vx=0.3, vy=0.0, wz=0.0)                     # + adelante, + izquierda, + giro izq
dog.stop()
```

### Bajo nivel: tu propia política

**Cuándo:** entrenas una política RL y la despliegas. Todos los vectores de 12
que entran y salen son en **orden motor**.

```python
from go2core.control.lowlevel import LowLevel, SafetyTrip
c = ct.load_contract(paths.CONTRACT)
with LowLevel(c, mode="sim") as ll:                          # start() al entrar, stop() al salir
    kp, kd = ct.policy_gains_motor(c)
    ref = ct.policy_defaults_motor(c)
    ll.set_command_clamped(objetivo_motor, kp, kd, ref)      # recorta a ±q_delta_max de ref
    ll.check_safety()                                        # lanza SafetyTrip; llámalo cada paso
```

`ll.set_command(q, kp, kd)` es lo mismo sin recorte. `ll.go_passive()` amortigua.
El hilo interno reemite el último objetivo a 500 Hz; tú puedes ir a 50 Hz.
`LowLevel` **nunca** junto a `SportClient` en el mismo robot.

---

## 3. El contrato

**Qué es:** `usecases/uc01_locomotion/configs/robot_go2.yaml` es la única
fuente de poses, ganancias, escalado de acciones, límites de seguridad,
velocidades máximas (`commands`) y redes DDS (`dds.sim` / `dds.real`).
No copies esos números a tu código.

```python
c = ct.load_contract(paths.CONTRACT)      # valida el fichero; ContractError si no cuadra
dds = c["dds"][paths.mode()]              # {"domain_id": ..., "interface": ...}; GO2_IFACE ya aplicada
lim = c["commands"]                       # vx_range, vy_range, wz_range
tilt = c["safety"]["max_tilt_rad"]
print(ct.describe(c))                     # resumen legible, útil para el manifest
```

**Dos ordenaciones de articulaciones. Es la trampa más cara del proyecto.**

| orden | patas | quién lo usa |
|---|---|---|
| **motor** (firmware Unitree) | FR, FL, RR, RL | `lowstate`, `LowCmd`, `LowLevel`, `fsm` |
| **política** (mjlab) | FL, FR, RL, RR | la red neuronal (obs y acciones) |

Cada pata son 3 articulaciones (hip, thigh, calf). Convierte **siempre** con el
contrato, nunca a mano:

```python
q_pol = ct.motor_to_policy(ll.joint_q(), c)          # motor -> política
q_mot = ct.policy_to_motor(accion_pol, c)            # política -> motor
q0 = ct.policy_defaults_motor(c)                     # pose por defecto, ya en orden motor
kp, kd = ct.policy_gains_motor(c)                    # ganancias, ya en orden motor
```

Mezclar órdenes no da error: da un robot que se retuerce.

---

## 4. Rutas

**Cuándo:** siempre. Nada de `/home/ibon/...`: `go2core.paths` lo deduce del
entorno y funciona igual en el contenedor y en un clon cualquiera.

```python
from go2core import paths
paths.ROOT, paths.EXPERIMENTS, paths.CONTRACT     # raíz del repo, experiments/, contrato
paths.mode()                                      # "sim" | "real"  (GO2_MODE)
paths.iface(default), paths.domain(default)       # GO2_IFACE / GO2_DOMAIN mandan sobre el contrato
paths.UNITREE_MUJOCO, paths.SIM_DIR               # dependencias externas (GO2_DEPS)
print(paths.describe())                           # diagnóstico; también: python3 src/go2core/paths.py
```

---

## 5. Percepción

### Cámara del robot

**Cuándo:** cualquier cosa que necesite imagen. Llega **por red** con
`VideoClient`, no por `/dev/video`: 1920×1080 a unos 23.9 fps con 11 ms de
latencia (medido). Está a ~30 cm del suelo y es ojo de pez.

```python
sys.path.insert(0, str(paths.TOOLS))
from robot_camera import CamaraRobot
cam = CamaraRobot(iface, domain)          # init_dds=False si ya llamaste a ChannelFactoryInitialize
imagen = cam.leer()                       # ndarray BGR, o None si la petición falla
print(cam.fps, cam.resumen())             # tasa y latencia medidas
```

Solo en el robot real. En simulación no hay cámara del robot.

### Detección de personas

**Cuándo:** seguir, contar o vigilar personas. YOLO clase `person` (no caras:
la cámara está baja y ve piernas y torso). Devuelve posición lateral y tamaño
aparente ya suavizados.

```python
sys.path.insert(0, str(paths.USECASES / "uc04_person_following"))
from perception.detector import DetectorPersonas
det = DetectorPersonas(fuente="robot", iface=iface, domain=domain, init_dds=False)
imagen, d = det.leer()                    # d.visible, d.lateral (-1..+1), d.tamano (0..1), d.confianza
if d.visible: print(d.lateral, d.tamano)
det.cerrar()                              # al terminar
```

`fuente="webcam"` (por defecto) usa `/dev/video<camara>`. Con la cámara del
robot el tamaño aparente cambia poco con la distancia (0.85 a 1 m, 0.65 a 3 m):
calibra tu consigna con eso, ver `uc04/configs/following.yaml`.

---

## 6. Registrar experimentos

**Regla:** todo experimento necesita `manifest.json` con el sha de git, o no es
trazable. Y todo script que mueva el robot necesita `--dry-run`.

```python
from go2core.logging.run import create_run, git_sha, git_dirty
run_dir = create_run("uc05_mi_caso", "mi_etiqueta", config={"params": cfg})
# -> experiments/uc05_mi_caso/<fecha>_<sha>_mi_etiqueta/manifest.json
(run_dir / "metrics.csv").write_text(csv_texto)     # tus resultados, en la misma carpeta
```

`create_run` escribe el sha completo y si había cambios sin commitear
(`git.dirty`), y avisa: un run con `dirty: true` **no es reproducible**. Haz
commit antes de medir. Para anotar resultados después, mira
`usecases/uc00_plantilla/eval/measure.py`.
