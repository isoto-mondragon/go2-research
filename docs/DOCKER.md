
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

## Efecto de GO2_GUI=none (2026-09-19)

Mismo portatil, `run_policy.py --mode sim --publish-hz 200 --duration 30`:

| metrica | GUI=novnc | GUI=none |
|---|---|---|
| trabajo por paso | 1.37 ms | 0.84 ms |
| pasos fuera de plazo | 0.0 % | 0.0 % |
| inclinacion en regimen | 1 grado | 0 grados |
| par en reposo | 7.9 Nm | 7.1 Nm |

Un 39 % menos de trabajo por paso. Para experimentos largos y para barridos,
usar siempre `GO2_GUI=none docker compose --profile sim up`.

El cliente VNC nativo en el puerto 5900 no mejora de forma apreciable frente al
navegador en este equipo: el cuello es el renderizado por software, no la
transmision.

## Imagen publicada (2026-09-21)

`ghcr.io/isoto-mondragon/go2-workspace:latest`, publica, unos 6.4 GB.

Instalacion para un usuario nuevo: `git clone`, `docker compose --profile sim
pull`, `docker compose --profile sim up`. Unos 5 minutos en vez de los 20-40
que costaba construirla.

Se reconstruye automaticamente con GitHub Actions al cambiar `docker/`. El
workflow comprueba, sobre la imagen ya publicada, que los imports funcionan y
que la configuracion del simulador es la correcta.

### Commits fijados

Los seis repositorios de Unitree estan anclados. Auditar cualquier contenedor:

    docker run --rm --entrypoint cat \
        ghcr.io/isoto-mondragon/go2-workspace:latest /opt/go2/VERSIONS.txt

Combinacion validada el 2026-09-21:

    unitree_ros2         668d1ec5
    unitree_sdk2         c7538298
    unitree_sdk2_python  65691c8a
    unitree_mujoco       1eb6642e
    rmw_cyclonedds       e370e09c
    cyclonedds           5041f356

Sin fijarlos, dos personas que construyan en dias distintos obtienen imagenes
distintas. No es teorico: tres cambios silenciosos del upstream nos rompieron
la construccion en cuestion de semanas.
