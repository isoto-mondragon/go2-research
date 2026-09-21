# Entorno Go2 — Guía de usuario

**Grupo DANZ · Escuela Politécnica Superior · Mondragon Unibertsitatea**

Todo lo que necesitas para trabajar con el robot cuadrúpedo Unitree Go2, en
simulación o con el robot físico, sin instalar nada en tu ordenador más allá de
Docker.

Funciona en **Linux, Windows y macOS**, con cualquier tarjeta gráfica. No hace
falta NVIDIA.

---

## Índice

1. [Qué es esto y qué puedes hacer](#1-qué-es-esto-y-qué-puedes-hacer)
2. [Arquitectura](#2-arquitectura)
3. [Puertos y accesos](#3-puertos-y-accesos)
4. [Instalación](#4-instalación)
5. [Primeros pasos](#5-primeros-pasos)
6. [Qué hay dentro del contenedor](#6-qué-hay-dentro-del-contenedor)
7. [Herramientas disponibles](#7-herramientas-disponibles)
8. [Rendimiento](#8-rendimiento)
9. [El robot físico](#9-el-robot-físico)
10. [Límites conocidos](#10-límites-conocidos)
11. [Problemas frecuentes](#11-problemas-frecuentes)

---

## 1. Qué es esto y qué puedes hacer

Un entorno completo de desarrollo y experimentación sobre el Unitree Go2 EDU,
empaquetado en un contenedor Docker.

### Qué puedes hacer

| | |
|---|---|
| **Simular el robot** | física realista en MuJoCo, con el modelo oficial del Go2 |
| **Conducirlo con el teclado** | igual en simulación y en el robot real |
| **Desplegar políticas de control** | redes neuronales en formato ONNX |
| **Programar comportamientos** | Python, con API de alto y bajo nivel |
| **Leer todos los sensores** | IMU, posición y par de las 12 articulaciones, fuerza en los pies, batería |
| **Evaluar de forma reproducible** | protocolo con métricas de seguimiento, estabilidad y energía |
| **Conectar con el robot físico** | por Ethernet, con el mismo código |

### El principio de diseño

**El mismo código vale para el simulador y para el robot real.** No hay una
versión "de pruebas" y otra "de verdad": lo único que cambia es una variable de
entorno. Lo que funciona en simulación funciona en el robot.

### Qué NO es

No es un entorno de entrenamiento de aprendizaje por refuerzo. Entrenar una
política desde cero necesita GPU y se hace en Google Colab, aparte. Aquí se
**despliegan** políticas ya entrenadas y se **desarrollan** comportamientos
sobre el controlador de locomoción del fabricante.

---

## 2. Arquitectura

### Visión general

```
  TU ORDENADOR                          │  CONTENEDOR
                                        │
  navegador ──── puerto 6080 ───────────┼──► escritorio virtual
  cliente VNC ── puerto 5900 ───────────┼──►   (Xvfb + x11vnc)
                                        │          │
  terminal ───── docker compose exec ───┼──► shell  │
                                        │      │    │
  tu editor ──── volumen montado ───────┼──► /workspace
                                        │      │
                                        │      ▼
                                        │  ┌─────────────────┐
                                        │  │  Tu código      │
                                        │  │  Python         │
                                        │  └────────┬────────┘
                                        │           │ DDS
                                        │           ▼
                                        │  ┌─────────────────┐
                                        │  │ unitree_mujoco  │──► visor
                                        │  │  (simulador)    │
                                        │  └─────────────────┘
```

Con el robot físico, el último bloque se sustituye por el propio robot al otro
lado de un cable Ethernet. El resto es idéntico.

### Capas de software

```
  TUS CASOS DE USO        usecases/
         │
  NÚCLEO COMPARTIDO       src/go2core/
         │                  control/     contrato, alto y bajo nivel, seguridad
         │                  comms/       teleoperación
         │                  perception/  visión por computador (YOLO)
         │
  COMUNICACIÓN            CycloneDDS 0.10.2
         │                  (la misma versión que usa el robot por dentro)
         │
  DESTINO                 simulador MuJoCo  │  Go2 físico
```

### Los dos niveles de control

**Alto nivel — Sport Mode.** El controlador de locomoción del fabricante. Le
mandas velocidades y el robot camina solo. Robusto, no hay que entrenar nada.
Es lo adecuado para casi todo: navegación, percepción, seguimiento, medición.

```python
from go2core.control.go2_controller import Go2Controller

dog = Go2Controller(mode="sim", network="lo")
dog.stand_up()
dog.set_velocity(vx=0.3, vy=0.0, wz=0.0)   # adelante a 0.3 m/s
dog.stop()
```

**Bajo nivel — LowCmd.** Control articular directo: posición objetivo, ganancias
y par de cada uno de los 12 motores, a 200-500 Hz. Necesario para desplegar
políticas propias de aprendizaje por refuerzo.

```python
from go2core.control.lowlevel import LowLevel
from go2core.control import contract as ct

c = ct.load_contract("usecases/uc01_locomotion/configs/robot_go2.yaml")
ll = LowLevel(c, mode="sim")
ll.start()
print(ll.joint_q(), ll.joint_tau(), ll.tilt_rad())
```

> **Los dos niveles son excluyentes.** Publicar comandos de bajo nivel con Sport
> Mode activo hace que dos controladores peleen por los mismos motores. En el
> robot real eso puede provocar un movimiento brusco. Antes de bajar a `LowCmd`
> hay que liberar Sport Mode. Está explicado en `docs/SAFETY.md`.

### Los tres perfiles

| perfil | para quién | robot real | GUI |
|---|---|---|---|
| `sim` | uso normal, cualquier sistema operativo | no | navegador o VNC |
| `real` | robot físico | sí, **solo Linux** | no |
| `dev` | desarrollo avanzado en Linux | sí | X11 nativo |

---

## 3. Puertos y accesos

### Puertos publicados

| puerto | protocolo | para qué | cómo se usa |
|---|---|---|---|
| **6080** | HTTP (noVNC) | ver el simulador en el navegador | `http://localhost:6080/vnc.html` |
| **5900** | VNC | ver el simulador con cliente nativo, **más rápido** | conectar a `localhost:5900`, sin contraseña |

No hay más puertos abiertos. El contenedor no expone ningún servicio de red
adicional.

### Canales DDS (dentro del contenedor)

La comunicación con el robot, simulado o real, va por DDS. No son puertos que
tengas que tocar, pero conviene saber que existen:

| topic | dirección | contenido | frecuencia |
|---|---|---|---|
| `rt/lowstate` | robot → tú | estado completo: IMU, 12 articulaciones (posición, velocidad, par, temperatura), fuerza en los pies, batería | 200 Hz sim / 500 Hz real |
| `rt/lowcmd` | tú → robot | comandos articulares: posición, ganancias, par | 200-500 Hz |
| `rt/wirelesscontroller` | tú → robot | comandos de velocidad, como el mando | 50 Hz |
| `rt/sportmodestate` | robot → tú | posición y velocidad del tronco (**solo simulación**) | 50 Hz |

Dominios DDS: **1** para simulación, **0** para el robot real. Están separados a
propósito, para que no se mezclen.

### Acceso al sistema de ficheros

El repositorio está **montado**, no copiado:

```
  tu ordenador                      contenedor
  ~/go2-research/          <──────► /workspace
```

Editas con tu editor de siempre y el cambio se ve dentro al instante, sin
reconstruir nada. Lo que guardes en `/workspace` persiste; lo que escribas fuera
de ahí desaparece al parar el contenedor.

---

## 4. Instalación

### Requisitos

- **Docker** 24 o superior
- **Git**
- **10 GB** libres en disco
- Conexión a internet la primera vez

### Linux (Ubuntu / Debian)

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2 docker-buildx git
sudo usermod -aG docker $USER
```

Después, **reinicia el ordenador**. No basta con cerrar la terminal: la
pertenencia al grupo `docker` solo se aplica en una sesión nueva.

### Windows y macOS

Instala [Docker Desktop](https://www.docker.com/products/docker-desktop/). En
Windows, elige el motor WSL2 cuando lo pregunte.

**Importante:** entra en **Settings → Resources** y asigna al menos **4 CPUs y
8 GB de RAM**. Los valores por defecto son bajos y el simulador irá lento.

### Comprobar

```bash
docker run --rm hello-world
```

Debe imprimir `Hello from Docker!`. Si dice `permission denied`, en Linux falta
reiniciar tras el `usermod`.

### Descargar el proyecto y la imagen

```bash
git clone https://github.com/isoto-mondragon/go2-research.git
cd go2-research
docker compose --profile sim pull
```

Unos **5 minutos**: se descarga la imagen ya construida, no se compila nada.

<details>
<summary>Construirla tú mismo (no hace falta)</summary>

```bash
docker compose --profile sim build
```

20 a 40 minutos: compila ROS 2, CycloneDDS y el SDK de Unitree desde el código
fuente. Solo es necesario si modificas el `Dockerfile`.
</details>

---

## 5. Primeros pasos

### Arrancar el simulador

```bash
docker compose --profile sim up
```

Esta terminal se queda ocupada. **Déjala abierta.**

Cuando veas `escritorio virtual listo`, abre en el navegador:

**http://localhost:6080/vnc.html** → botón **Connect**

Verás la ventana de MuJoCo con el robot tumbado en el suelo.

### Poner el robot de pie

Abre una **terminal nueva**:

```bash
cd go2-research
docker compose --profile sim exec shell bash
```

El prompt cambia a `root@a1b2c3:/workspace#`. **Ya estás dentro.**

```bash
python3 usecases/uc01_locomotion/deploy/run_policy.py --mode sim --duration 60
```

Mira el navegador: el robot se levanta y se mantiene de pie.

### Conducirlo con el teclado

Necesitas **tres terminales**.

**Terminal 1** — el simulador, ya la tienes.

**Terminal 2** — la política escuchando el teclado:

```bash
cd go2-research
docker compose --profile sim exec shell bash
python3 usecases/uc01_locomotion/deploy/run_policy.py --mode sim --teleop --duration 300
```

**Terminal 3** — el teclado:

```bash
cd go2-research
docker compose --profile sim exec shell bash
python3 tools/teleop.py --mode sim
```

| tecla | acción |
|---|---|
| `W` / `S` | adelante / atrás |
| `A` / `D` | lateral izquierda / derecha |
| `Q` / `E` | girar izquierda / derecha |
| espacio | parar |
| `x` | salir |

### Parar

Ctrl+C en la terminal del simulador, y después:

```bash
docker compose --profile sim down
```

### Anfitrión o contenedor: la confusión del primer día

| | prompt | ruta |
|---|---|---|
| **tu ordenador** | `tunombre@tumaquina:~$` | `/home/tunombre/...` |
| **contenedor** | `root@a1b2c3:/workspace#` | `/workspace` |

Si dudas:

```bash
ls /.dockerenv >/dev/null 2>&1 && echo "CONTENEDOR" || echo "ANFITRION"
```

| en tu ordenador | dentro del contenedor |
|---|---|
| `docker compose ...` | `python3 ...` de cualquier herramienta |
| `git` | el simulador |
| editar ficheros | todo lo demás |

---

## 6. Qué hay dentro del contenedor

### Software

| componente | versión | para qué |
|---|---|---|
| Ubuntu | 22.04 | única combinación probada por Unitree con ROS 2 |
| ROS 2 Humble | ros-base + rviz2 | middleware robótico |
| CycloneDDS | 0.10.2 | comunicación; **la versión exacta del robot** |
| unitree_sdk2 | C++ y Python | API del robot |
| unitree_mujoco | — | simulador, ya configurado |
| MuJoCo | última | motor de física |
| PyTorch | CPU | inferencia |
| ONNX Runtime | — | ejecución de políticas |
| Ultralytics | — | YOLO para visión |
| OpenCV, NumPy, SciPy, pandas, matplotlib | — | análisis |

### Rutas

| ruta | contenido |
|---|---|
| `/workspace` | el repositorio, montado desde tu ordenador |
| `/opt/go2/` | dependencias de Unitree |
| `/opt/go2/unitree_mujoco/` | simulador |
| `/opt/go2/unitree_ros2/` | mensajes ROS 2 y CycloneDDS |
| `/opt/unitree_robotics/` | librería C++ del SDK |

### Variables de entorno

| variable | valores | para qué |
|---|---|---|
| `GO2_MODE` | `sim` / `real` | destino |
| `GO2_IFACE` | `lo` / `enp3s0`... | interfaz de red |
| `GO2_DOMAIN` | `1` / `0` | dominio DDS |
| `GO2_GUI` | `novnc` / `x11` / `none` | escritorio |
| `GO2_RES` | `1024x768x16` | resolución del escritorio |

Ver cómo están resueltas:

```bash
python3 -m go2core.paths
```

---

## 7. Herramientas disponibles

Todas se ejecutan **dentro del contenedor**, desde `/workspace`.

### Diagnóstico

```bash
python3 -m go2core.paths                    # rutas y entorno
python3 tools/dds_smoketest.py --mode sim   # comprobar lectura de sensores
python3 tools/diag_sim.py                   # comprobar la física del simulador
python3 tools/check_write_path.py           # comprobar envío de comandos
```

Si algo no funciona, empieza siempre por `dds_smoketest.py`: dice si el estado
del robot llega y si los sensores son plausibles.

### Control

```bash
# Desplegar una política
python3 usecases/uc01_locomotion/deploy/run_policy.py --mode sim --duration 60

# Con teclado
python3 usecases/uc01_locomotion/deploy/run_policy.py --mode sim --teleop --duration 300

# Velocidad constante
python3 usecases/uc01_locomotion/deploy/run_policy.py --mode sim --vx 0.5 --duration 60

# Secuencia automática, útil para comparar
python3 usecases/uc01_locomotion/deploy/run_policy.py --mode sim --auto --duration 60

# Solo levantarse, sin política
python3 usecases/uc01_locomotion/deploy/run_policy.py --mode sim --stand-only

# Sin mover nada: muestra lo que haría
python3 usecases/uc01_locomotion/deploy/run_policy.py --mode sim --dry-run
```

### Evaluación

```bash
python3 usecases/uc01_locomotion/eval/eval_sim.py \
    --policy experiments/uc01_locomotion/legacy_wsl2/checkpoints/policy.onnx \
    --rollouts 3 --out /tmp/mi_evaluacion
```

Ejecuta una secuencia fija de comandos y mide seguimiento de velocidad,
estabilidad, coste de transporte y calidad de la marcha. Emite un veredicto:
si la política camina de verdad o si hace algo degenerado.

### Teleoperación

```bash
python3 tools/teleop.py --mode sim
python3 tools/teleop.py --mode real --iface enp3s0
```

---

## 8. Rendimiento

### Lo que va rápido y lo que va lento

| | |
|---|---|
| **Física y control** | rápido. El bucle de control usa el 7% de su plazo |
| **Visor** | lento al girar la cámara o hacer zoom |

**La lentitud es solo visual.** El visor dibuja por software y se transmite por
VNC; la física y el control corren en hilos aparte y van sobrados. Los
experimentos no se ven afectados.

Medido en un portátil sin GPU dedicada (i5-1335U): 1.37 ms de trabajo por paso
de control sobre un plazo de 20 ms, 0% de pasos fuera de plazo.

### Cómo mejorarlo

**1. Dar más recursos a Docker** (Windows y macOS). Settings → Resources → al
menos 4 CPUs y 8 GB. Es la mejora más grande y mucha gente no la hace.

**2. Usar un cliente VNC nativo en vez del navegador.** Es bastante más rápido:

- Linux: `sudo apt install tigervnc-viewer` y luego `vncviewer localhost:5900`
- Windows: [TightVNC](https://www.tightvnc.com/) o RealVNC Viewer
- macOS: Finder → Ir → Conectarse al servidor → `vnc://localhost:5900`

Sin contraseña.

**3. Cerrar la pestaña del navegador cuando no mires.** El servidor VNC solo
codifica imagen si hay alguien conectado. Cerrar la pestaña libera CPU al
instante.

**4. Bajar la resolución del escritorio:**

```bash
GO2_RES=800x600x16 docker compose --profile sim up
```

**5. Ejecutar sin visor para experimentos largos:**

```bash
GO2_GUI=none docker compose --profile sim up
```

No verás nada, pero todo lo demás funciona igual y va más rápido.

---

## 9. El robot físico

> **Antes de nada, lee `docs/SAFETY.md`.** No es burocracia: son 15 kg de robot
> con motores que dan 45 Nm.

**Solo funciona desde Linux.** La comunicación DDS por Ethernet necesita que el
contenedor use la red del anfitrión, y eso en Docker Desktop de Windows y macOS
no funciona de verdad. No es una limitación de este proyecto, es del transporte.

### Resumen del procedimiento

En **tu ordenador**, no en el contenedor:

```bash
./env/go2_net.sh detect          # qué interfaz tiene el cable
./env/go2_net.sh create enp3s0   # IP estática 192.168.123.222
./env/go2_net.sh up
./env/go2_net.sh probe           # cuatro comprobaciones
```

Luego, con la interfaz anotada en `.env`:

```bash
docker compose --profile real run --rm real
```

Y dentro, en este orden:

```bash
# 1. Solo lectura. No envía nada.
python3 tools/dds_smoketest.py --mode real --iface enp3s0 --duration 30

# 2. Alto nivel: el robot camina solo
python3 -c "
from go2core.control.go2_controller import Go2Controller
dog = Go2Controller(mode='real', network='enp3s0')
dog.stand_up()
"
```

El control de bajo nivel exige liberar Sport Mode antes y tiene su propio
protocolo en `SAFETY.md`.

---

## 10. Límites conocidos

**Robot real solo desde Linux.** Explicado arriba.

**El visor va lento.** Explicado arriba. No afecta a la simulación.

**En simulación no hay telemetría de sensores.** El simulador no emula
temperatura de motores, fuerza en los pies ni batería: salen a cero. Con el
robot real sí vienen. El par solo es distinto de cero cuando hay comandos.

**`rt/lowstate` va a 200 Hz en simulación**, no a 500 como el robot real.

**Un solo simulador a la vez.** Dos instancias producen un estado incoherente
que parece un fallo de control y no lo es.

**El contenedor corre como root.** En Linux, los ficheros que cree dentro del
volumen montado quedarán con dueño `root`. Si te molesta:
`sudo chown -R $USER:$USER ~/go2-research`

---

## 11. Problemas frecuentes

| síntoma | causa y solución |
|---|---|
| `permission denied ... docker.sock` | en Linux, reinicia tras `usermod -aG docker $USER` |
| `docker compose build` acaba al instante | falta `--profile sim` |
| `ModuleNotFoundError: numpy` | estás en tu ordenador, no en el contenedor |
| El navegador no muestra nada en 6080 | comprueba que `up` sigue corriendo y dijo `escritorio virtual listo`; recarga y pulsa Connect |
| El robot se queda tumbado | cada ejecución termina amortiguando; es normal. Reinicia el simulador |
| Va muy lento | sección 8 |
| El teclado no mueve el robot | ¿está corriendo `run_policy.py --teleop` en otra terminal? |
| `No existe la politica` | `git pull`: el fichero va en el repositorio |

### Reiniciar del todo

```bash
docker compose --profile sim down
docker compose --profile sim up
```

### Empezar de cero

```bash
docker compose --profile sim down -v
docker compose --profile sim build --no-cache
```

---

## Dónde seguir

| documento | para qué |
|---|---|
| `docs/GUIA_COMPLETA.md` | desarrollar casos de uso, arquitectura interna |
| `docs/SAFETY.md` | **obligatorio** antes de tocar el robot físico |
| `docs/DOCKER.md` | detalles del contenedor |
| `usecases/*/README.md` | cada caso de uso |

### Contacto

Ibon Soto Alsua · Grupo DANZ · Escuela Politécnica Superior
Mondragon Unibertsitatea
