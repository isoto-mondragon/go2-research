# Linea base: politica heredada (Colab T4, ~2 h), simulacion

Entorno: unitree_mujoco, escena plana (scene_flat.xml), domain 1, lo.
3 rollouts, secuencia fija de 6 segmentos, 30 s cada uno.
Masa asumida 15.0 kg (PROVISIONAL: pesar el robot al recibirlo).

| comando | medido | seguimiento | CoT |
|---|---|---|---|
| vx 0.3 m/s  | 0.151 | 50 % | 0.255 |
| vx 0.6 m/s  | 0.403 | 67 % | 0.380 |
| vy 0.3 m/s  | 0.112 | 37 % | 0.344 |
| wz 0.5 rad/s| 0.178 | 36 % | -    |

Caidas: 0/3. Dispersion entre rollouts: < 0.003 m/s.

El seguimiento parcial es sistematico y reproducible, no ruido. Es la
variable que el barrido de presupuesto de computo debe explicar.
