# Cómo desarrollar un caso de uso

## Lo primero: no hace falta entrenar nada

El Go2 EDU trae **Sport Mode**, el controlador de locomoción del fabricante.
Le mandas velocidades y camina. Robusto, ya entrenado, sin mantenimiento.

Para navegación, percepción, seguimiento o medición energética **no se entrena
ninguna política**. Se usa Sport Mode y se programa encima.

## La trampa del simulador

`unitree_mujoco` **no emula Sport Mode**. En simulación la única forma de mover
al robot es una política RL de bajo nivel.

| | robot real | simulación |
|---|---|---|
| Sport Mode | sí | **no existe** |
| política RL propia | opcional | única opción |

Consecuencia práctica: en simulación el robot se mueve peor de lo que se moverá
en la realidad, porque la política heredada sigue los comandos al 40-56 %
(medido en uc01) mientras Sport Mode los sigue bastante mejor.

**No confundas esa limitación con un problema de tu caso de uso.**

## Qué transfiere del simulador al robot

| valida | ¿transfiere? |
|---|---|
| el bucle percepción → decisión → DDS | **sí, idéntico** |
| los signos del control | **sí** |
| tasa de fotogramas, carga de CPU | **sí** |
| ausencia de errores de indexado, CRC, dominios | **sí** |
| que no se cuelga ni se cae en casos raros | **sí** |
| las ganancias del control | **no** |
| la velocidad que alcanza de verdad | **no** |

Lo que no transfiere son dos o tres números. Lo que sí transfiere es donde
están los errores que cuestan días.

## La receta

**1. Diseña con dos destinos desde el principio.**

Tu código decide `(vx, vy, wz)`. Una clase pequeña decide a dónde van:

```python
class SalidaSimulador:      # publica en rt/wirelesscontroller
class SalidaRobot:          # llama a Go2Controller (Sport Mode)
```

Ver `usecases/uc04_person_following/deploy/follow_person.py`.

**2. El simulador valida la lógica, no los números.**

**3. Marca en el YAML qué parámetros hay que reajustar con el robot**, y con
qué valores de partida. Si no, alguien llevará las ganancias de simulación al
hardware y se llevará un susto.

**4. En el robot real, Sport Mode por defecto.** Bajar a `LowCmd` solo si
investigas sobre locomoción, y con el protocolo de `docs/SAFETY.md`.

## Cuándo sí merece entrenar una política

| situación | ¿entrenar? |
|---|---|
| navegación, percepción, seguimiento | no |
| medición energética | no |
| investigar marchas o control de bajo nivel | sí |
| comparar Sport Mode contra una política RL | sí, es el sujeto del experimento |

Para la mayoría de casos de uso, la política heredada basta: solo está ahí
porque el simulador no ofrece otra cosa.

## Estructura de un caso de uso

usecases/ucXX_nombre/
├── README.md pregunta, diseño, limitaciones, qué reajustar
├── configs/ parámetros versionados, nada cableado en el código
├── perception/ si usa sensores
├── deploy/ el bucle de control
└── eval/ medición y figuras


Se crea con:

```bash
./env/init_repo.sh --add-usecase ucXX_nombre
```

Y se usa la librería compartida:

```python
from go2core import paths                      # rutas, sin cablear nada
from go2core.control import contract as ct      # parámetros del robot
from go2core.control.lowlevel import LowLevel   # telemetría y bajo nivel
from go2core.control.go2_controller import Go2Controller   # Sport Mode
```

## Reglas

1. Ningún parámetro de control se cablea: todo en `configs/`
2. Un experimento sin `manifest.json` no existe
3. Las figuras se generan con un comando, nunca se editan a mano
4. Antes de tocar el robot, `docs/SAFETY.md`
5. Prueba siempre con `--dry-run` antes de mover nada

## Cuidado con `Go2Controller` en modo real

`src/go2core/control/go2_controller.py` viene del workspace WSL2, donde el
simulador era `play_dds.py`. Publica en `rt/wirelesscontroller`.

Eso funciona en simulacion, pero **el robot fisico NO escucha ese topic desde
fuera**: lo publica el mando. Los comandos salen, nadie los recibe, y el robot
se queda quieto sin ningun error.

Para mover el robot real hay que llamar a `SportClient` directamente:

```python
from unitree_sdk2py.go2.sport.sport_client import SportClient
sport = SportClient(); sport.SetTimeout(10.0); sport.Init()
sport.StandUp(); time.sleep(3)
sport.BalanceStand(); time.sleep(2)
sport.Move(vx, vy, wz)      # repetir a 20 Hz mientras se quiera avanzar
sport.StopMove()
```

Ver `tools/teleop_real.py` y `SalidaRobot` en uc04.
