
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

## Rendimiento del visor: conclusion final (2026-09-21)

### Tres configuraciones, medidas

| configuracion | renderiza | CPU del contenedor | fluidez |
|---|---|---|---|
| `sim` (noVNC) | llvmpipe, en CPU | 406 %, saturada | pesado |
| `dev` (X11 nativo) | GPU del anfitrion | libre | **fluido** |
| `sim --headless` | nada | minima | sin visor |

### El cuello era la CPU

No el renderizado (MuJoCo da 188-216 FPS), ni la transmision (identico con y
sin cliente VNC), ni la tasa de refresco. Era la CPU saturada haciendo
renderizado 3D por software a la vez que fisica a 200 Hz (`SIMULATE_DT=0.005`).

El perfil `dev` lo resuelve sacando el renderizado a la GPU del anfitrion.

### Recomendacion por sistema

| | |
|---|---|
| **Linux, mirando el simulador** | `./go2 dev shell` — GPU real, sin VNC |
| **Windows o macOS** | `docker compose --profile sim up` — noVNC, ira pesado |
| **Cualquiera, experimentando** | `./go2 sim headless` — sin dibujar nada |

En Windows y macOS no hay alternativa: Docker Desktop no puede pasar la GPU
para OpenGL. Es una limitacion del sistema, no del proyecto.

### Callejones sin salida, para que nadie los repita

- Compartir `/dev/dri` con el perfil `sim`: inutil. Ni Xvfb ni Xvnc soportan
  DRI, asi que mesa cae a llvmpipe. `Accelerated: no`, y 1067 FPS con el
  dispositivo frente a 1166 sin el.
- Cliente VNC nativo en el 5900: sin mejora apreciable.
- Bajar la resolucion: marginal.
- Subir VIEWER_DT de 10 a 50 fps: mejora algo, pero con la CPU saturada
  subir a 60 no aporta nada.

### Lo que si aporto

- **Xvnc en lugar de Xvfb + x11vnc**: x11vnc sondea el framebuffer, Xvnc dibuja
  directamente en el.
- **`-noshm`** con x11vnc: Docker aisla los segmentos IPC y el ShmAttach falla
  con BadAccess, matando el proceso en silencio.
- **`GO2_NO_XVFB=1` en `shell`**: comparte namespace con `sim`; si arranca su
  propio servidor X en `:99`, impide que `sim` levante el suyo.
- **`VIEWER_DT = 0.02`** en lugar de 0.1.

### Leccion

Se optimizo durante varias sesiones sin medir donde estaba el cuello. Las dos
medidas que lo resolvieron (FPS de MuJoCo, y `docker stats`) tardaron dos
minutos cada una.

## Validación de reproducibilidad (2026-09-22)

Partiendo de un Docker completamente limpio (`docker system prune -a`, 28 GB
liberados), como haría un usuario nuevo:

| paso | resultado |
|---|---|
| clonar el repositorio | sin claves, repo público |
| `docker compose --profile sim pull` | **1 min 4 s** (6.6 GB en disco) |
| arrancar el simulador | correcto |
| crear uc03 desde cero y medir | correcto |
| crear uc04 con visión y bucle cerrado | correcto |

### Agujeros encontrados y tapados

Ninguno habría aparecido arrancando el simulador y moviendo el robot: solo
salen construyendo algo real encima.

| hallazgo | dónde |
|---|---|
| experimentos registrados sin sha de git | uc03 |
| identificadores de run que colisionaban y sobrescribían datos | uc03 |
| ficheros del volumen propiedad de root | uc03 |
| `.env` con `UID_GID` necesario en Linux y no documentado | instalación |
| `opencv-python-headless` sin interfaz gráfica | uc04 |
| perfil `dev` corriendo como root | uc04 |

### Lo que falta

Que lo pruebe alguien que no sea el autor.
