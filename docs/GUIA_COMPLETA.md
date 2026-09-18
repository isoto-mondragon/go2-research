# Guía completa

Para quien vaya a desarrollar sobre esta infraestructura. Si solo quieres
arrancar el simulador y mover el perro, con [`QUICKSTART.md`](QUICKSTART.md)
tienes bastante.

Grupo DANZ, Escuela Politécnica Superior, Mondragon Unibertsitatea.

---

## 1. Qué es esto

Una infraestructura de investigación sobre el Unitree Go2 EDU que permite:

- Simular el robot y controlarlo por DDS, igual que al robot físico
- Desplegar políticas de control entrenadas (formato ONNX)
- Conectar con el robot real por Ethernet
- Evaluar comportamientos con un protocolo reproducible
- Registrar experimentos de forma trazable y citable

El principio de diseño: **el mismo código sirve para simulación y para el robot
real**. Lo único que cambia es una variable de entorno.

---

## 2. Arquitectura

### Capas

```
  CASOS DE USO        usecases/uc01_locomotion, uc02_room_exit, ...
       |
  NÚCLEO              src/go2core/
       |                control/   contrato, LowCmd, seguridad, Sport Mode
       |                comms/     teleoperación
       |                perception/ YOLO
       |                sim/       entornos
       |
  COMUNICACIÓN        CycloneDDS 0.10.2 (la versión que usa el robot)
       |
  DESTINO             unitree_mujoco   o   Go2 físico por Ethernet
```

### Simulación y robot: la misma cadena

```
  tools/teleop.py  --rt/wirelesscontroller-->  run_policy.py
                                                    |
                                             ONNX + seguridad
                                                    |
                                              rt/lowcmd
                                                    |
                                 unitree_mujoco   o   Go2 físico
```

Lo que distingue un destino del otro:

| | simulación | robot real |
|---|---|---|
| `GO2_MODE` | `sim` | `real` |
| domain DDS | 1 | 0 |
| interfaz | `lo` | Ethernet (`GO2_IFACE`) |
| `publish_hz` | 200 | 500 |
| `watchdog_ms` | 300 | 100 |

### Dos niveles de control, excluyentes

**Sport Mode (alto nivel).** El controlador de locomoción de fábrica. Le mandas
velocidades y camina. Robusto, no hay que entrenar nada. Es lo adecuado para
casi todos los casos de uso: navegación, percepción, medición energética.

```python
from go2core.control.go2_controller import Go2Controller
dog = Go2Controller(mode="real", network="enp3s0")
dog.stand_up()
dog.set_velocity(vx=0.3, vy=0.0, wz=0.0)
```

**LowCmd (bajo nivel).** Control articular directo: posición, ganancias y par
por motor. Necesario para desplegar políticas RL propias.

```bash
python3 usecases/uc01_locomotion/deploy/run_policy.py --mode real --iface enp3s0
```

**No se pueden usar los dos a la vez.** Si publicas `LowCmd` con Sport Mode
activo, dos controladores pelean por los mismos motores y el robot puede dar
una patada. Antes de bajar a `LowCmd` hay que liberar el modo con
`MotionSwitcherClient.ReleaseMode()`. Está en [`SAFETY.md`](SAFETY.md).

---

## 3. Los tres perfiles

| perfil | para quién | red | GUI | robot real |
|---|---|---|---|---|
| `sim` | alumnos, cualquier SO | interna | navegador, 6080 | no |
| `real` | robot físico | host | ninguna | **solo Linux** |
| `dev` | desarrollo en Linux | host | X11 nativo | sí |

```bash
docker compose --profile sim  up                  # simulador
docker compose --profile sim  exec shell bash     # terminal
docker compose --profile real run --rm real       # robot
docker compose --profile dev  run --rm dev        # desarrollo
```

### Por qué el perfil `sim` levanta dos contenedores

`sim` corre el simulador y `shell` da la terminal. `shell` usa
`network_mode: "service:sim"` para compartir el loopback del primero, que es
por donde va el DDS de la simulación.

Dos contenedores independientes **no se verían**: `lo` no se comparte entre
contenedores. Es la razón de este reparto y está validado: 2003 mensajes de
`rt/lowstate` recibidos en 10 segundos desde `shell`.

### Por qué el robot real solo funciona desde Linux

DDS por Ethernet necesita `network_mode: host`, que en Docker Desktop de
Windows y macOS no funciona de verdad. No es una limitación de este proyecto,
es del transporte. Los alumnos usan el simulador desde cualquier sistema; quien
conecte el robot lo hace desde Linux.

---

## 4. Estructura del repositorio

```
go2-research/
├── docker/                  Dockerfile, entrypoint, escena plana
├── docker-compose.yml       los tres perfiles
├── env/                     scripts de red y arranque manual
├── src/go2core/             núcleo compartido
│   ├── paths.py             rutas y entorno: nada cableado
│   └── control/
│       ├── contract.py      carga y validación del contrato
│       ├── lowlevel.py      LowCmd con CRC, watchdog y límites
│       └── go2_controller.py  API de alto nivel (Sport Mode)
├── usecases/
│   └── uc01_locomotion/
│       ├── configs/         contrato sim2real, escena plana
│       ├── train/           entorno fijado, notebook de Colab
│       ├── deploy/          run_policy.py
│       └── eval/            eval_sim.py
├── experiments/             runs con manifest.json; pesos en DVC
├── results/tables/          tablas de resultados
├── tools/                   diagnóstico, teleop, importación de runs
└── docs/                    esta guía y el resto
```

### Variables de entorno

Todas opcionales: sin ellas el proyecto deduce valores razonables.

| variable | para qué |
|---|---|
| `GO2_ROOT` | raíz del repositorio (`/workspace` en el contenedor) |
| `GO2_DEPS` | dependencias de Unitree (`/opt/go2`) |
| `GO2_MODE` | `sim` o `real` |
| `GO2_IFACE` | interfaz de red; **manda sobre el contrato** |
| `GO2_DOMAIN` | domain id DDS |
| `GO2_GUI` | `novnc`, `x11` o `none` |

Comprobar cómo se han resuelto:

```bash
python3 -m go2core.paths
```

---

## 5. El contrato sim2real

`usecases/uc01_locomotion/configs/robot_go2.yaml` es el **único sitio** donde
viven las constantes de control: poses, ganancias, escalado de acciones, orden
de articulaciones y composición de observaciones.

Si estos valores se duplican en dos ficheros, tarde o temprano divergen y el
despliegue falla por una razón que no es el algoritmo.

### Dos avisos que ahorran días

**Hay dos ordenaciones de articulaciones.**

```
  ORDEN MOTOR    (firmware Unitree) : FR, FL, RR, RL
  ORDEN POLÍTICA (mjlab)            : FL, FR, RL, RR
```

Cada bloque del contrato declara el suyo. La conversión se hace **solo** con
`go2core.control.contract`, nunca a mano. Un error aquí no lanza excepción, no
se ve en simulación propia, y en el robot real produce una marcha inestable que
parece un problema de ganancias.

**Hay dos poses de referencia y no son la misma.**

```
  fsm.poses.stand          = [0, 0.8, -1.5]      objetivo del FSM
  policy.default_joint_pos = [±0.1, 0.9, -1.8]   offset de la red
```

Difieren 0.3 rad en la rodilla. Usar la del FSM como offset de la política da
una marcha agachada e inestable.

---

## 6. Añadir un caso de uso

```bash
./env/init_repo.sh --add-usecase uc05_mi_caso
```

Crea la estructura: `configs/`, `train/`, `deploy/`, `eval/`, `notebooks/` y un
`README.md` con la plantilla de pregunta de investigación, hipótesis y estado.

Reglas del repositorio:

1. Ningún parámetro de control se cablea: todo en `usecases/*/configs/`
2. Un experimento sin `manifest.json` no existe
3. Las figuras se generan con un comando, nunca se editan a mano
4. Pesos y rosbags por DVC, nunca por git
5. Antes de tocar el robot, `docs/SAFETY.md`

### Caso de uso con Sport Mode (lo habitual)

Para navegación, percepción o medición energética **no hace falta entrenar
nada**. El robot ya camina. Tu código manda velocidades y lee sensores:

```python
from go2core.control.go2_controller import Go2Controller
from go2core.control.lowlevel import LowLevel
from go2core.control import contract as ct

c = ct.load_contract("usecases/uc01_locomotion/configs/robot_go2.yaml")
dog = Go2Controller(mode="real", network="enp3s0")   # comandos
ll = LowLevel(c, mode="real"); ll.start()            # telemetría

dog.set_velocity(vx=0.3)
print(ll.joint_tau(), ll.tilt_rad())
```

`lowstate` sigue publicando con Sport Mode activo, así que tienes par por motor,
temperatura, fuerza en los pies y batería mientras el robot camina solo.

---

## 7. Evaluación

`eval_sim.py` ejecuta una secuencia fija de comandos y mide seguimiento de
velocidad, estabilidad, coste de transporte y **calidad de la marcha**.

```bash
python3 usecases/uc01_locomotion/eval/eval_sim.py \
    --policy experiments/uc01_locomotion/<run_id>/checkpoints/policy.onnx \
    --rollouts 3 --settle-s 2 \
    --out experiments/uc01_locomotion/<run_id>/
```

### Por qué mide la marcha y no solo la velocidad

El seguimiento de velocidad por sí solo **no mide lo que parece**. Una política
que desliza el cuerpo con las patas rígidas puntúa bien, gasta poca energía y no
se cae. En el robot real se caería o destrozaría los pies.

El discriminador es la desviación típica de la altura del tronco, calculada
desde los ángulos articulares: si el robot da pasos, oscila. Umbrales
calibrados con tres políticas reales:

```
  caminan    h_sd 0.006 a 0.010
  no camina  h_sd 0.0005 a 0.0016
  frontera   0.004
```

El evaluador emite un veredicto por política. Una que no camina queda
registrada como tal en lugar de aportar una fila engañosa a las tablas.

### Sesgos corregidos, por si reaparecen

1. Columna de error leída como medida. Ahora imprime comando, medido y
   seguimiento en %, sin columna de error.
2. Coste de transporte con velocidad comandada en vez de medida.
3. Velocidad por diferencias finitas, frágil. Ahora desplazamiento neto.
4. Transitorio de aceleración: `--settle-s 2` descarta los 2 s iniciales de
   cada segmento.

---

## 8. Entrenamiento

Solo si necesitas una política propia. Para la mayoría de casos de uso, Sport
Mode es suficiente.

Se entrena en **Google Colab** con T4 gratuita, con el notebook
`usecases/uc01_locomotion/notebooks/Unitree_RL_MJLAB_sweep.ipynb`.

**El entorno está fijado y no se toca**: `unitree_rl_mjlab @ 1425b15f`,
`mjlab 1.2.0`, `mujoco 3.7.0`, `mujoco-warp 3.5.0`, `warp-lang 1.12.1`. El
porqué de cada versión está en `usecases/uc01_locomotion/train/ENTORNO_FIJADO.md`,
y no es capricho: con resolución libre, la instalación no arranca.

Importar un entrenamiento al repositorio:

```bash
python3 tools/import_run.py ~/Descargas/run_TAG --tag TAG --budget-min 30 --seed 1
```

Verifica que el ONNX y el `deploy_params.yaml` son coherentes antes de aceptarlo.

### Resultado establecido

Cinco minutos de T4 no bastan para aprender a caminar (n=3, las tres semillas
fallan igual). Quince sí. Entre 15 minutos y 2 horas el rendimiento no se
distingue con los datos actuales. Detalle en
`results/tables/sweep_progress.md`.

---

## 9. Robot real

### Antes de nada

Lee [`SAFETY.md`](SAFETY.md). No es burocracia: en un grupo de investigación ese
documento vale tanto como el código.

Resumen: radio de 2 m libre, batería >50%, mando físico **en la mano**, app
móvil cerrada, robot tumbado y en damping antes de cualquier comando.

### Conexión

En el **anfitrión**, no en el contenedor:

```bash
./env/go2_net.sh detect          # qué interfaz tiene el cable
./env/go2_net.sh create enp3s0   # perfil con IP 192.168.123.222
./env/go2_net.sh up
./env/go2_net.sh probe           # cuatro comprobaciones
```

Luego, con la interfaz en `.env`:

```bash
docker compose --profile real run --rm real
```

### Primeros pasos, en orden

```bash
# 1. Lectura, no envía nada
python3 tools/dds_smoketest.py --mode real --iface enp3s0 --duration 30

# 2. Un solo publicador (detecta la app móvil conectada)
#    ver el test de continuidad en docs/USAGE_GUIDE.md

# 3. Alto nivel: el robot camina solo
python3 -c "
from go2core.control.go2_controller import Go2Controller
dog = Go2Controller(mode='real', network='enp3s0')
dog.stand_up()
"

# 4. Bajo nivel: SOLO tras liberar Sport Mode y con el robot suspendido
python3 tools/check_write_path.py --real-robot-i-have-read-safety \
        --iface enp3s0 --joint 1 --kp 5 --offset 0.1
```

---

## 10. Limitaciones conocidas

**Robot real solo desde Linux.** Explicado en la sección 3.

**El visor va lento.** OpenGL por software sobre VNC. Afecta al zoom y al giro
de cámara, **no** a la física ni al control. Medido: el bucle de control usa el
7% de su plazo de 20 ms.

**En simulación no hay telemetría de sensores.** `unitree_mujoco` no emula
temperatura, `foot_force` ni batería: salen a cero. Con el robot real sí vienen.

**`rt/lowstate` va a 200 Hz en simulación**, no a 500 como el robot real.

**Un solo simulador a la vez.** Dos instancias producen un estado incoherente
indistinguible de un fallo de control. Comprobar con `pgrep -fa unitree_mujoco`.

**`go2_policy.py` y `go2_simulator.py`** pertenecen al camino de entrenamiento y
dependen de mjlab, que no está en la imagen. No se usan en despliegue.

---

## 11. Resolución de problemas

| síntoma | causa probable |
|---|---|
| `ModuleNotFoundError` de numpy o torch | estás en el anfitrión, no en el contenedor |
| El simulador publica pero el robot no se mueve | `USE_JOYSTICK` distinto de 0: el hilo de física no arranca |
| El teleop no llega | dominio DDS distinto entre publicador y suscriptor |
| Muchos pasos fuera de plazo | baja `--publish-hz` o sube `VIEWER_DT` |
| Estado incoherente, saltos imposibles | dos simuladores a la vez |
| El robot se abre de patas al levantarse | rampa demasiado lenta; usa `--stand-mode direct` |
| `permission denied ... docker.sock` | falta reiniciar tras `usermod -aG docker` |
| `build` termina al instante | falta `--profile sim` |

Herramientas de diagnóstico:

```bash
python3 -m go2core.paths              # rutas y entorno
python3 tools/dds_smoketest.py        # lectura DDS
python3 tools/diag_sim.py             # física del simulador
python3 tools/check_write_path.py     # escritura DDS
./tools/audit_portability.sh          # rutas cableadas
```

---

## 12. Contexto del proyecto

Tres líneas de investigación abiertas:

| línea | estado | hardware extra |
|---|---|---|
| uc03 coste de transporte | siguiente | ninguno |
| uc02 navegación de salida de sala | tras conocer el LiDAR | quizá Mid-360 |
| uc04 seguimiento de personas | base ya montada | ninguno |

uc01, locomoción RL, está cerrado con un resultado propio y en pausa.

Documentación relacionada:

- [`QUICKSTART.md`](QUICKSTART.md) — arrancar en 45 minutos
- [`DOCKER.md`](DOCKER.md) — detalles del contenedor
- [`SAFETY.md`](SAFETY.md) — obligatorio antes del robot
- [`USAGE_GUIDE.md`](USAGE_GUIDE.md) — notas de uso diario
- `usecases/uc01_locomotion/train/ENTORNO_FIJADO.md` — entorno de entrenamiento
- `results/tables/sweep_progress.md` — resultados experimentales
- [`legacy/`](legacy/) — documentación del montaje original en WSL2, **no seguir**
