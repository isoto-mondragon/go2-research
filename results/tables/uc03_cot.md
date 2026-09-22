# uc03 — coste de transporte

Masa: 15.0 kg. Locomoción: policy. Modo: sim. Commit: f14f4f7.

| v comandada | v medida | seguimiento | P mec (W) | P elec (W) | CoT mec | CoT elec | h sd |
|---|---|---|---|---|---|---|---|
| 0.20 | 0.082 | 41 % | 6.6 | - | 0.551 | - | 0.0052 |
| 0.30 | 0.169 | 56 % | 9.1 | - | 0.363 | - | 0.0061 |
| 0.40 | 0.260 | 65 % | 14.0 | - | 0.366 | - | 0.0073 |
| 0.50 | 0.349 | 70 % | 19.9 | - | 0.387 | - | 0.0087 |
| 0.60 | 0.445 | 74 % | 28.9 | - | 0.442 | - | 0.0098 |
| 0.80 | 0.635 | 79 % | 50.5 | - | 0.540 | - | 0.0120 |

## Limitaciones

En simulacion no hay bms_state: la potencia electrica y el rendimiento salen vacios. La potencia mecanica es una estimacion desde tau_est, que en el robot real tampoco es un par medido con celula de carga.
