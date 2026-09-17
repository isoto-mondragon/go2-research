# Barrido de presupuesto de computo: progreso

Entorno fijado (ver `usecases/uc01_locomotion/train/ENTORNO_FIJADO.md`):
unitree_rl_mjlab @ 1425b15f, mjlab 1.2.0, mujoco 3.7.0, mujoco-warp 3.5.0,
warp-lang 1.12.1. T4 gratuita, 4096 entornos, `--agent.seed` activo.

Evaluacion: `eval_sim.py`, 3 rollouts, escena plana, secuencia fija de 6
segmentos. Entrenamiento completo estimado: 7 h 30.

| run | presupuesto | semilla | vx 0.3 | vx 0.6 | wz 0.5 | vy 0.3 | caidas | CoT 0.3 |
|---|---|---|---|---|---|---|---|---|
| t4_15m_seed1 | 15 min | 1 | 0.164 | 0.439 | 0.260 | 0.089 | 0/3 | 0.273 |
| t4_5m_seed1 | 5 min | 1 | 0.293 | 0.589 | 0.157 | 0.001 | 0/3 | 0.066 |

AVISO sobre t4_5m_seed1: CoT de 0.066 implica ~2.9 W frente a los ~12 W del
run de 15 min a la misma velocidad comandada. Sigue vx casi perfecto pero no
gira ni se desplaza lateralmente. Sospecha de marcha degenerada (deslizamiento
sin levantar las patas). PENDIENTE de inspeccion visual y de metricas de marcha.
NO usar esta fila en ninguna figura hasta resolverlo.

## Pendientes

5, 30, 60 y 120 min x semillas 1, 2, 3.

## Fuera del barrido

`legacy_wsl2`: politica heredada del workspace WSL2. Otro commit, otra version
de mjlab, presupuesto incierto. NO es un punto de la curva. Sus numeros
(vx 0.3 -> 0.151, wz 0.5 -> 0.178) quedan por debajo del run de 15 minutos.

## Hipotesis a comprobar cuando esten los 15 runs

Las dos politicas evaluadas hasta ahora se quedan en un 50-70 % de seguimiento
de velocidad. Que dos entrenamientos muy distintos converjan al mismo techo
apunta a un factor sistematico del DESPLIEGUE, no de la calidad del
entrenamiento. Candidatos: el cero de `gait_phase` por debajo del umbral de
comando, la frecuencia de control, o el clamp de posicion. Si la curva del
barrido resulta plana, esta es la primera linea de investigacion.

| t4_5m_seed1 | 5 min | 1 | 0.293 | 0.589 | 0.157 | 0.001 | 0/3 | 0.066 |

## AVISO sobre t4_5m_seed1: fila EN CUARENTENA

CoT de 0.066, equivalente a ~2.9 W mecanicos, frente a los ~12 W del run de
15 min a velocidad comandada similar. Sigue vx casi al 98 % pero no gira
(31 %) ni se desplaza lateralmente (0 %).

Inspeccion visual: se levanta, da un par de pasos raros y se queda quieto. El
run de 15 min camina durante todo el rollout. (Que ambos acaben tumbados al
final es el `[PASSIVE] amortiguando` con el que termina el script, no una caida.)

Un robot quieto no puede medir 0.293 m/s. O el cuerpo se desplaza sin que las
patas trabajen, o la medida de velocidad falla. Pendiente de
`tools/inspect_rollout.py`.

NO usar esta fila en ninguna figura hasta resolverlo.

## Implicacion metodologica

El seguimiento de velocidad por si solo NO mide lo que parece. Una politica que
desliza puntua mejor que una que camina: sigue el comando frontal, gasta poca
energia y no se cae. Si esa es la metrica central del barrido, la curva seria
un artefacto, y en el robot real esa politica se caeria o destrozaria los pies.

El evaluador necesita metricas de MARCHA ademas de seguimiento. La primera y
mas barata es la desviacion tipica de la altura del tronco, que se calcula
desde los angulos articulares: si el robot da pasos, oscila; si las patas van
rigidas, es una linea plana.
