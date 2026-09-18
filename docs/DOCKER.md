
## Rendimiento medido (2026-09-18)

Portatil HP ProBook 450 G10, i5-1335U, 16 GB, Intel Iris Xe, sin GPU dedicada.
`run_policy.py --mode sim --publish-hz 200 --duration 30`:

| metrica | distrobox | Docker |
|---|---|---|
| pasos fuera de plazo | 0.0 % | 0.0 % |
| trabajo por paso | 4.34 ms | 1.37 ms |
| inferencia ONNX | ~0.18 ms | 0.04 ms |
| LowCmd real | 200 Hz | 200 Hz |

El contenedor va MEJOR que la instalacion manual: tres veces menos trabajo por
paso. El bucle de control usa el 7 % de su plazo de 20 ms.

La politica se mantiene estable 30 s: inclinacion 1 grado, altura 0.263 m,
par 7.9 Nm constantes.

**La lentitud del visor no afecta al control.** El redibujado va por software
sobre VNC y se nota al hacer zoom o girar la camara, pero la fisica, el DDS y
el bucle de control corren en hilos aparte y tienen el plazo de sobra.
