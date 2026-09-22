# uc03 — coste de transporte

Masa: 15.0 kg. Locomoción: policy. Modo: sim. Commit: unknown.

| v comandada | v medida | seguimiento | P mec (W) | P elec (W) | CoT mec | CoT elec | h sd |
|---|---|---|---|---|---|---|---|
| 0.10 | 0.019 | 19 % | 4.8 | - | - | - | 0.0045 |
| 0.20 | 0.083 | 41 % | 6.6 | - | 0.544 | - | 0.0052 |
| 0.30 | 0.169 | 56 % | 8.8 | - | 0.355 | - | 0.0061 |
| 0.40 | 0.259 | 65 % | 13.8 | - | 0.362 | - | 0.0073 |
| 0.50 | 0.351 | 70 % | 20.0 | - | 0.387 | - | 0.0086 |
| 0.60 | 0.441 | 74 % | 28.0 | - | 0.431 | - | 0.0099 |
| 0.80 | 0.633 | 79 % | 45.8 | - | 0.492 | - | 0.0121 |

## Limitaciones

En simulacion no hay bms_state: la potencia electrica y el rendimiento salen vacios. La potencia mecanica es una estimacion desde tau_est, que en el robot real tampoco es un par medido con celula de carga.
