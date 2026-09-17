# Barrido de presupuesto de computo: progreso

## Entorno

Fijado: unitree_rl_mjlab @ 1425b15f, mjlab 1.2.0, mujoco 3.7.0,
mujoco-warp 3.5.0, warp-lang 1.12.1, rsl-rl-lib 5.0.1. T4 gratuita de Colab,
4096 entornos, `--agent.seed` activo. Detalle y justificacion en
`usecases/uc01_locomotion/train/ENTORNO_FIJADO.md`.

Entrenamiento completo estimado: 7 h 30.

## Protocolo de evaluacion

`eval_sim.py` v3, 3 rollouts, escena plana (`scene_flat.xml`), secuencia fija
de 6 segmentos, `--settle-s 2` (se descartan los 2 s iniciales de cada
segmento, en los que el robot acelera desde parado).

Las columnas de velocidad son SEGUIMIENTO en %: velocidad medida por
desplazamiento neto sobre la ventana de regimen, dividida por la comandada.
`h sd` es la desviacion tipica de la altura del tronco: discrimina marcha real
de deslizamiento con las patas rigidas.

## Resultados

| run | min | semilla | vx 0.3 | vx 0.6 | wz 0.5 | vy 0.3 | media | h sd | CoT 0.3 | caidas | camina |
|---|---|---|---|---|---|---|---|---|---|---|---|
| t4_5m_seed1  |  5 | 1 |  0 % |  2 % | 70 % |  0 % |   -  | 0.0008 |   -   | 0/3 | **NO** |
| t4_5m_seed2  |  5 | 2 |  0 % |  0 % | 55 % |  0 % |   -  | 0.0006 |   -   | 0/3 | **NO** |
| t4_5m_seed3  |  5 | 3 |  0 % |  2 % | 53 % |  0 % |   -  | 0.0013 |   -   | 0/3 | **NO** |
| t4_15m_seed1 | 15 | 1 | 57 % | 73 % | 52 % | 30 % | 53.0 | 0.0069 | 0.549 | 0/3 | si |
| t4_30m_seed1 | 30 | 1 | 48 % | 65 % | 32 % | 36 % | 45.3 | 0.0059 | 0.534 | 0/3 | si |

La columna `media` es el promedio de los cuatro seguimientos. No se calcula
para las politicas que no caminan: promediar un 70 % de giro deslizado con un
0 % de traslacion no significa nada.

## Fuera del barrido

| run | vx 0.3 | vx 0.6 | wz 0.5 | vy 0.3 | media | h sd | CoT 0.3 | camina |
|---|---|---|---|---|---|---|---|---|
| legacy_wsl2 | 52 % | 69 % | 35 % | 39 % | 48.8 | 0.0060 | 0.521 | si |

Heredada del workspace WSL2: otro commit, otra version de mjlab, presupuesto
incierto (unas 2 h). NO es un punto de la curva. Se evalua con el mismo
protocolo solo como referencia historica del punto de partida del proyecto.

## Pendientes

Inmediato, para poder concluir algo:
  t4_15m_seed2, t4_15m_seed3, t4_30m_seed2, t4_30m_seed3   (90 min de GPU)

Despues, solo si la dispersion lo justifica:
  60 y 120 min x 3 semillas                                (9 h de GPU)

## Resultados establecidos

**1. Cinco minutos de T4 no bastan para aprender a caminar. n=3, sin excepcion.**

Las tres semillas fallan igual: 0-2 % de seguimiento en traslacion (frontal y
lateral), `h_sd` entre 0.0006 y 0.0013 frente a 0.006-0.010 de una marcha real.
Lo unico que aprenden es a girar sobre si mismas, y lo hacen deslizando con las
patas practicamente rigidas (53-70 % de seguimiento en `wz`, 3-7 W de potencia).

Que el giro se aprenda antes que la traslacion es un hallazgo secundario
interesante: pivotar no exige coordinar una marcha.

**2. Entre 15 y 120 minutos no se distingue nada con los datos actuales.**

Las tres politicas que caminan dan medias de 45.3, 48.8 y 53.0, y CoT de 0.534,
0.521 y 0.549. El de 15 min gana en `vx` y `wz` pero pierde en `vy`; el de
30 min y la heredada van al reves. Eso parece reparto distinto de la misma
capacidad (optimos locales) mas que niveles de competencia distintos.

CONCLUSION PENDIENTE DE REPLICAS. Con n=1 en 15 y 30 min no se puede separar
efecto del presupuesto de dispersion entre semillas.

## Hipotesis abierta: techo de seguimiento

Las tres politicas que caminan se quedan entre el 48 % y el 73 %. Se descarto
que fuera artefacto de medida: la ventana de regimen solo aporto 4-5 puntos y
el techo persiste.

Que politicas entrenadas con codigo distinto y presupuestos entre 15 min y 2 h
converjan al mismo rango apunta a un factor sistematico del DESPLIEGUE, no de
la calidad del entrenamiento. Candidatos por investigar:
  - el cero de `gait_phase` por debajo del umbral de norma de comando
  - la frecuencia de control (50 Hz de politica, 200-500 Hz de LowCmd)
  - el clamp de posicion `q_delta_max`
  - diferencias entre el entorno de entrenamiento (mjlab) y unitree_mujoco

Si el barrido confirma que la curva es plana por encima de 15 min, esta pasa a
ser la linea principal de investigacion: el cuello de botella no seria el
computo.

## Cambio de protocolo: ventana de regimen (2026-09-17)

Todas las medidas se toman descartando los primeros 2 s de cada segmento. El
robot arranca parado en cada uno y la fase de aceleracion penalizaba el
promedio.

Efecto medido sobre t4_15m_seed1, mismo run y mismo simulador:

| segmento | sin ventana | con 2 s |
|---|---|---|
| vx 0.3 | 55 % | 60 % |
| vx 0.6 | 71 % | 75 % |
| wz 0.5 | 51 % | 52 % |
| vy 0.3 | 32 % | 32 % |

El transitorio valia 4-5 puntos, y solo en traslacion frontal: el giro y el
lateral no tienen fase de aceleracion apreciable.

Efectos colaterales, ambos correctos:
- Los segmentos de reposo pasan de h_sd ~0.007 a ~0.0001. Antes arrastraban los
  coletazos del segmento anterior; ahora miden reposo de verdad.
- El CoT baja: la misma energia sobre una velocidad mayor.

Los cinco runs y la politica heredada se remidieron con la ventana. No mezclar
valores con y sin ventana en la misma tabla.

## Sesgos de medida detectados y corregidos

Cuatro, cada uno con el dato que lo destapo:

1. **Columna de error leida como medida.** La v2 imprimia `err vx`; un 0.293 de
   error con comando 0.3 se leyo como "98 % de seguimiento" cuando significaba
   lo contrario. La v3 imprime comando, medido y seguimiento, sin columna de
   error.
2. **CoT con velocidad comandada.** Se calculaba con la comandada en el
   denominador, lo que lo subestimaba justo en las politicas que peor seguian
   el comando. El run de 5 min salia con CoT 0.066, absurdo para 15 kg.
3. **Velocidad por diferencias finitas.** Sensible a cuantas muestras de
   `sportmodestate` llegaran. Sustituida por desplazamiento neto sobre la
   ventana, con comprobacion cruzada entre ambos metodos.
4. **Transitorio de aceleracion.** Ver seccion anterior.

Ninguno se habria visto sin contrastar politicas muy distintas con el mismo
protocolo. El seguimiento de velocidad por si solo no basta como metrica: una
politica que desliza puntua bien, gasta poca energia y no se cae, y en el robot
real se caeria o destrozaria los pies.
