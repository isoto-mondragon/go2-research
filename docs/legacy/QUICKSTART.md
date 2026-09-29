# Guía rápida

Del ordenador en blanco a mover el robot en el simulador. Unos 45 minutos, casi
todo esperando a que se construya la imagen.

Funciona en **Linux, Windows y macOS**, con cualquier tarjeta gráfica. No hace
falta NVIDIA ni instalar ROS, Python ni nada: va todo dentro de un contenedor.

---

## 1. Lo que necesitas

- **Docker**, versión 24 o superior
- **Git**
- Unos **10 GB** libres en disco
- Conexión a internet la primera vez

### Instalar Docker

**Linux (Ubuntu / Debian)**

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2 docker-buildx git
sudo usermod -aG docker $USER
```

Después de esto hay que **reiniciar el ordenador**, no basta con cerrar la
terminal: la pertenencia al grupo `docker` solo se aplica en una sesión nueva.

**Windows y macOS**

Instala [Docker Desktop](https://www.docker.com/products/docker-desktop/).
En Windows, elige el motor WSL2 cuando lo pregunte.

### Comprobar que funciona

```bash
docker run --rm hello-world
```

Debe imprimir `Hello from Docker!`. Si dice `permission denied`, en Linux no
has reiniciado tras el `usermod`.

---

## 2. Descargar el proyecto

```bash
git clone git@github.com:isoto-mondragon/go2-research.git
cd go2-research
```

---

## 3. Construir la imagen (solo la primera vez)

```bash
docker compose --profile sim build
```

Entre **20 y 40 minutos**. Compila ROS 2, CycloneDDS y el SDK de Unitree desde
el código fuente.

Hay un tramo de 5-10 minutos en el que apenas imprime nada, mientras compila
CycloneDDS. Es normal, no está colgado.

Al terminar:

```bash
docker images | grep go2-workspace
```

Debe aparecer `go2-workspace 1.0` con unos 6.3 GB.

---

## 4. Arrancar el simulador

```bash
docker compose --profile sim up
```

Esta terminal se queda ocupada. **Déjala abierta.**

Cuando veas `escritorio virtual listo`, abre en el navegador:

**http://localhost:6080/vnc.html** y pulsa **Connect**.

Verás la ventana de MuJoCo con el perro tumbado.

> El visor va lento al girar la cámara o hacer zoom: dibuja por software. **No
> afecta a la simulación**, que corre aparte y a velocidad normal.

---

## 5. Poner el perro de pie

Abre una **terminal nueva** (la anterior está ocupada con el simulador):

```bash
cd go2-research
docker compose --profile sim exec shell bash
```

El prompt cambia a algo como `root@a1b2c3:/workspace#`. **Ya estás dentro del
contenedor.**

Ahora:

```bash
python3 usecases/uc01_locomotion/deploy/run_policy.py --mode sim --duration 60
```

Mira el navegador: el perro se levanta y se mantiene de pie.

---

## 6. Conducirlo con el teclado

Necesitas **tres terminales**: simulador, política y teclado.

**Terminal 1** — el simulador, ya la tienes del paso 4.

**Terminal 2** — la política escuchando el teclado:

```bash
cd go2-research
docker compose --profile sim exec shell bash
python3 usecases/uc01_locomotion/deploy/run_policy.py --mode sim --teleop --duration 300
```

**Terminal 3** — el teclado:

```bash
cd go2-research
docker compose --profile sim exec shell bash
python3 tools/teleop.py --mode sim
```

Controles:

| tecla | acción |
|---|---|
| `W` / `S` | adelante / atrás |
| `A` / `D` | lateral izquierda / derecha |
| `Q` / `E` | girar izquierda / derecha |
| espacio | parar |
| `x` | salir |

Cada pulsación suma 0.1 al comando. Mira el perro en el navegador.

---

## 7. Parar todo

En la terminal del simulador, **Ctrl+C**, y después:

```bash
docker compose --profile sim down
```

---

## Anfitrión o contenedor: la confusión habitual

Casi todos los problemas del primer día son ejecutar un comando en el sitio
equivocado.

| | prompt | ruta |
|---|---|---|
| **anfitrión** (tu ordenador) | `tunombre@tumaquina:~$` | `/home/tunombre/...` |
| **contenedor** | `root@a1b2c3:/workspace#` | `/workspace` |

Si dudas:

```bash
ls /.dockerenv >/dev/null 2>&1 && echo "CONTENEDOR" || echo "ANFITRION"
```

Qué va en cada sitio:

| en el anfitrión | dentro del contenedor |
|---|---|
| `docker compose ...` | `python3 ...` de cualquier herramienta |
| `git` | el simulador |
| editar ficheros | `run_policy.py`, `teleop.py`, `eval_sim.py` |

El repositorio está **montado**, no copiado: si editas un fichero en tu editor,
el cambio se ve dentro del contenedor al instante, sin reconstruir nada.

---

## Problemas frecuentes

**`permission denied ... docker.sock`**
En Linux, falta reiniciar tras `sudo usermod -aG docker $USER`. Reiniciar de
verdad, no solo cerrar la terminal.

**`docker compose build` termina al instante sin hacer nada**
Falta el perfil. Tiene que ser `docker compose --profile sim build`.

**El navegador no muestra nada en el puerto 6080**
Comprueba que el paso 4 sigue corriendo y que dijo `escritorio virtual listo`.
Prueba a recargar y pulsar **Connect**.

**`ModuleNotFoundError: No module named 'numpy'`**
Estás ejecutando en el anfitrión. Entra al contenedor primero (paso 5).

**El perro se cae o se queda tumbado**
Reinicia el simulador: Ctrl+C en la terminal del paso 4 y vuelve a lanzarlo.
Cada ejecución termina amortiguando, y el perro se queda tumbado; es normal.

**Va muy lento**
Cierra otras aplicaciones. El simulador y el visor comparten la CPU. La
lentitud del visor no afecta a la simulación.

---

## Y ahora qué

- Desarrollar casos de uso, conectar el robot real, arquitectura interna:
  [`GUIA_COMPLETA.md`](GUIA_COMPLETA.md)
- Detalles del contenedor y limitaciones conocidas: [`DOCKER.md`](DOCKER.md)
- Antes de tocar el robot físico, **obligatorio**: [`SAFETY.md`](SAFETY.md)
