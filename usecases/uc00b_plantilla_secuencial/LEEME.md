# Tu caso de uso, escrito como una receta

> **Para quién:** quien quiere que el robot haga algo suyo, sin conocer el proyecto.
> **Cuándo:** es lo primero que abres al empezar un caso de uso.

Escribes lo que quieres que haga el robot, **de arriba abajo**, en un solo
fichero: `mi_caso.py`. Por ejemplo: *levántate, busca a una persona, sígueme*.

## 1. Copia la carpeta

Dale el nombre que quieras (aquí, `uc05_mi_idea`):

```bash
cp -r usecases/uc00b_plantilla_secuencial usecases/uc05_mi_idea
```

## 2. Abre `mi_caso.py`

Es lo único que tocas. Ya trae un caso escrito:

```python
def caso(robot):
    robot.levantarse()
    robot.avanzar(2)         # dos segundos hacia delante...
    robot.parar()            # ...y quieto
```

`robot` es el robot. Cada línea le pide algo y **espera a que termine** antes de
pasar a la siguiente. Lo demás (`deploy/`, `configs/`) no se toca.

## 3. Pruébalo sin mover nada

```bash
python3 usecases/uc05_mi_idea/deploy/main.py --mode sim --dry-run
```

`--dry-run` significa "hazlo de mentira": ejecuta tu caso entero y te enseña lo
que haría, pero no manda nada al robot. Empieza siempre así.

## 4. Cuando funcione, quítale el `--dry-run`

```bash
python3 usecases/uc05_mi_idea/deploy/main.py --mode sim
```

Para el simulador necesitas tenerlo abierto (mira `docs/GUIA.md`, parte 3), y
`run_policy.py --mode sim --teleop` en marcha. Para el robot de verdad, cambia a
`--mode real`, ten el mando en la mano (**L2 + B** lo para) y lee
`docs/SAFETY.md` antes.

Ctrl + C para parar cuando quieras: el robot se queda quieto. Si tu caso no ha
terminado antes, se corta a los 60 segundos (`--duration 120` para más).

## Tu código vale para los dos

**El mismo `mi_caso.py` sirve para el simulador y para el robot de verdad.**
Solo cambias el comando:

```bash
python3 usecases/uc05_mi_idea/deploy/main.py --mode sim
python3 usecases/uc05_mi_idea/deploy/main.py --mode real --iface <IFACE>
```

(`<IFACE>` es el nombre de la conexión de red con el robot; mira `docs/GUIA.md`,
parte 4.)

**Lo que cambia es qué puedes hacer y qué datos tienes:**

| lo que usas | simulador | robot real |
|---|---|---|
| `avanzar`, `retroceder`, `girar_*`, `mover`, `parar`, `esperar` | sí | sí |
| `levantarse()` | no hace nada (ya está de pie) | sí |
| `sentarse()` | no hace nada | sí |
| `angulos()`, `velocidades()`, `pares()` | sí | sí |
| `giro()`, `inclinacion_grados()` | sí | sí |
| `bateria()` | **siempre 0** | sí |
| `temperatura()` | **siempre 0** | sí |
| `fuerza_pies()` | **siempre 0** | sí |
| `imagen()` (cámara del robot) | **no existe** | sí |
| `buscar_persona()` | con la webcam del portátil | con la cámara del robot |

**Si tu lógica depende de la batería, la temperatura o los pies, no la podrás
probar en el simulador.** Escríbela igual, pero pruébala con el robot.

Y una diferencia de comportamiento:

**En el robot real, Sport Mode ignora los comandos por debajo de unos
0.2 m/s.** El robot se queda quieto o va a tirones. No es un fallo tuyo. En
simulación no pasa. La plantilla sube las órdenes pequeñas a ese mínimo por ti.

## Cinco ejemplos para empezar

Se copian encima de `mi_caso.py`:

```bash
cp usecases/uc05_mi_idea/ejemplos/1_avanzar.py usecases/uc05_mi_idea/mi_caso.py
```

| ejemplo | qué hace | qué enseña |
|---|---|---|
| `1_avanzar.py` | se levanta, avanza dos segundos y se sienta | una receta de arriba abajo |
| `2_cuadrado.py` | recorre un cuadrado y escribe la inclinación | bucles y leer un sensor |
| `3_parar_si_se_inclina.py` | avanza, pero para si se inclina más de 15° | reaccionar a un sensor |
| `4_seguir_a_una_persona.py` | se levanta, busca a una persona y la sigue | percepción: YOLO en un bucle |
| `5_girar_segun_bateria_SOLO_REAL.py` | gira mientras la batería pase del 60 % | **solo con el robot real** |

Los ejemplos 1, 2 y 3 se ven moverse en el simulador. El 4 necesita cámara (la
del robot, o una webcam). El 5 no hace nada en simulación.

## Qué puedes hacer con `robot`

Cada apartado: el código y cuándo se usa.

### Ponerse de pie y sentarse

Cuándo: al empezar y al terminar. Solo tienen efecto en el robot real. Si te
olvidas de `levantarse()`, en el robot real la plantilla avisa y lo hace ella.

```python
robot.levantarse()
robot.sentarse()      # después de sentarse, hay que volver a levantarse()
```

### Moverse durante un tiempo

Cuándo: para secuencias sencillas. Cada verbo **termina con el robot parado**.
El primer número son los segundos; `vel` es opcional.

```python
robot.avanzar(2)                 # 2 s adelante a 0.3 m/s
robot.retroceder(1, vel=0.2)     # 1 s atrás
robot.girar_izquierda(3)         # 3 s a 0.5 rad/s, unos 90 grados
robot.girar_derecha(3, vel=0.4)
```

### Moverse dentro de un bucle

Cuándo: cuando lo que haces depende de lo que ves. `robot.mover()` da **un paso**
(unos 50 ms) con la velocidad que le pidas, y se repite en un bucle.

```python
while robot.activo():
    robot.mover(vx=0.3, wz=0.2)     # avanza girando un poco a la izquierda
```

Los tres números son `vx` (adelante +, atrás −, en m/s), `vy` (izquierda +,
derecha −, en m/s) y `wz` (giro a la izquierda +, a la derecha −, en rad/s). Las
velocidades se recortan a los topes de `configs/params.yaml` (por defecto
0.4 m/s y 0.6 rad/s), así que pedir 1.0 no es peligroso.

### Pararse y esperar

Cuándo: entre dos pasos, o para dar tiempo al robot.

```python
robot.parar()          # frena hasta quedarse quieto
robot.esperar(2)       # se queda quieto 2 segundos
```

### Saber cuándo terminar

Cuándo: en los bucles. `robot.activo()` es `False` cuando pulsas Ctrl-C, se acaba
`--duration` o salta una seguridad (robot muy inclinado, sin datos). No hace falta
que lo compruebes en las secuencias: los verbos ya paran solos.

```python
while robot.activo() and robot.tiempo() < 10:     # tiempo(): segundos desde que empezó
    robot.mover(vx=0.3)
```

### Leer el robot

Cuándo: para reaccionar a lo que le pasa al robot.

```python
print(robot.inclinacion_grados())     # 0 es recto
if robot.giro()[2] > 0.3:             # está girando a la izquierda
    print("girando")
```

| lectura | qué devuelve |
|---|---|
| `robot.inclinacion_grados()` | un número, grados; 0 es recto |
| `robot.giro()` | array de 3, rad/s, ejes del cuerpo (`[2]` es el giro sobre sí mismo) |
| `robot.angulos()` | array de 12, ángulos en rad |
| `robot.velocidades()` | array de 12, rad/s |
| `robot.pares()` | array de 12, par estimado en Nm |
| `robot.bateria()` | un número, 0 a 100 |
| `robot.temperatura()` | un número, grados del motor más caliente |
| `robot.fuerza_pies()` | array de 4, uno por pie (valor del sensor, sin calibrar) |

**Orden de las articulaciones** en `angulos()`, `velocidades()` y `pares()`:
patas en el orden FR, FL, RR, RL (delantera derecha, delantera izquierda, trasera
derecha, trasera izquierda), y en cada pata: cadera (*hip*), muslo (*thigh*),
rodilla (*calf*). Es decir: `[FR_hip, FR_thigh, FR_calf, FL_hip, ..., RL_calf]`.

### Recordar cosas

Cuándo: cuando lo que haces ahora depende de lo que pasó antes. Es Python normal:
una variable dentro de `caso()` se conserva mientras dure.

```python
esquinas = 0
while robot.activo() and esquinas < 4:
    robot.avanzar(2)
    robot.girar_izquierda(3)
    esquinas += 1
```

### Usar la cámara

Cuándo: cuando necesitas la imagen. **En simulación no hay cámara del robot**:
`imagen()` devuelve `None` y avisa.

```python
imagen = robot.imagen()           # imagen BGR de 1920x1080, o None si falla
if imagen is not None:
    print(imagen.shape)
```

### Detectar personas

Cuándo: seguir, contar o vigilar personas. `cargar_detector()` carga YOLO (tarda
unos segundos): llámalo una vez, antes del bucle. Usa la cámara del robot en real
y la webcam del portátil en simulación. Necesita el contenedor.

```python
robot.cargar_detector()
persona = robot.buscar_persona()     # dentro del bucle
if persona.visible:
    print(persona.lateral, persona.tamano)
```

`lateral` va de −1 (izquierda) a +1 (derecha) y `tamano` de 0 a 1 (sube al
acercarse). Con la cámara del robot, 0.85 es a un metro y 0.65 a tres. Si no se
puede cargar YOLO o no hay cámara, avisa y `buscar_persona()` devuelve "no
visible": el robot se queda quieto, no falla.

### Parámetros propios

Cuándo: para cambiar valores sin tocar el código, y que queden guardados con cada
experimento. Se ponen en `configs/params.yaml`, en la sección `mi_caso`, y se
leen con `robot.param()`. El segundo valor es el que se usa si no está en el yaml.

```yaml
mi_caso:
  velocidad: 0.3
```

```python
robot.avanzar(2, vel=robot.param("velocidad", 0.3))
```

## Lo que hace la plantilla por ti

- Recorta las velocidades a los topes y acelera poco a poco.
- Para si se pulsa Ctrl-C, si se acaba el tiempo, si el robot se inclina mucho o
  si dejan de llegar datos. Al salir, el robot se queda quieto.
- Si tu caso tiene un error, te enseña en qué línea y para el robot igualmente.
- Con `--dry-run` no manda nada.

**Estado:** `levantarse()` y `sentarse()` en el robot real todavía no se han
probado con el robot; hazlo primero con espacio libre y el mando en la mano.

## Si quieres guardar lo que pasa

Añade `--log --tag lo_que_sea`. Se crea una carpeta en `experiments/` con los
datos y un `manifest.json` con la versión exacta del código. Antes, haz
`git commit`: con cambios sin guardar el resultado no se puede reproducir.
Luego, `python3 usecases/uc05_mi_idea/eval/measure.py` calcula un resumen.

## Otras plantillas y más información

- [`uc00_plantilla`](../uc00_plantilla/LEEME.md): la otra forma de escribir un
  caso, con una función `decidir(tel, t)` que se llama 20 veces por segundo.
  Sirve si prefieres pensar en reglas antes que en secuencias.
- [`docs/API.md`](../../docs/API.md) y
  [`docs/ESTRATEGIA_CASOS_USO.md`](../../docs/ESTRATEGIA_CASOS_USO.md): cómo
  funciona por dentro. No hacen falta para empezar.
