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

## Comportamiento de Colab con celdas en segundo plano

La celda de entrenamiento lanza el proceso con `Popen` y dos hilos demonio
(`_watchdog` y `_tail`). El codigo sincrono de la celda termina en segundos,
Colab da la celda por finalizada y cierra su stdout. Todo lo que los hilos
impriman despues se pierde: el tick verde aparece enseguida y el mensaje
`terminado (exit=0)` NO llega a verse nunca.

El entrenamiento SI corre correctamente en segundo plano. Para seguirlo:

    !tail -f /tmp/train_output.log        # en una celda aparte
    !ps aux | grep train.py               # comprobar que sigue vivo

La celda de empaquetado detecta el final por si misma, asi que no hay que
esperar a ningun mensaje: se ejecuta cuando han pasado los BUDGET_MIN.

## De donde sale deploy.yaml

`scripts/train.py` solo vuelca `params/env.yaml` y `params/agent.yaml`. NUNCA
escribe `deploy.yaml`. El contrato de despliegue viene en el propio repositorio:

    deploy/robots/go2/config/policy/velocity/v0/params/deploy.yaml

Describe la TAREA (orden de articulaciones, ganancias, action_scale, las 47
observaciones), no el entrenamiento. Las 12 politicas del barrido comparten
tarea y por tanto contrato; entre ellas solo cambian los pesos.

NO sustituirlo por `env.yaml`: tiene otra estructura, y un run empaquetado asi
parece valido pero no lo es.

## Coste de un entrenamiento completo

Con 4096 entornos en T4 gratuita, el entrenamiento completo estima unas 7 h 30.
El barrido de 15 a 120 min cubre del 3 % al 27 % de ese total. La politica
heredada del workspace WSL2 (unas 2 h) corresponde al 27 %.
