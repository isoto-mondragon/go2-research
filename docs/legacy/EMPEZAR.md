# Empezar de cero

Esta guía te lleva desde un ordenador vacío hasta mover un robot cuadrúpedo en
un simulador, en tu pantalla.

No hace falta saber nada de robótica, ni de Docker, ni de Linux. Solo copiar y
pegar comandos.

**Tiempo:** unos 30 minutos, casi todo esperando descargas.

---

## Antes de empezar: la idea en 30 segundos

Trabajar con el robot necesita muchos programas instalados y bien configurados.
Hacerlo a mano lleva días y casi siempre algo falla.

Por eso todo está metido en una **caja** que se descarga ya montada. La caja se
llama contenedor, y dentro está todo listo.

```
   TU ORDENADOR                      LA CAJA (contenedor)
   ─────────────                     ────────────────────
   Escribes el código      ←───→     Ejecutas el código
   con tu editor                     Está el simulador
                                     Están los programas del robot
```

Dos ideas que hay que tener claras:

1. **El código vive en tu ordenador.** Lo editas con tu editor de siempre.
2. **El código se ejecuta dentro de la caja.** Para eso "entras" en ella con un
   comando.

Es como tener un ordenador prestado dentro del tuyo, que ya viene con todo
instalado, y que ve tus ficheros.

---

## Paso 1. Instalar dos programas

Necesitas **Docker** y **Git**. Docker es lo que gestiona la caja. Git es lo que
descarga el proyecto.

### Si tienes Windows o Mac

1. Entra en https://www.docker.com/products/docker-desktop/
2. Descarga **Docker Desktop** para tu sistema
3. Instálalo como cualquier otro programa, dándole a Siguiente
4. **Reinicia el ordenador**
5. Abre Docker Desktop y déjalo abierto en segundo plano

En Windows, si te pregunta, elige la opción **WSL2**.

**Importante para Windows y Mac:** abre Docker Desktop, ve a **Settings**
(el engranaje), luego **Resources**, y sube:
- **CPUs** a 4 o más
- **Memory** a 8 GB o más

Y dale a **Apply & Restart**. Si no lo haces, todo irá muy lento.

### Si tienes Linux (Ubuntu)

Abre una terminal con **Ctrl+Alt+T** y pega esto:

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2 docker-buildx git
sudo usermod -aG docker $USER
```

Y después **reinicia el ordenador**. No vale con cerrar la terminal.

---

## Paso 2. Comprobar que Docker funciona

Abre una terminal:

- **Windows**: busca "PowerShell" en el menú de inicio
- **Mac**: busca "Terminal" con Spotlight (Cmd + Espacio)
- **Linux**: Ctrl+Alt+T

Y escribe esto, seguido de Enter:

```bash
docker run --rm hello-world
```

**Tiene que aparecer** un texto que incluye `Hello from Docker!`.

<details>
<summary>No aparece, ¿y ahora qué?</summary>

- **`permission denied`** (Linux): no has reiniciado después de instalar.
  Reinicia el ordenador.
- **`command not found`** o **`no se reconoce`**: Docker no está instalado, o
  en Windows y Mac no has abierto Docker Desktop.
- **`Cannot connect to the Docker daemon`**: abre Docker Desktop y espera a que
  el icono deje de moverse.
</details>

---

## Paso 3. Descargar el proyecto

En la misma terminal:

```bash
git clone https://github.com/isoto-mondragon/go2-research.git
cd go2-research
```

Esto crea una carpeta llamada `go2-research` con todo el proyecto dentro.

> **`cd go2-research` significa "entrar en esa carpeta".** A partir de ahora
> todos los comandos se ejecutan desde ahí. Si cierras la terminal y abres
> otra, tendrás que volver a escribir `cd go2-research`.

---

## Paso 4. Solo si tienes Linux: un ajuste

Pega esto tal cual:

```bash
echo "UID_GID=$(id -u):$(id -g)" > .env
```

Sirve para que los ficheros que cree la caja sean tuyos y los puedas borrar.

**Si tienes Windows o Mac, sáltate este paso.**

---

## Paso 5. Descargar la caja

```bash
docker compose --profile sim pull
```

Se descargan unos 1.6 GB. Tarda entre 1 y 10 minutos según tu conexión.

Verás muchas líneas con barras de progreso. Es normal. Espera a que vuelva a
aparecer el cursor.

---

## Paso 6. Arrancar el simulador

### Linux (recomendado, va fluido)

```bash
./go2 dev shell
```

y dentro de la caja:

```bash
cd /opt/go2/unitree_mujoco/simulate_python && python3 unitree_mujoco.py
```

Se abre una ventana en el escritorio, con la GPU de tu ordenador. Salta a los
problemas típicos si no se abre.

### Windows y Mac (navegador)

```bash
docker compose --profile sim up
```

**Esta terminal se queda ocupada.** No la cierres: es donde está funcionando el
simulador. Verás texto pasando.

Cuando veas una línea que dice `escritorio virtual listo`, abre tu navegador
(Chrome, Firefox, el que uses) y entra en esta dirección:

**http://localhost:6080/vnc.html**

Aparecerá una pantalla negra con un botón que pone **Connect** o **Conectar**.
Púlsalo.

**Ya está:** estás viendo el robot tumbado en un suelo gris.

> **Va lento y no tiene arreglo:** Docker Desktop no puede usar la tarjeta
> gráfica y el 3D se dibuja por software. No afecta a nada importante. En Linux
> no uses el navegador (satura la CPU al 406 %): usa `./go2 dev shell`.

---

## Paso 7. Entrar en la caja

Ahora vamos a poner el robot de pie. Para eso hay que **entrar en la caja**.

**Abre una terminal NUEVA** (la anterior está ocupada con el simulador):

- **Windows**: otra ventana de PowerShell
- **Mac**: Cmd + N en Terminal
- **Linux**: Ctrl+Alt+T

Y escribe:

En **Linux**:

```bash
cd go2-research
./go2 dev shell
```

En **Windows y Mac**:

```bash
cd go2-research
./go2 dev shell        # Linux; en Windows y Mac: docker compose --profile sim exec shell bash
```

**Mira el principio de la línea.** Ha cambiado:

| dónde estás | lo que pone al principio |
|---|---|
| Tu ordenador | `tunombre@tuordenador:~$` |
| **Dentro de la caja** | `go2@a1b2c3:/workspace$` |

Si pone `go2@` y algo con letras y números, **estás dentro**. Todo lo que
escribas ahora se ejecuta en la caja.

---

## Paso 8. Poner el robot de pie

Ya dentro de la caja, pega esto:

```bash
python3 usecases/uc01_locomotion/deploy/run_policy.py --mode sim --duration 60
```

**Mira el navegador.** El robot se levanta y se queda de pie durante un minuto.

Enhorabuena: acabas de ejecutar tu primer programa de control robótico.

---

## Paso 9. Conducirlo con el teclado

Esto necesita **tres terminales** a la vez. Suena raro, pero tiene sentido: una
para el simulador, otra para el programa que hace caminar al robot, y otra para
el teclado.

**Terminal 1** — el simulador. Ya la tienes del paso 6. No la toques.

**Terminal 2** — ya la tienes del paso 7. Escribe:

```bash
python3 usecases/uc01_locomotion/deploy/run_policy.py --mode sim --teleop --duration 300
```

Espera a ver un mensaje que dice `politica a 50 Hz`.

**Terminal 3** — abre otra terminal nueva y escribe:

```bash
cd go2-research
./go2 dev shell        # Linux; en Windows y Mac: docker compose --profile sim exec shell bash
python3 tools/teleop.py --mode sim
```

Ahora, con esta última terminal seleccionada, usa estas teclas:

| tecla | qué hace |
|---|---|
| `W` | adelante |
| `S` | atrás |
| `A` | a la izquierda |
| `D` | a la derecha |
| `Q` | girar a la izquierda |
| `E` | girar a la derecha |
| barra espaciadora | parar |
| `x` | salir |

Cada vez que pulsas, va un poco más rápido. **Mira el robot en el navegador
mientras pulsas.**

---

## Paso 10. Apagar todo

Cuando termines:

1. En las terminales 2 y 3, escribe `exit` y Enter
2. En la terminal 1, pulsa **Ctrl+C**
3. Y después escribe:

```bash
docker compose --profile sim down
```

La próxima vez, para volver a empezar, solo necesitas:

```bash
cd go2-research
docker compose --profile sim up
```

Ya no hay que descargar nada más.

---

## Lo que tienes que recordar

Solo tres cosas.

### 1. El código está en tu ordenador, se ejecuta en la caja

Si abres la carpeta `go2-research` con tu editor (VS Code, por ejemplo) y
cambias un fichero, **el cambio está dentro de la caja al instante**. No hay
que copiar nada ni volver a descargar nada.

Lo único que hay que hacer es volver a ejecutar el programa dentro de la caja.

### 2. Para ejecutar algo, primero entra en la caja

```bash
cd go2-research
./go2 dev shell        # Linux; en Windows y Mac: docker compose --profile sim exec shell bash
```

Y ya puedes escribir comandos que empiecen por `python3`.

**Si escribes `python3 algo.py` sin haber entrado en la caja, dará error.** Es
el fallo más común del primer día. El error suele decir
`ModuleNotFoundError: No module named 'numpy'`.

### 3. ¿Estoy dentro o fuera?

Si dudas, escribe esto:

```bash
ls /.dockerenv
```

- Si responde `/.dockerenv` → estás **dentro** de la caja
- Si dice que no existe → estás **fuera**, en tu ordenador

---

## Problemas típicos

**"No pasa nada cuando ejecuto `docker compose --profile sim up`"**
Comprueba que estás en la carpeta correcta. Escribe `pwd` y tiene que terminar
en `go2-research`. Si no, escribe `cd go2-research`.

**"El navegador no muestra nada en localhost:6080"**
La terminal 1 tiene que seguir abierta y con el simulador funcionando. Recarga
la página y pulsa Connect otra vez.

**"`ModuleNotFoundError: No module named 'numpy'`"**
No has entrado en la caja. Vuelve al paso 7.

**"El robot se queda tumbado y no se levanta"**
Cada programa termina dejando al robot tumbado. Es normal. Vuelve a ejecutarlo.

**"El simulador va lentísimo en Linux"**
Estás usando el navegador: usa `./go2 dev shell`.

**"Todo va lentísimo"**
En Windows y Mac, sube los recursos de Docker Desktop (paso 1). Cierra otros
programas pesados.

**"He cerrado la terminal sin querer"**
No pasa nada. Abre otra, `cd go2-research`, y vuelve a arrancar con
`docker compose --profile sim up`.

---

## ¿Y ahora qué?

Ya tienes el entorno funcionando. A partir de aquí:

| quiero... | dónde mirar |
|---|---|
| Entender cómo está montado todo | `docs/GUIA_USUARIO.md` |
| Programar mi propio comportamiento | `docs/ESTRATEGIA_CASOS_USO.md` |
| Usar el robot de verdad, no el simulador | `docs/SAFETY.md`, **obligatorio** |
| Ver ejemplos ya hechos | la carpeta `usecases/` |

### Ejemplos que ya funcionan

**El robot mide cuánta energía gasta** según a qué velocidad camina:

```bash
python3 usecases/uc03_energy/eval/measure_cot.py --mode sim
```

**El robot te sigue con una cámara.** Necesita webcam y solo funciona en Linux.
Está explicado en `usecases/uc04_person_following/README.md`.

---

## Si algo no funciona

Escríbeme con:

1. Qué comando ejecutaste, copiado tal cual
2. Qué te respondió, copiado tal cual
3. Qué sistema tienes: Windows, Mac o Linux

Con eso se resuelve casi siempre a la primera.

**Ibon Soto Alsua** · Grupo DANZ
Escuela Politécnica Superior · Mondragon Unibertsitatea
