# uc03 — Coste de transporte

## Pregunta de investigación

¿Cuánta energía gasta el Unitree Go2 por metro recorrido, y cómo depende de la
velocidad?

## Hipótesis

El coste de transporte, `CoT = P / (m·g·v)`, describe una curva en U: alto a
velocidades bajas porque el coste de sostenerse en pie domina, alto a
velocidades altas por el coste aerodinámico e inercial, con un mínimo a una
velocidad intermedia.

Esperamos localizar ese mínimo y compararlo con el de animales cuadrúpedos de
masa similar.

## Por qué es publicable

El CoT es adimensional y por tanto comparable entre robots y entre especies.
Para cuadrúpedos comerciales hay muy pocos datos empíricos publicados: casi
todo lo que existe es simulación o plataformas de laboratorio a medida.

Un barrido medido sobre un Go2 de serie, con protocolo reproducible y
artefacto ejecutable, es un dato citable por sí mismo.

## Qué se mide

| magnitud | fuente | disponible en |
|---|---|---|
| potencia mecánica | suma de \|tau·dq\| de las 12 articulaciones | siempre |
| potencia eléctrica | corriente × voltaje de batería (`bms_state`) | solo robot real |
| velocidad real | desplazamiento neto en régimen | `rt/sportmodestate` |
| calidad de marcha | desviación típica de la altura del tronco | siempre |
| temperatura | por motor | solo robot real |

La comparación entre potencia mecánica y eléctrica da el rendimiento de la
cadena de transmisión, que es un resultado en sí mismo.

## Estado

- [x] Protocolo de medida implementado
- [x] Generación de figuras
- [ ] Barrido en simulación
- [ ] Barrido en robot real con Sport Mode
- [ ] Comparación entre ambos
- [ ] Redacción

## Cómo se ejecuta

Simulación, con el simulador arrancado y desde el contenedor:

```bash
python3 usecases/uc03_energy/eval/measure_cot.py --mode sim
python3 usecases/uc03_energy/eval/plot_cot.py experiments/uc03_energy/<run_id>
```

Robot real con Sport Mode:

```bash
python3 usecases/uc03_energy/eval/measure_cot.py \
    --mode real --iface enp3s0 --locomotion sport
```

## Decisiones de diseño

**Dos motores de locomoción.** En simulación solo hay política RL, porque
unitree_mujoco no emula Sport Mode. En el robot real se prefiere Sport Mode:
es el controlador del fabricante, robusto, y no hay que entrenar nada.

**Con Sport Mode NUNCA se publica LowCmd.** Los dos niveles de control son
excluyentes. Por eso el script usa un suscriptor de solo lectura en ese modo,
en lugar de la capa `LowLevel`.

**Ventana de régimen.** Se descartan los primeros segundos de cada velocidad:
el robot arranca parado y la aceleración contamina el promedio. Misma decisión
que en uc01, y por la misma razón medida allí.

## Limitaciones conocidas

- En simulación no hay `bms_state`: la potencia eléctrica sale vacía.
- `tau_est` es una estimación del firmware, no un par medido con célula de
  carga. Hay que declararlo en cualquier publicación.
- La masa (15 kg) es provisional hasta pesar el robot. Entra directamente en
  el denominador del CoT.
