# Rendimiento del visor: qué esperar según tu sistema

Resumen: **el visor va fluido en Linux y pesado en Windows y macOS.** No hay
nada que configurar; la diferencia la marca el sistema operativo.

Y lo más importante: **el visor solo hace falta para mirar.** La simulación, el
control y los experimentos van igual de rápido en todos los sistemas.

## Qué usar

| tu sistema | comando | visor |
|---|---|---|
| Linux | `./go2 dev shell` y lanzar el simulador dentro | fluido, usa tu GPU |
| Windows, macOS | `docker compose --profile sim up` | pesado |
| cualquiera, para experimentos | `./go2 sim headless` | ninguno, y va mejor |

## Por qué

El contenedor necesita dibujar en 3D. En Linux puede usar la tarjeta gráfica
del anfitrión a través del perfil `dev`. En Windows y macOS, Docker Desktop
ejecuta los contenedores dentro de una máquina virtual **sin acceso a la GPU
para OpenGL**, así que el dibujado recae en el procesador.

No es algo que falte configurar: ese camino no existe en esos sistemas.

## Medidas

| configuración | renderiza | CPU del contenedor | fluidez |
|---|---|---|---|
| `sim` con noVNC | procesador (llvmpipe) | 406 %, saturada | pesado |
| `dev` con X11 | GPU del anfitrión | libre | fluido |
| `sim --headless` | nada | mínima | sin visor |

MuJoCo renderiza la escena a 188-216 FPS en los dos casos. El cuello no es el
dibujado ni la transmisión: es la CPU saturada haciendo gráficos 3D por
software a la vez que física a 200 Hz.

## ¿Necesito el visor?

| tarea | ¿visor fluido? |
|---|---|
| ejecutar experimentos y recoger métricas | **no**, mejor sin él |
| programar comportamientos y depurar | **no**, se lee la telemetría |
| ver si el robot se cae o camina raro | sí |
| clases y demostraciones | sí |

Las dos primeras son la mayor parte del trabajo.

## Windows: alternativa con GPU (por validar)

Windows 11 incluye WSLg, que da aceleración gráfica a aplicaciones Linux. Si en
lugar de Docker Desktop se instala Docker **dentro** de una Ubuntu de WSL2, el
perfil `dev` podría funcionar con GPU.

Pasos aproximados, PENDIENTES DE VALIDAR:

```powershell
wsl --install -d Ubuntu-22.04
```

Y dentro de esa Ubuntu:

```bash
sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER      # cerrar y reabrir WSL
git clone https://github.com/isoto-mondragon/go2-research.git
cd go2-research
./go2 dev shell
```

Si `glxinfo -B` dentro del contenedor nombra tu tarjeta en lugar de `llvmpipe`,
funciona. Si alguien lo prueba, que lo comunique para documentarlo.

## Para clases y demostraciones

Si hay que enseñar el simulador a un grupo, lo más seguro es hacerlo desde un
portátil con Linux usando `./go2 dev shell`. Es la configuración fluida y
probada.
