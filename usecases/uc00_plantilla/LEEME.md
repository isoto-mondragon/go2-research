# Tu caso de uso en cinco minutos

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

## Qué puedes leer del robot

Dentro de `decidir(tel, t)`:

| qué | línea | 
|---|---|
| batería (0 a 100) | `tel.bateria_pct()` |
| inclinación (radianes, 0 es recto) | `tel.inclinacion()` |
| temperatura máxima (grados) | `tel.temp_max()` |
| ángulos de las 12 articulaciones | `tel.q()` |
| velocidades de las articulaciones | `tel.dq()` |
| pares de las articulaciones | `tel.tau()` |
| giro del cuerpo | `tel.gyro()` |
| fuerza en los 4 pies | `tel.foot_force()` |
| segundos desde que empezó | `t` |

## Lo que no puedes hacer en simulación

**Batería, temperatura y fuerza de los pies valen 0.** El simulador no los
tiene. No es un fallo. Un caso que dependa de ellos (como el ejemplo 5) solo
hace algo en el robot real.

Además, en el robot real las velocidades por debajo de 0.2 m/s las ignora el
robot: se queda quieto o va a tirones. La plantilla ya lo tiene en cuenta.

## Si quieres guardar lo que pasa

Añade `--log --tag lo_que_sea`. Se crea una carpeta en `experiments/` con los
datos y un `manifest.json` con la versión exacta del código. Antes, haz
`git commit`: con cambios sin guardar el resultado no se puede reproducir.
Luego, `python3 usecases/uc05_mi_idea/eval/measure.py` calcula un resumen.

## ¿Y si quiero saber cómo funciona por dentro?

[`docs/API.md`](../../docs/API.md) y
[`docs/ESTRATEGIA_CASOS_USO.md`](../../docs/ESTRATEGIA_CASOS_USO.md).
No hacen falta para empezar.
