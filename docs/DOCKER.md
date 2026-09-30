# El contenedor por dentro

> **Para quién:** quien quiere entender o ajustar el contenedor: puertos,
> variables, rendimiento del visor, versiones fijadas.
> **Cuándo:** cuando la [`GUIA.md`](GUIA.md) se te queda corta. Para usar el
> proyecto no hace falta leerlo.

## Perfiles

| perfil | para qué | robot real | ventana |
|---|---|---|---|
| `sim` | uso normal, cualquier sistema operativo | no | navegador o VNC |
| `real` | robot físico | sí, **solo Linux** | no |
| `dev` | ventana nativa con la GPU, **solo Linux** | sí | X11 |

El perfil `sim` levanta **dos** contenedores: `sim` (el simulador y su escritorio
virtual) y `shell` (tu terminal). `shell` comparte la red de `sim`, y por eso
`GO2_NO_XVFB=1`: si arrancara su propio servidor X en `:99`, impediría que `sim`
levante el suyo.

El robot real solo funciona desde Linux porque necesita `network_mode: host`
para el DDS por Ethernet, y Docker Desktop no lo ofrece.

## Puertos

| puerto | para qué | cómo se usa |
|---|---|---|
| **6080** | simulador en el navegador (noVNC) | `http://localhost:6080/vnc.html` |
| **5900** | VNC nativo | conectar a `localhost:5900`, sin contraseña |

No hay más puertos abiertos.

## Ficheros

El repositorio está **montado**, no copiado: `~/go2-research` en tu ordenador es
`/workspace` en el contenedor. Lo que guardes en `/workspace` persiste; lo que
escribas fuera desaparece al parar el contenedor.

| ruta | contenido |
|---|---|
| `/workspace` | el repositorio |
| `/opt/go2/` | dependencias de Unitree |
| `/opt/go2/unitree_mujoco/` | el simulador |
| `/opt/go2/unitree_ros2/` | mensajes ROS 2 y CycloneDDS |

## Variables de entorno

| variable | valores | para qué |
|---|---|---|
| `GO2_MODE` | `sim` / `real` | destino |
| `GO2_IFACE` | `lo` / `enp3s0`... | interfaz de red |
| `GO2_DOMAIN` | `1` (sim) / `0` (real) | dominio DDS; separados a propósito |
| `GO2_GUI` | `novnc` / `x11` / `none` | escritorio |
| `GO2_RES` | `1280x800x24` | resolución del escritorio |

Tres cosas dependen de **cada ordenador** y por eso no se copian de un
compañero: el nombre de la interfaz (`GO2_IFACE`), los GID de los grupos
`render` y `video`, y qué `/dev/video*` existen. De eso se ocupan
`tools/gen_linux_override.py` y las comprobaciones de `tools/doctor.py`.

## Canales DDS

| topic | dirección | contenido |
|---|---|---|
| `rt/lowstate` | robot → tú | IMU, 12 articulaciones, fuerza en los pies, batería. 200 Hz en simulación, 500 Hz en el robot real |
| `rt/lowcmd` | tú → robot | comandos articulares (bajo nivel) |
| `rt/wirelesscontroller` | tú → simulador | velocidades, como el mando. Lo consume `run_policy.py --teleop`. Para el robot real, ver [`API.md`](API.md) |

En simulación no hay `bms_state`, `foot_force` ni temperatura: salen a cero.

---

# Rendimiento del visor

**El visor va fluido en Linux y pesado en Windows y macOS.** No hay nada que
configurar: lo marca el sistema operativo. Y el visor **solo hace falta para
mirar**: la simulación, el control y los experimentos van igual de rápido en
todos los sistemas.

| tu sistema | comando | visor |
|---|---|---|
| Linux | `./go2 dev shell` y lanzar el simulador dentro | fluido, usa tu GPU |
| Windows, macOS | `docker compose --profile sim up` | pesado |
| cualquiera, para experimentos | `./go2 sim headless` | ninguno, y va mejor |

En Windows, `./go2` no existe en PowerShell; sin visor, el equivalente es
`$env:GO2_GUI="none"; docker compose --profile sim up`.

## Medidas

| configuración | renderiza | CPU del contenedor | fluidez |
|---|---|---|---|
| `sim` (noVNC) | procesador (llvmpipe) | 406 %, saturada | pesado |
| `dev` (X11 nativo), Linux | GPU del anfitrión | libre | **fluido** |
| `sim` sin visor (`GO2_GUI=none`) | nada | mínima | sin imagen |

**El cuello era la CPU.** No el renderizado (MuJoCo da 188-216 FPS), ni la
transmisión (idéntico con y sin cliente VNC), ni la tasa de refresco. Era la CPU
saturada haciendo gráficos 3D por software a la vez que física a 200 Hz
(`SIMULATE_DT=0.005`). El perfil `dev` lo resuelve sacando el dibujado a la GPU
del anfitrión.

**Con Docker Desktop no tiene arreglo:** ejecuta los contenedores en una máquina
virtual sin acceso a la GPU para OpenGL. No es un fallo del proyecto. Hay una vía
posible (Docker dentro de WSL2) **sin verificar**: ver la sección de Windows en
[`GUIA.md`](GUIA.md), parte 3.

## ¿Necesito el visor?

| tarea | ¿visor fluido? |
|---|---|
| ejecutar experimentos y recoger métricas | **no**, mejor sin él |
| programar comportamientos y depurar | **no**, se lee la telemetría |
| ver si el robot se cae o camina raro | sí |
| clases y demostraciones | sí, desde un portátil con Linux |

## La lentitud del visor no afecta al control

Portátil HP ProBook 450 G10 (i5-1335U, 16 GB, Intel Iris Xe, sin GPU dedicada),
`run_policy.py --mode sim --publish-hz 200 --duration 30`:

| métrica | distrobox | Docker | Docker, `GO2_GUI=none` |
|---|---|---|---|
| pasos fuera de plazo | 0.0 % | 0.0 % | 0.0 % |
| trabajo por paso | 4.34 ms | 1.37 ms | 0.84 ms |
| LowCmd real | 200 Hz | 200 Hz | — |

El contenedor va mejor que la instalación manual, y quitar el visor recorta otro
39 % el trabajo por paso. El bucle de control usa el 7 % de su plazo de 20 ms.
Para experimentos largos y barridos, usa siempre `GO2_GUI=none`.

## Callejones sin salida, para que nadie los repita

- Compartir `/dev/dri` con el perfil `sim`: inútil. Ni Xvfb ni Xvnc soportan DRI,
  así que mesa cae a llvmpipe. `Accelerated: no`, y 1067 FPS con el dispositivo
  frente a 1166 sin él.
- Cliente VNC nativo en el 5900: sin mejora apreciable.
- Bajar la resolución: marginal.
- Subir `VIEWER_DT` de 10 a 50 fps mejora algo; con la CPU saturada, subir a 60
  no aporta nada.

Lo que sí aportó: **Xvnc** en lugar de Xvfb + x11vnc (dibuja directamente en el
framebuffer en vez de sondearlo), **`-noshm`** con x11vnc (Docker aísla los
segmentos IPC y `ShmAttach` fallaba con `BadAccess`, matando el proceso en
silencio) y **`VIEWER_DT = 0.02`** en lugar de 0.1.

**Lección:** se optimizó durante varias sesiones sin medir dónde estaba el
cuello. Las dos medidas que lo resolvieron (FPS de MuJoCo y `docker stats`)
tardaron dos minutos cada una.

---

# La imagen

`ghcr.io/isoto-mondragon/go2-workspace:latest`, pública, unos 6.4 GB. Instalación
para un usuario nuevo: `git clone`, `docker compose --profile sim pull`,
`docker compose --profile sim up`. Unos 5 minutos en vez de los 20-40 que costaba
construirla.

Se reconstruye automáticamente con GitHub Actions al cambiar `docker/`. El
workflow comprueba, sobre la imagen ya publicada, que los imports funcionan y que
la configuración del simulador es la correcta.

## Commits fijados

Los seis repositorios de Unitree están anclados. Para auditar cualquier
contenedor:

    docker run --rm --entrypoint cat \
        ghcr.io/isoto-mondragon/go2-workspace:latest /opt/go2/VERSIONS.txt

Combinación validada el 2026-09-21:

    unitree_ros2         668d1ec5
    unitree_sdk2         c7538298
    unitree_sdk2_python  65691c8a
    unitree_mujoco       1eb6642e
    rmw_cyclonedds       e370e09c
    cyclonedds           5041f356

Sin fijarlos, dos personas que construyan en días distintos obtienen imágenes
distintas. No es teórico: tres cambios silenciosos del upstream nos rompieron la
construcción en cuestión de semanas.

## Validación de reproducibilidad (2026-09-22)

Partiendo de un Docker completamente limpio (`docker system prune -a`, 28 GB
liberados), como haría un usuario nuevo: clonar (sin claves, repo público),
`docker compose --profile sim pull` (**1 min 4 s**, 6.6 GB en disco), arrancar el
simulador, y crear uc03 y uc04 desde cero. Todo correcto, en Linux.

Ninguno de los agujeros que aparecieron habría salido arrancando el simulador y
moviendo el robot: solo salen construyendo algo real encima. Se encontraron y
taparon experimentos registrados sin sha de git, identificadores de run que
colisionaban, ficheros del volumen propiedad de root, `UID_GID` necesario en
Linux y no documentado, `opencv-python-headless` sin interfaz gráfica y el perfil
`dev` corriendo como root.

**Lo que falta:** que lo pruebe alguien que no sea el autor, y en Windows y Mac.
