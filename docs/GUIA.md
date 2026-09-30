# Guía completa: del ordenador vacío al robot siguiéndote

> **Para quién:** cualquiera, aunque nunca hayas usado Docker ni Linux.
> **Cuándo:** es el primer documento que abres. Empieza aquí.

Esta es la única guía que necesitas. Está pensada para quien **nunca ha usado
Docker ni Linux**: puedes copiar y pegar cada comando sin entender qué hace.

Al terminar habrás pasado por cinco partes:

| parte | qué haces | sistema |
|---|---|---|
| 1 | Instalar Docker y Git, descargar el proyecto | todos |
| 2 | Ajustes que dependen de tu ordenador | **solo Linux** |
| 3 | Ver el simulador y mover el robot virtual | todos |
| 4 | Conectar el robot de verdad | **solo Linux** |
| 5 | Que el robot te siga con su cámara | **solo Linux** |

### Dónde acaba el camino común y dónde empieza el de Linux

| | Windows | Mac | Linux |
|---|:-:|:-:|:-:|
| Parte 1: instalar y descargar | sí | sí | sí |
| Parte 2: ajustes del ordenador | **no** | **no** | sí |
| Parte 3: el simulador | sí (visor lento) | sí (visor lento) | sí (visor fluido) |
| Parte 4: conectar el robot | **no** | **no** | sí |
| Parte 5: que el robot te siga | **no** | **no** | sí |

**Si tienes Windows o Mac, la guía termina al final de la parte 3.** Las partes
2, 4 y 5 usan comandos de Linux (`./env/go2_net.sh`, `ip`, `sudo`...) que no
existen en tu ordenador, y el robot físico necesita acceso directo a la red,
que Docker Desktop no da. Es una limitación de Docker Desktop, no del proyecto.

Lo único que escribes **fuera** de la caja en Windows y Mac es:

1. instalar Docker y Git,
2. `git clone`,
3. `docker compose --profile sim pull`,
4. `docker compose --profile sim up`,
5. `docker compose --profile sim exec shell bash` (para entrar en la caja).

No necesitas instalar Python ni nada más. Todo lo demás se hace dentro.

Cómo leerla: cada paso dice **qué escribir** y **qué tiene que pasar**. Si lo que
ves no coincide con lo que dice la guía, **para** y mira la
[tabla de problemas](#problemas-y-soluciones) antes de seguir.

---

## Antes de empezar: la idea más importante

Todo el software del proyecto vive dentro de una **caja** (un *contenedor*).
Tu ordenador no tiene instalado Python, ni las bibliotecas, ni nada: están en la
caja. Por eso hay **dos lugares** donde puedes escribir comandos:

| lugar | cómo lo reconoces | qué se hace aquí |
|---|---|---|
| **FUERA** de la caja (tu ordenador) | la línea empieza por `tunombre@tuordenador:~/go2-research$` | `git` y `docker` (todos los sistemas); `./go2`, `./env/...` y `tools/doctor.py` (**solo Linux**) |
| **DENTRO** de la caja | la línea empieza por `go2@` (o `root@`) seguido de letras y números | todo lo que empieza por `python3 tools/...` o `python3 usecases/...` |

**Regla de oro:** los programas del robot (`python3 usecases/...`,
`python3 tools/teleop.py`...) **solo funcionan dentro de la caja**. Si los
ejecutas fuera verás:

```text
ModuleNotFoundError: No module named 'numpy'
```

Ese error **no significa que falte instalar numpy**. Significa que estás fuera
de la caja. Entra en ella (cada parte te dice cómo) y repite el comando.

Excepción, **solo en Linux**: `python3 tools/doctor.py` y
`python3 tools/gen_linux_override.py` se ejecutan **fuera** (Linux ya trae
Python). En Windows y Mac no hace falta ninguno de los dos. Cada vez que la guía
te pida algo así, lo dirá.

A lo largo de la guía verás estas etiquetas:

- 🖥️ **FUERA**: en tu ordenador
- 📦 **DENTRO**: en la caja

---

# PARTE 1. Instalar y descargar (todos)

Necesitas unos 10 GB libres en disco y conexión a internet.

## 1.1 Instalar Docker y Git

**Linux (Ubuntu / Debian).** 🖥️ FUERA:

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2 docker-buildx git
sudo usermod -aG docker $USER
```

Te pedirá tu contraseña (al escribirla no se ve nada, es normal).

Después **reinicia el ordenador**. No basta con cerrar la terminal: el permiso
para usar Docker solo se aplica al iniciar sesión de nuevo.

**Windows.** Instala [Docker Desktop](https://www.docker.com/products/docker-desktop/)
y [Git](https://git-scm.com/download/win). Cuando Docker Desktop pregunte,
elige el motor **WSL2**. Reinicia si te lo pide. Los comandos de la guía se
escriben en **PowerShell**.

**Mac.** Instala [Docker Desktop](https://www.docker.com/products/docker-desktop/).
Git viene con las herramientas de desarrollo: si escribes `git` y te ofrece
instalarlas, acepta. Los comandos se escriben en la aplicación **Terminal**.

> **Mac con chip Apple (M1, M2...):** la imagen del proyecto está construida
> para procesadores Intel/AMD. Docker Desktop puede ejecutarla emulada, pero
> **no lo hemos probado**. Si lo intentas, cuéntanos cómo va.

Abre Docker Desktop y espera a que el icono deje de moverse antes de seguir.

## 1.2 Comprobar que Docker funciona (opcional)

Sirve para saber que Docker funciona antes de bajar 6 GB. 🖥️ FUERA:

```bash
docker run --rm hello-world
```

**Qué tiene que pasar:** tras unos segundos aparece un texto que incluye
`Hello from Docker!`.

Si en Linux dice `permission denied`, no has reiniciado tras el paso anterior.

## 1.3 Descargar el proyecto

🖥️ FUERA:

```bash
git clone https://github.com/isoto-mondragon/go2-research.git
cd go2-research
```

**Qué tiene que pasar:** se crea una carpeta `go2-research` y te metes en ella.

> **`cd go2-research` significa "entrar en esa carpeta".** Todos los comandos
> de la guía se escriben desde ahí. Si cierras la terminal y abres otra, vuelve
> a escribir `cd go2-research` (desde la carpeta donde lo descargaste).

## 1.4 Descargar la caja

🖥️ FUERA:

```bash
docker compose --profile sim pull
```

**Qué tiene que pasar:** varias líneas con barras de progreso durante 1 a 10
minutos (unos 6 GB). Termina cuando vuelve a aparecer el cursor. Es normal que
parezca que no avanza en algunos momentos.

---

# PARTE 2. Ajustes de tu ordenador (solo Linux)

> **Windows y Mac: salta a la parte 3.**

**Esta parte no es opcional.** Tres cosas cambian de un ordenador a otro: el
nombre de la conexión de red (`enp3s0`, `enp4s0`, `eno1`...), los números de
los grupos de permisos, y qué dispositivos de vídeo existen. Si se copian de
otro ordenador aparecen errores como `does not match an available interface` o
`Unable to find group render`.

## 2.1 Detectar los valores solos

No tienes que editar nada: estos comandos miran tu ordenador y escriben los
valores correctos. 🖥️ FUERA, dentro de la carpeta `go2-research`:

```bash
cd go2-research
echo "UID_GID=$(id -u):$(id -g)" > .env
IFACE=$(ip -br link | awk '$1 ~ /^e/ && $1 !~ /docker|veth|br-/ {print $1; exit}')
echo "GO2_IFACE=${IFACE:-enp3s0}" >> .env
python3 tools/gen_linux_override.py --write
```

**Qué tiene que pasar:** no imprimen errores. El último comando escribe un
fichero `docker-compose.linux.yml` y cuenta qué ha detectado.

Para ver el resultado:

```bash
cat .env
```

Debe mostrar dos líneas parecidas a:

```text
UID_GID=1000:1000
GO2_IFACE=enp3s0
```

> **⚠️ El nombre de la conexión (`GO2_IFACE`) es el de TU ordenador.** Puede
> ser `enp3s0`, `enp4s0`, `eno1`, `enx...`. **No copies `enp3s0` a ciegas de esta
> guía ni de un compañero.** Si tu ordenador no tiene conexión Ethernet ahora
> mismo, el comando pondrá `enp3s0` como valor provisional: no pasa nada si
> solo vas a usar el simulador, y lo corregirás en la parte 4.

## 2.2 Puerta de comprobación número 1

🖥️ FUERA:

```bash
python3 tools/doctor.py
```

Revisa tu ordenador y te dice, con colores, qué está bien (`[ok]`), qué es un
aviso (`[--]`) y qué es un problema (`[XX]`).

**Qué tiene que pasar:** al final aparece

```text
TODO CORRECTO
```

> **🛑 No sigas hasta que salga `TODO CORRECTO`.** Cada problema `[XX]` lleva
> debajo su arreglo, con el comando exacto. Puedes probar
> `python3 tools/doctor.py --fix`: aplica solo los arreglos que puede, y **te
> dice en voz alta los que no** (por ejemplo los que llevan `sudo`), que tendrás
> que escribir tú. Vuelve a ejecutar `doctor.py` hasta que salga `TODO CORRECTO`.

Es normal que salgan **avisos** (`[--]`). Por ejemplo, si no tienes el robot
conectado verás `no tiene cable conectado`: sin robot eso no es un problema.
Los avisos no bloquean, solo los `[XX]`.

---

# PARTE 3. El simulador (todos)

Un robot virtual en tu pantalla. Aquí puedes equivocarte sin consecuencias.

## 3.1 Arrancar el simulador

### Linux: ventana nativa (va fluido)

🖥️ FUERA:

```bash
./go2 dev shell
```

**Qué tiene que pasar:** el principio de la línea cambia: ahora estás
**📦 DENTRO** de la caja. Escribe:

```bash
cd /opt/go2/unitree_mujoco/simulate_python && python3 unitree_mujoco.py
```

**Qué tiene que pasar:** se abre una **ventana** con un robot tumbado en un
suelo gris. Esta terminal se queda ocupada mientras el simulador funciona: no
la cierres.

Si no se abre ninguna ventana, mira la tabla de problemas
(`cannot connect to X server`).

### Windows y Mac: navegador (va lento)

🖥️ FUERA:

```bash
docker compose --profile sim up
```

Esta terminal se queda ocupada. Cuando veas una línea con
`escritorio virtual listo`, abre el navegador en:

**http://localhost:6080/vnc.html**

Pulsa **Connect**. **Qué tiene que pasar:** ves el robot tumbado en un suelo
gris.

> **Aviso: va a ir lento.** Sobre todo al mover la cámara con el ratón. Está
> medido: la CPU del contenedor se satura al 406 % porque dibuja el 3D por
> software y lo transmite por VNC. **Con Docker Desktop esto no tiene arreglo**:
> no es un fallo del proyecto, es que Docker Desktop no da acceso a la tarjeta
> gráfica. No afecta a la física ni al control: el robot se mueve igual de bien,
> solo se ve peor. En Linux se evita usando la ventana nativa.
>
> Si en Windows 11 quieres probar una vía que podría ir fluida, mira la sección
> siguiente. **Nadie la ha probado todavía.**

### Windows: ventana nativa con WSL2 (⚠️ NO VERIFICADA)

> **⚠️ NADIE HA PROBADO ESTO TODAVÍA.** No es el camino recomendado. El camino
> recomendado en Windows es el navegador de arriba. Si lo intentas, **cuéntanos
> qué ha pasado** (funcione o no): así podremos dejar aquí la respuesta.

**La idea.** Windows 11 trae *WSLg*, que da aceleración gráfica a las
aplicaciones Linux. Si en lugar de Docker Desktop usas Docker **dentro** de una
Ubuntu de WSL2, el perfil `dev` (ventana nativa) podría funcionar con GPU,
igual que en Linux.

Pasos aproximados. En PowerShell:

```powershell
wsl --install -d Ubuntu-22.04
```

Reinicia si te lo pide, abre **Ubuntu** desde el menú Inicio y crea tu usuario.
Dentro de esa Ubuntu ya estás en un Linux: **sigue esta guía como si fueras
Linux**, empezando en la parte 1 (rama de Linux) y sin usar Docker Desktop.
Clona el proyecto dentro de tu carpeta personal de Ubuntu (`~`), no en `/mnt/c`.
Para el simulador, usa `./go2 dev shell` como en el apartado de Linux.

**Cómo saber si funciona.** Dentro del contenedor (📦):

```bash
glxinfo -B
```

Si nombra tu tarjeta gráfica, funciona. Si dice `llvmpipe`, sigue dibujando por
software y no has ganado nada.

**Posibles obstáculos, sin comprobar.** Es posible que el contenedor no vea la
GPU de WSLg, porque en WSL2 no se accede a ella por `/dev/dri` sino por otros
dispositivos que el proyecto no comparte. Si es así, la solución no está aquí
todavía. El robot físico sigue sin estar soportado en Windows.

## 3.2 Entrar en la caja (segunda terminal)

Necesitas una **terminal nueva** (la primera está ocupada con el simulador):

- **Windows**: otra ventana de PowerShell
- **Mac**: `Cmd + N` en Terminal
- **Linux**: `Ctrl + Alt + T`

**Linux** 🖥️ FUERA:

```bash
cd go2-research
./go2 dev shell
```

**Windows y Mac** 🖥️ FUERA (en Windows, en PowerShell):

```bash
cd go2-research
docker compose --profile sim exec shell bash
```

**Qué tiene que pasar:** la línea empieza por `go2@` y letras y números. Ya
estás **📦 DENTRO**.

## 3.3 Poner el robot de pie

📦 DENTRO:

```bash
python3 usecases/uc01_locomotion/deploy/run_policy.py --mode sim --duration 60
```

**Qué tiene que pasar:** en el simulador el robot **se levanta** y se queda de
pie durante un minuto. Después el programa termina.

Si sale `ModuleNotFoundError: No module named 'numpy'`: estás fuera de la caja.
Repite el paso 3.2.

## 3.4 Conducirlo con el teclado (tres terminales)

Hacen falta **tres** terminales a la vez: una para el simulador, otra para el
programa que hace caminar al robot y otra para el teclado.

**Terminal 1**: el simulador, ya arrancado en 3.1. No la toques.

**Terminal 2** 📦 DENTRO (entra como en 3.2):

```bash
python3 usecases/uc01_locomotion/deploy/run_policy.py --mode sim --teleop --duration 300
```

**Qué tiene que pasar:** el robot se levanta y aparece un mensaje con
`politica a 50 Hz`. Espera a verlo antes de continuar.

**Terminal 3**: terminal nueva, entra en la caja igual que en 3.2 y escribe:

```bash
python3 tools/teleop.py --mode sim
```

Con esta terminal seleccionada, usa el teclado:

| tecla | qué hace |
|---|---|
| `W` / `S` | adelante / atrás |
| `A` / `D` | izquierda / derecha |
| `Q` / `E` | girar izquierda / derecha |
| barra espaciadora | parar |
| `x` | salir |

**Qué tiene que pasar:** el robot del simulador se mueve mientras pulsas. Cada
pulsación aumenta un poco la velocidad.

## 3.5 Apagar el simulador

1. En las terminales 2 y 3: `Ctrl + C` si algo sigue corriendo, y luego `exit`
   (esto te saca de la caja).
2. En la terminal 1: `Ctrl + C`.
3. En Windows y Mac, además, 🖥️ FUERA: `docker compose --profile sim down`

La próxima vez solo tienes que repetir 3.1: no hay que descargar nada más.

---

# PARTE 4. Conectar el robot físico (solo Linux)

> **Windows y Mac: la guía termina en la parte 3.** El robot físico necesita
> acceso directo a la red, que Docker Desktop no da.

## 4.0 Seguridad: léelo antes de tocar nada

Un robot de 15 kg que se mueve puede hacer daño y hacérselo a sí mismo. Cuatro
reglas cortas, **siempre**:

1. **Mando siempre en la mano.** `L2` + `B` para el robot al instante.
2. **Dos metros libres** alrededor del robot. **Cinco** cuando vaya a caminar.
3. **Batería por encima del 50 %.**
4. **App del móvil cerrada del todo**, no en segundo plano. Si está abierta
   pelea con el ordenador por el control del robot.

**Antes de tocar el ordenador, practica `L2` + `B` tres veces** con el robot
encendido y de pie: mantén `L2` pulsado, pulsa `B`, el robot se amortigua y se
tumba. Es lo que harás si algo va mal. Cortar el programa del ordenador **no**
detiene al robot por sí solo.

Y una regla de método: **toda acción con el robot va precedida de su versión
`--dry-run`**, que hace todo menos mover el robot.

### Lo que va a parecer raro (y no es un fallo)

- **El robot se dobla o se tumba al arrancar un programa.** Es su forma de
  tomar el control: se agacha y luego se levanta.
- **Cada programa termina dejando al robot tumbado o amortiguado.** Es a
  propósito: es la postura segura. Para el siguiente programa se volverá a
  levantar.
- **A velocidades bajas va a tirones o se queda quieto.** El controlador del
  fabricante ignora las órdenes por debajo de unos 0.2 m/s. No lo has roto.
- **La cámara del robot no ve caras.** Está a 30 cm del suelo y apunta al
  frente: ve piernas y torso. Además es de ojo de pez y deforma los bordes.
- **Los programas de la parte 3 no sirven aquí.** `tools/teleop.py` es solo para
  el simulador: en el robot real no mueve nada, y no da error.

## 4.1 Encender el robot y conectar el cable

1. Pon el robot **tumbado** en el suelo, con 2 m libres alrededor.
2. Enciéndelo y **espera un par de minutos** a que termine de arrancar (se
   levanta o emite un sonido y las luces se estabilizan).
3. Conecta el cable de red entre tu ordenador y el robot.
4. Cierra la app del móvil **del todo**.

## 4.2 Configurar la red

🖥️ FUERA, en la carpeta `go2-research`:

```bash
./env/go2_net.sh detect
```

**Qué tiene que pasar:** lista tus conexiones Ethernet e indica cuál tiene
cable conectado (`carrier`). **Anota su nombre**: ese es tu `<IFACE>`.

> **⚠️ `<IFACE>` es el nombre real de TU conexión.** En los comandos de abajo
> **hay que sustituirlo**. Si tu conexión se llama `eno1`, escribes `eno1`.
> Escribir `enp3s0` sin comprobar es la causa nº 1 de fallos en esta parte.
> Debe coincidir con la línea `GO2_IFACE=` de tu fichero `.env`: si no, edítala
> con `sed -i "s/^GO2_IFACE=.*/GO2_IFACE=eno1/" .env` (cambiando `eno1` por el
> tuyo).

Crea el perfil de red y actívalo (te pedirá la contraseña):

```bash
./env/go2_net.sh create <IFACE>
./env/go2_net.sh up
./env/go2_net.sh probe
```

**Qué tiene que pasar:** `probe` muestra que responde **192.168.123.161**. Si no
responde, revisa cable, que el robot haya acabado de arrancar, y el nombre de la
conexión.

Este perfil no te deja sin internet: solo añade la red del robot.

## 4.3 Puerta de comprobación número 2

Con el robot encendido y el cable puesto, 🖥️ FUERA:

```bash
python3 tools/doctor.py
```

**Qué tiene que pasar:** `TODO CORRECTO`, y en la sección "Red del robot" una
línea `[ok] el ROBOT RESPONDE   192.168.123.161`.

> **🛑 No toques el robot hasta que salga `TODO CORRECTO`.** Si dice
> `[--] no tiene cable conectado`, el cable no está bien puesto o el robot está
> apagado. Si dice que la interfaz no tiene la IP, ejecuta
> `./env/go2_net.sh create <IFACE>` y `./env/go2_net.sh up`.

## 4.4 Entrar en la caja en modo robot

🖥️ FUERA:

```bash
xhost +local:docker
docker compose -f docker-compose.yml -f docker-compose.linux.yml \
    --profile real run --rm real bash
```

`xhost` permite que la caja abra ventanas en tu pantalla (para ver la cámara).

**Qué tiene que pasar:** la línea pasa a empezar por `root@` o `go2@`: estás
**📦 DENTRO**, en modo robot. Todos los comandos de las partes 4 y 5 que llevan
`python3` se escriben aquí.

> Esta caja ve el mismo cable de red que tu ordenador. Si al entrar dice que
> `GO2_IFACE` no está definida, vuelve a la parte 2 (fichero `.env`).

## 4.5 Leer los sensores (no mueve el robot)

📦 DENTRO (sustituye `<IFACE>` por tu conexión):

```bash
python3 tools/dds_smoketest.py --mode real --iface <IFACE> --duration 20
```

**Qué tiene que pasar:** durante 20 segundos escucha al robot y muestra un
informe con los datos que recibe, sin errores. **Este comando no mueve el
robot.** Si no recibe nada, vuelve a 4.2.

## 4.6 Ver la cámara del robot

📦 DENTRO:

```bash
python3 tools/robot_camera.py --iface <IFACE> --seconds 20 --width 800
```

**Qué tiene que pasar:** se abre una ventana con lo que ve el robot, y al final
imprime los fotogramas por segundo y la latencia (deberían salir unos 24 fps y
poca latencia, mejor que la webcam de un portátil). Tampoco mueve el robot.

Colócate delante y camina un poco: ves tus piernas y tu torso, no tu cara. Es
lo esperado.

La cámara del robot llega **por la red**. Los dispositivos `/dev/video*` solo
son para la webcam del portátil: **no hacen falta para nada de esta guía**.

Si no hay imagen: comprueba que la app del móvil está cerrada del todo.

## 4.7 Mover el robot con el teclado

Antes de esto: **mando en la mano, 5 m libres, batería > 50 %**.

Primero la versión de prueba, que no mueve nada (📦 DENTRO):

```bash
python3 tools/teleop_real.py --iface <IFACE> --dry-run
```

**Qué tiene que pasar:** imprime lo que haría al pulsar teclas, pero el robot
no se mueve.

Ahora de verdad:

```bash
python3 tools/teleop_real.py --iface <IFACE> --step 0.1
```

**Qué tiene que pasar:** el robot **se levanta** (tarda unos segundos).
Después, las teclas `W A S D Q E` lo mueven, igual que en el simulador, y la
barra espaciadora lo detiene. Al salir (Ctrl + C), el robot se para y se
amortigua.

Por seguridad la velocidad máxima está limitada a 0.3 m/s. Recuerda que por
debajo de unos 0.2 m/s va a tirones o no se mueve: para verlo caminar bien,
pulsa varias veces la misma tecla.

**Si algo va mal: `L2` + `B`.**

---

# PARTE 5. Que el robot te siga (solo Linux)

El robot usa su cámara para localizarte y avanzar o girar para mantenerte
centrado y a distancia constante. Necesitas estar en la caja en modo robot (4.4)
y haber pasado por la parte 4.

**Repite las reglas de seguridad:** mando en la mano, **5 m libres**, batería
> 50 %, app cerrada.

## 5.1 Prueba sin mover el robot (obligatoria)

📦 DENTRO:

```bash
python3 usecases/uc04_person_following/deploy/follow_person.py \
    --mode real --iface <IFACE> --source robot --show --dry-run
```

**Qué tiene que pasar:** tarda unos segundos en cargar (`cargando YOLO...`,
`detector listo`), se abre una ventana con la cámara del robot y un recuadro
alrededor de cualquier persona que vea. **El robot no se mueve.**

Colócate a 2 o 3 metros, de pie y **quieto**. Recuerda que solo te ve de
cintura para abajo y algo de torso.

## 5.2 La comprobación crítica

Con la prueba anterior en marcha, mira las velocidades que el programa
calcularía (aparecen como `vx` y `wz` en la ventana, o en la línea de texto):

> **🛑 Si estando tú quieto y visible los comandos NO son cero, PARA.**
> Pulsa `q` sobre la ventana o `Ctrl + C`, y **no sigas al paso 5.3**.

Con una persona quieta y centrada las velocidades tienen que estar en cero (o
saltar poquísimo). Con la persona quieta, `vx` y `wz` distintos de cero
significan que el robot **avanzaría o giraría sin control**. Es un fallo real que
se detectó así, antes de que hiciera daño. Avisa a quien mantiene el proyecto.

Prueba también:

- **Sal del encuadre:** los comandos vuelven a cero (si no ve a nadie, el robot
  para).
- **Da un paso lateral:** aparece un giro hacia ti.
- **Aléjate un par de pasos:** aparece avance (te ve más pequeño y quiere
  recuperar la distancia).

Cuando todo eso se comporte como debe, continúa.

## 5.3 Seguimiento real

Mando en la mano. Persona delante, a 2 o 3 m. 📦 DENTRO:

```bash
python3 usecases/uc04_person_following/deploy/follow_person.py \
    --mode real --iface <IFACE> --source robot --show --duration 60
```

**Qué tiene que pasar:**

1. Carga el detector (unos segundos).
2. Imprime `ROBOT FISICO. Confirma:` con las condiciones de seguridad.
3. El robot **se levanta** (`levantando el robot (StandUp + BalanceStand)...`):
   tarda unos 5 segundos. Todavía no camina.
4. Empieza el seguimiento: si te mueves despacio, el robot gira y avanza
   para mantenerte centrado y a la misma distancia.
5. A los 60 segundos, o con `q` o `Ctrl + C`, el robot se detiene y se queda
   en la postura segura.

Consejos:

- Camina despacio y sin cambios bruscos.
- Si ves **tirones**, es lo normal a baja velocidad: el robot ignora órdenes
  por debajo de 0.2 m/s.
- Si se pierde de vista a la persona, **el robot se detiene**; no sigue con el
  último comando.

**Si algo va mal: `L2` + `B`.**

## 5.4 Al terminar

1. Escribe `exit` para salir de la caja.
2. Apaga el robot cuando esté tumbado.
3. Cierra el permiso de ventanas: `xhost -local:docker`
4. Opcional: `./env/go2_net.sh down` para quitar la red del robot.

---

# Referencia rápida

Recuerda: **📦 DENTRO** = en la caja, **🖥️ FUERA** = en tu ordenador.

| qué | dónde | comando |
|---|---|---|
| comprobar que todo está bien (Linux) | 🖥️ | `python3 tools/doctor.py` |
| arreglar lo automatizable (Linux) | 🖥️ | `python3 tools/doctor.py --fix` |
| entrar en la caja (Linux, simulador) | 🖥️ | `./go2 dev shell` |
| entrar en la caja (Windows/Mac) | 🖥️ | `docker compose --profile sim exec shell bash` |
| arrancar simulador (Windows/Mac) | 🖥️ | `docker compose --profile sim up` |
| arrancar simulador (Linux) | 📦 | `cd /opt/go2/unitree_mujoco/simulate_python && python3 unitree_mujoco.py` |
| robot de pie (simulador) | 📦 | `python3 usecases/uc01_locomotion/deploy/run_policy.py --mode sim --duration 60` |
| teclado (simulador) | 📦 | `python3 tools/teleop.py --mode sim` |
| red del robot | 🖥️ | `./env/go2_net.sh detect / create <IFACE> / up / probe` |
| entrar en modo robot | 🖥️ | ver 4.4 |
| leer sensores | 📦 | `python3 tools/dds_smoketest.py --mode real --iface <IFACE> --duration 20` |
| cámara del robot | 📦 | `python3 tools/robot_camera.py --iface <IFACE> --seconds 20 --width 800` |
| teclado (robot real) | 📦 | `python3 tools/teleop_real.py --iface <IFACE> --step 0.1` |
| seguimiento (prueba) | 📦 | ver 5.1 |
| seguimiento (real) | 📦 | ver 5.3 |
| salir de la caja | 📦 | `exit` |
| parar el simulador | 🖥️ | `Ctrl + C` y `docker compose --profile sim down` |

Cerrar todo: `exit` en cada terminal de la caja, `Ctrl + C` donde corra algo.

---

# Problemas y soluciones

## Emergencias con el robot físico

| situación | qué hacer |
|---|---|
| **cualquier cosa rara con el robot** | **`L2` + `B` en el mando. Siempre lo primero.** |
| el robot avanza o gira sin control | `L2` + `B`; después `Ctrl + C` en el ordenador |
| el programa se queda colgado o no responde | `L2` + `B`; luego cierra la terminal |
| el robot no responde ni al mando | aléjate de él y avisa a quien mantiene el robot; no lo agarres mientras se mueve |
| alguien se acerca demasiado | `L2` + `B` y avisa |
| se cae al suelo | `L2` + `B`, no lo levantes con el programa en marcha |
| cortas el programa y el robot sigue moviéndose | `L2` + `B`. Cortar el programa **no** lo detiene por sí solo |

## Errores frecuentes

| lo que ves | qué pasa | qué hacer |
|---|---|---|
| `error during connect` o `Cannot connect to the Docker daemon` | Docker no está en marcha | Abre Docker Desktop y espera a que el icono deje de moverse (en Linux: `sudo systemctl enable --now docker`) |
| **`ModuleNotFoundError: No module named 'numpy'`** (o `cv2`, `torch`, `unitree_sdk2py`...) | **Estás FUERA de la caja.** Las bibliotecas solo existen dentro | Entra en la caja (3.2 o 4.4) y repite el comando. El principio de la línea tiene que decir `go2@` o `root@` |
| `docker: command not found` (o `./go2: command not found`) dentro de la caja | Estás **DENTRO** y ese comando es para FUERA | Escribe `exit` para salir de la caja y repítelo |
| `python3: can't open file 'tools/...'` | No estás en la carpeta del proyecto | Fuera de la caja: `cd go2-research`. Dentro: `cd /workspace` |
| `permission denied` al usar docker | Falta el permiso de Docker | `sudo usermod -aG docker $USER` y **reinicia el ordenador** |
| `does not match an available interface` | `<IFACE>` no es el nombre real de tu conexión | `./env/go2_net.sh detect` (FUERA), usa ese nombre y corrige `.env`. Ejecuta `python3 tools/doctor.py` |
| `Unable to find group render` | El fichero de Linux trae valores de otro ordenador | 🖥️ `python3 tools/gen_linux_override.py --write` |
| `error gathering device information` | Pide un dispositivo `/dev/video*` que no existe | Igual: `python3 tools/gen_linux_override.py --write` |
| `cannot connect to X server` / `Can't open display` / no se abre ninguna ventana | La caja no tiene permiso para abrir ventanas | 🖥️ `xhost +local:docker` y vuelve a entrar en la caja |
| el navegador no muestra el simulador | El simulador no ha terminado de arrancar o el puerto está ocupado | Espera a `escritorio virtual listo`. Si sigue, `docker compose --profile sim down` y otra vez `up` |
| El simulador va lentísimo en Linux | Estás usando el navegador (`--profile sim up`) | Usa `./go2 dev shell` y lanza el simulador dentro (3.1) |
| el simulador va muy lento (Windows/Mac) | Dibuja en 3D con el procesador | No tiene arreglo en Windows y Mac. Es normal y no afecta al control |
| `python3 tools/doctor.py` dice `no tiene cable conectado` | La interfaz está apagada porque no hay cable | Sin robot no es un problema. Con robot: revisa cable y que esté encendido |
| `el robot no responde` en `probe` o `doctor` | Robot aún arrancando, cable, o red mal configurada | Espera 2 minutos, revisa el cable, repite `./env/go2_net.sh up` |
| la cámara del robot no da imagen | La app del móvil está usando la cámara | Ciérrala **del todo** (no en segundo plano) |
| el robot no se mueve y no da error | Estás usando `tools/teleop.py` (solo simulador), o `Go2Controller`, que con el robot no funcionó (ver `ESTRATEGIA_CASOS_USO.md`) | Usa `tools/teleop_real.py` o `follow_person.py --mode real` |
| el robot va a tirones o se queda quieto a poca velocidad | El controlador del fabricante ignora órdenes por debajo de ~0.2 m/s | No es un fallo. Aumenta la velocidad |
| el robot se dobla / se tumba al empezar o al terminar | Toma y suelta el control | Es normal (ver 4.0) |
| la detección no ve mi cara | La cámara está a 30 cm del suelo | Es normal: ve piernas y torso |
| en 5.2 los comandos no son cero con la persona quieta | Fallo de control | **PARA** (`q` o `Ctrl + C`), no sigas y avisa |
| los ficheros creados por la caja no se pueden borrar | `UID_GID` mal en `.env` | Ejecuta la parte 2.1 de nuevo |

Cuando dudes: en Linux, `python3 tools/doctor.py` (FUERA). En Windows y Mac, entra
en la caja (3.2) y ejecútalo ahí: comprueba lo que corresponde dentro.

---

# A dónde seguir

- **Tu propio caso de uso:** copia [`usecases/uc00_plantilla`](../usecases/uc00_plantilla/LEEME.md)
  y abre `mi_caso.py`. Es lo único que tocas; funciona sin cambiar nada.
- [`ESTRATEGIA_CASOS_USO.md`](ESTRATEGIA_CASOS_USO.md): para entender cómo se
  desarrolla un caso de uso y qué transfiere del simulador al robot real.
- [`API.md`](API.md): referencia técnica, la línea exacta de cada operación.
- [`SAFETY.md`](SAFETY.md): protocolo de seguridad completo del grupo. Léelo
  antes de hacer nada que vaya más allá de esta guía con el robot real.
- [`DOCKER.md`](DOCKER.md): el contenedor por dentro: puertos, variables,
  rendimiento del visor y versiones fijadas.
