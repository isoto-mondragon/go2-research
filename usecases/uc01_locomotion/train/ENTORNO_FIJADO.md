# Entorno de entrenamiento fijado (Colab T4)

Conjunto de versiones verificado el 2026-09-14. Todos los runs del barrido
usan exactamente este entorno; si no, no son comparables entre si.

| paquete | version | motivo |
|---|---|---|
| unitree_rl_mjlab | 1425b15f73bd4095f0df53709d7c389c3eb9e790 | commit fijado | 
| mjlab | 1.2.0 | lo fija el repo |
| mujoco | 3.7.0 | ultima que conserva `mjENBL_MULTICCD` |
| mujoco-warp | 3.5.0 | de PyPI, NO desde git |
| warp-lang | 1.12.1 | mjlab 1.2.0 usa `wp.context.runtime`, retirado en 1.13 | 
| rsl-rl-lib | 5.0.1 | lo fija mjlab |
| torch | 2.11.0+cu128 | el de Colab |
| Python | 3.13 | el de Colab |

## Por que hace falta fijarlo

`mjlab 1.2.0` declara `mujoco>=3.5.0` sin techo. Con resolucion libre, en
el futuro las versiones nuevas podrian romper el entrenamiento. Fijando estas
versiones nos aseguramos de que el barrido funcione de forma reproducible.
