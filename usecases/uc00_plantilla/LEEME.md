# Tu caso de uso en cinco minutos

> **Para quién:** quien quiere que el robot haga algo suyo, sin conocer el proyecto.
> **Cuándo:** es lo primero que abres al empezar un caso de uso.

Aquí haces que el robot haga algo tuyo. Solo escribes en **un** fichero:
`mi_caso.py`.

## 1. Copia la carpeta

Dale el nombre que quieras (aquí, `uc05_mi_idea`):

```bash
cp -r usecases/uc00_plantilla usecases/uc05_mi_idea
```

## 2. Abre `mi_caso.py`

Es lo único que tocas. Ya trae un ejemplo escrito: avanza dos segundos y para.
Cámbialo por lo tuyo. Devuelve tres números: `(vx, vy, wz)`, es decir,
adelante, izquierda y giro.

Lo demás (`deploy/main.py`, `configs/`) no se toca.

## 3. Pruébalo sin mover nada

```bash
python3 usecases/uc05_mi_idea/deploy/main.py --mode sim --dry-run
```

`--dry-run` significa "hazlo de mentira": calcula y te lo enseña, pero no manda
nada al robot. Empieza siempre así.

## 4. Cuando funcione, quítale el `--dry-run`

```bash
python3 usecases/uc05_mi_idea/deploy/main.py --mode sim
```

Para el simulador necesitas tenerlo abierto (mira `docs/GUIA.md`, parte 3).
Para el robot de verdad, cambia a `--mode real`, ten el mando en la mano
(**L2 + B** lo para) y lee `docs/SAFETY.md` antes.

Ctrl + C para parar cuando quieras. El robot se queda quieto.

## Tu código vale para los dos

**El mismo `mi_caso.py` sirve para el simulador y para el robot de verdad.**
Solo cambias el comando:

```bash
python3 usecases/uc05_mi_idea/deploy/main.py --mode sim
python3 usecases/uc05_mi_idea/deploy/main.py --mode real --iface <IFACE>
```

(`<IFACE>` es el nombre de la conexión de red con el robot; mira `docs/GUIA.md`,
parte 4.)

**Lo que cambia es qué datos tienes.**

| lo que lees | simulador | robot real |
|---|---|---|
| `tel.q()` posiciones de las 12 articulaciones | sí | sí |
| `tel.dq()` velocidades | sí | sí |
| `tel.tau()` par de cada motor | sí, estimado | sí, estimado |
| `tel.gyro()` giro | sí | sí |
| `tel.inclinacion()` | sí | sí |
| `tel.bateria_pct()` | **siempre 0** | sí |
| `tel.temp_max()` temperatura | **siempre 0** | sí |
| `tel.foot_force()` fuerza en los pies | **siempre 0** | sí |
| cámara del robot | **no existe** | sí |

**Si tu lógica depende de la batería, la temperatura o los pies, no la podrás
probar en el simulador.** Escríbela igual, pero pruébala con el robot.

Y una diferencia de comportamiento:

**En el robot real, Sport Mode ignora los comandos por debajo de unos
0.2 m/s.** El robot se queda quieto o va a tirones. No es un fallo tuyo. En
simulación no pasa. Si tu caso de uso necesita movimientos lentos, tenlo en
cuenta. La plantilla sube las órdenes pequeñas a ese mínimo por ti.

## Cinco ejemplos para empezar

Se copian encima de `mi_caso.py`:

```bash
cp usecases/uc05_mi_idea/ejemplos/1_avanzar.py usecases/uc05_mi_idea/mi_caso.py
```

| ejemplo | qué hace | qué enseña |
|---|---|---|
| `1_avanzar.py` | avanza dos segundos y para | lo más simple |
| `2_alternar_avanzar_y_girar.py` | cada 5 s alterna entre avanzar y girar | leer un dato del robot |
| `3_parar_si_se_inclina.py` | avanza, pero para si se inclina más de 15° | reaccionar a un sensor |
| `4_seguir_con_camara.py` | gira hacia la persona que ve | usar la cámara |
| `5_girar_segun_bateria_SOLO_REAL.py` | gira mientras la batería pase del 60 % | **solo con el robot real** |

Los ejemplos 1, 2 y 3 se ven moverse en el simulador. El 4 necesita una cámara.
El 5 no hace nada en simulación.

## Qué puedes hacer en `decidir()`

`decidir(tel, t)` se llama unas 20 veces por segundo. Cada apartado: el código
y cuándo se usa.

### Leer el robot

Cuándo: para reaccionar a lo que le pasa al robot.

```python
angulos = tel.q()                    # los 12 ángulos; tel.q()[1] es FR_thigh
print(tel.inclinacion())             # radianes, 0 es recto
if tel.gyro()[2] > 0.3: ...          # está girando a la izquierda
```

| lectura | qué devuelve |
|---|---|
| `tel.q()` | array de 12, ángulos en rad |
| `tel.dq()` | array de 12, velocidades en rad/s |
| `tel.tau()` | array de 12, par estimado en Nm |
| `tel.gyro()` | array de 3, rad/s, ejes del cuerpo (`[2]` es el giro sobre sí mismo) |
| `tel.inclinacion()` | un número, radianes; 0 es recto |
| `tel.bateria_pct()` | un número, 0 a 100 |
| `tel.temp_max()` | un número, grados del motor más caliente |
| `tel.foot_force()` | array de 4, uno por pie (valor del sensor, sin calibrar) |

**Orden de las articulaciones** en `q()`, `dq()` y `tau()`: patas en el orden
FR, FL, RR, RL (delantera derecha, delantera izquierda, trasera derecha,
trasera izquierda), y en cada pata: cadera (*hip*), muslo (*thigh*), rodilla
(*calf*). Es decir: `[FR_hip, FR_thigh, FR_calf, FL_hip, ..., RL_calf]`.

### Devolver movimiento

Cuándo: siempre. `decidir()` devuelve tres números: `(vx, vy, wz)`.
`vx > 0` adelante, `vy > 0` izquierda, `wz > 0` giro a la izquierda.

```python
return 0.3, 0.0, 0.0      # adelante
return 0.0, 0.0, 0.5      # girar a la izquierda
return 0.0, 0.0, 0.0      # parar
```

Las velocidades están en m/s y rad/s. `main.py` las recorta a los topes de
`configs/params.yaml` (por defecto 0.4 m/s y 0.6 rad/s), así que pedir 1.0 no
es peligroso. Si no devuelves nada, el robot para.

### Usar el tiempo

Cuándo: para hacer secuencias. `t` son los segundos desde que empezó.

```python
if t < 2.0:
    return 0.3, 0.0, 0.0
elif t < 4.0:
    return 0.0, 0.0, 0.5
return 0.0, 0.0, 0.0       # importante: qué hacer cuando acaba la secuencia
```

### Recordar cosas entre llamadas

Cuándo: cuando lo que haces ahora depende de lo que pasó antes. Una variable
global fuera de la función se conserva entre llamadas.

```python
inicio = None

def decidir(tel, t):
    global inicio
    if inicio is None and tel.inclinacion() > 0.2:
        inicio = t                      # apunta cuándo se inclinó por primera vez
    if inicio is not None and t - inicio < 3.0:
        return 0.0, 0.0, 0.0            # espera tres segundos quieto
    return 0.3, 0.0, 0.0
```

Si necesitas prepararlo **una sola vez antes de empezar** (abrir la cámara,
cargar un modelo), define `preparar(modo, iface, domain)`; se llama antes del
primer `decidir()`. `modo` es `"sim"` o `"real"`.

### Usar la cámara

Cuándo: cuando necesitas imagen. Se crea en `preparar()` y se lee en
`decidir()`. **En simulación no hay cámara del robot**: por eso solo se crea
en modo real (pedir la imagen en simulación deja el bucle esperando).

```python
camara = None

def preparar(modo, iface, domain):
    global camara
    if modo == "real":
        from robot_camera import CamaraRobot
        camara = CamaraRobot(iface, domain, init_dds=False)

def decidir(tel, t):
    imagen = camara.leer() if camara else None    # imagen BGR de 1920x1080, o None si falla
```

### Detectar personas

Cuándo: seguir, contar o vigilar personas. Se crea en `preparar()` y se lee en
`decidir()`. **No crees además la cámara aparte:** el detector abre la del robot
él solo. Necesita el contenedor (usa YOLO).

```python
import sys
from go2core import paths
sys.path.insert(0, str(paths.USECASES / "uc04_person_following"))
from perception.detector import DetectorPersonas

detector = DetectorPersonas(fuente="robot", iface=iface, domain=domain, init_dds=False)   # en preparar()
imagen, d = detector.leer()          # en decidir(); d.visible, d.lateral (-1 izq a +1 der), d.tamano (0 a 1)
```

Con `fuente="webcam"` usa la webcam del portátil en lugar de la del robot (es lo
que hay que usar en simulación). El ejemplo 4 lo tiene todo montado.

### Parámetros propios

Cuándo: para cambiar valores sin tocar el código, y que queden guardados con
cada experimento. Se ponen en `configs/params.yaml`, en la sección `mi_caso`,
y se leen con el diccionario `PARAMS`.

```yaml
mi_caso:
  velocidad: 0.3
```

```python
return PARAMS["velocidad"], 0.0, 0.0
```

## Si quieres guardar lo que pasa

Añade `--log --tag lo_que_sea`. Se crea una carpeta en `experiments/` con los
datos y un `manifest.json` con la versión exacta del código. Antes, haz
`git commit`: con cambios sin guardar el resultado no se puede reproducir.
Luego, `python3 usecases/uc05_mi_idea/eval/measure.py` calcula un resumen.

## ¿Y si quiero saber cómo funciona por dentro?

[`docs/API.md`](../../docs/API.md) y
[`docs/ESTRATEGIA_CASOS_USO.md`](../../docs/ESTRATEGIA_CASOS_USO.md).
No hacen falta para empezar.
