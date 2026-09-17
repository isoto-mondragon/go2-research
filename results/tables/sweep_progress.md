# Barrido de presupuesto de computo: progreso

Entorno fijado: unitree_rl_mjlab @ 1425b15f, mjlab 1.2.0, mujoco 3.7.0,
mujoco-warp 3.5.0, warp-lang 1.12.1. T4 gratuita, 4096 entornos,
`--agent.seed` activo. Ver `usecases/uc01_locomotion/train/ENTORNO_FIJADO.md`.

Evaluacion: `eval_sim.py` v3, 3 rollouts, escena plana, secuencia fija de 6
segmentos. Las columnas de velocidad son SEGUIMIENTO en % (velocidad medida
por desplazamiento neto / velocidad comandada). `h sd` es la desviacion tipica
de la altura del tronco, que discrimina marcha real de deslizamiento.
Entrenamiento completo estimado: 7 h 30.

| run | min | semilla | vx 0.3 | vx 0.6 | wz 0.5 | vy 0.3 | h sd | CoT 0.3 | caidas | camina |
|---|---|---|---|---|---|---|---|---|---|---|
| t4_5m_seed1  |  5 | 1 |  2 % |  2 % | 69 % |  1 % | 0.0012 |   -   | 0/3 | **NO** |
| t4_15m_seed1 | 15 | 1 | 54 % | 72 % | 52 % | 31 % | 0.0071 | 0.515 | 0/3 | si |

## Pendientes

13 runs: 5, 15, 30, 60 y 120 min x semillas 1, 2, 3 (menos los dos ya hechos).

## Fuera del barrido

| run | vx 0.3 | vx 0.6 | wz 0.5 | vy 0.3 | h sd | CoT 0.3 | camina |
|---|---|---|---|---|---|---|---|
| legacy_wsl2 | 48 % | 66 % | 36 % | 38 % | 0.0067 | 0.707 | si |

Heredada del workspace WSL2: otro commit, otra version de mjlab, presupuesto
incierto. NO es un punto de la curva. Se evalua con el mismo protocolo solo
como referencia historica del punto de partida del proyecto.

## Resultados preliminares

1. **5 minutos de T4 no bastan para aprender a caminar; 15 si.** El run de 5 min
   no obedece los comandos de traslacion (2 % de seguimiento, 0.04 m recorridos
   de 1.80 comandados) y solo gira, deslizando con las patas rigidas
   (h_sd 0.0015, 6.8 W). El de 15 min camina en los cuatro comandos.
   Justifica haber anadido el presupuesto de 5 min al diseno original.

2. **El run de 15 min supera a la politica heredada en las cuatro medidas**
   (54 vs 48 %, 72 vs 66 %, 52 vs 36 %, 31 vs 38 % en lateral) y ademas es mas
   eficiente: CoT 0.515 frente a 0.707. Con la octava parte de computo. No es
   comparacion limpia (distinto codigo), pero indica que la version actual de
   unitree_rl_mjlab aprende bastante mas rapido.

3. **Techo de seguimiento en torno al 50-72 %** en las dos politicas que
   caminan. Que dos entrenamientos distintos converjan a un rango parecido
   apunta a un factor sistematico del DESPLIEGUE, no de la calidad del
   entrenamiento. Candidatos: el cero de `gait_phase` por debajo del umbral de
   comando, la frecuencia de control, o el clamp de posicion. Si la curva del
   barrido sale plana, esta es la primera linea a investigar.

## Incidencias metodologicas resueltas

**Columna mal leida.** La v2 del evaluador imprimia `err vx` (ERROR de
seguimiento) y se confundio con la velocidad medida: un 0.293 de error con
comando 0.3 se leyo como "98 % de seguimiento" cuando significaba lo contrario.
La v3 imprime comando, medido y seguimiento en %, sin columna de error.

**Coste de transporte sesgado.** La v2 calculaba el CoT con la velocidad
COMANDADA en el denominador en vez de la medida, lo que lo subestimaba justo
en las politicas que peor seguian el comando. El run de 5 min salia con CoT
0.066, fisicamente absurdo para 15 kg. La v3 usa la velocidad medida y devuelve
"sin dato" cuando el robot no se mueve.

**Velocidad fragil.** La v2 promediaba diferencias finitas paso a paso, sensible
a cuantas muestras de sportmodestate llegaran. La v3 usa desplazamiento neto
del segmento dividido por su duracion, y compara ambos metodos avisando si
discrepan.

**El seguimiento no basta como metrica.** Una politica que desliza puntua bien,
gasta poca energia y no se cae, y en el robot real se caeria o destrozaria los
pies. El evaluador v3 anade metricas de marcha y emite veredicto de validez,
con umbrales calibrados sobre tres politicas reales: caminan 0.006-0.010,
no camina 0.0005-0.0016, frontera en 0.004.
