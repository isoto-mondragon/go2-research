# uc04 — Seguimiento de personas

## Qué hace

El robot detecta a una persona con la cámara y la sigue: gira para mantenerla
centrada y avanza o retrocede para mantener la distancia.

cámara ──► YOLO ──► control ──► (vx, vy, wz) ──► robot
                             ▲
                             │
               simulador MuJoCo o Go2 físico


## Por qué está montado así

**El script solo decide velocidades.** No sabe caminar. De eso se encarga la
capa de locomoción: la política RL en simulación, Sport Mode en el robot real.
El mismo código sirve para los dos porque la interfaz es la misma, tres
números.

**Se detectan personas, no caras.** La cámara del Go2 está a unos 30 cm del
suelo: de una persona a dos metros ve piernas y torso. La clase `person` de
YOLO se dispara igual con cuerpos parciales.

**La distancia se estima por tamaño aparente.** No es fiable a corta distancia,
cuando la persona se sale del encuadre por arriba y el recuadro deja de crecer.
El control lo compensa con zona muerta amplia y topes de velocidad.

## Cómo se ejecuta

Tres terminales, todas dentro del contenedor.

```bash
# 1. Simulador
./go2 sim up

# 2. Locomoción escuchando comandos
python3 usecases/uc01_locomotion/deploy/run_policy.py --mode sim --teleop --duration 600

# 3. Seguimiento
python3 usecases/uc04_person_following/deploy/follow_person.py --mode sim --show
```

Antes de mover nada, conviene probar solo la detección:

```bash
python3 usecases/uc04_person_following/perception/detector.py --show
python3 usecases/uc04_person_following/deploy/follow_person.py --mode sim --show --dry-run
```

Robot real, con Sport Mode:

```bash
python3 usecases/uc04_person_following/deploy/follow_person.py \
    --mode real --iface enp3s0 --show
```

## Seguridad

- Velocidades limitadas a los rangos del contrato, y con topes propios más bajos
- Si se pierde a la persona, el robot para: no sigue con el último comando
- Ctrl-C envía velocidad cero antes de salir
- `--dry-run` detecta y calcula sin enviar nada

## Qué ejercita de la infraestructura

Este caso de uso se construyó desde cero sobre la imagen descargada, sin tocar
el Dockerfile ni reconstruir nada. Prueba:

| | |
|---|---|
| dispositivos del anfitrión | `/dev/video0` al contenedor |
| visión por computador | YOLO y OpenCV de la imagen |
| control de alto nivel | Sport Mode, sin tocar LowCmd |
| DDS bidireccional | publicar comandos mientras el simulador camina |
| trazabilidad | manifest, métricas y sha de git |

## Estado

- [x] Detector con suavizado y gestión de pérdidas
- [x] Ley de control con zonas muertas y rampa
- [x] Salida a simulador y a robot real
- [ ] Probado en simulación
- [ ] Probado en robot real
- [ ] Ajuste de ganancias con el robot

## La locomoción en simulación limita la demo

En simulación, el robot se mueve con la política RL heredada, que sigue los
comandos solo al 40-56 % a velocidades bajas (medido en uc01). Un comando de
0.1 m/s se convierte en unos 0.05 m/s reales: el robot se arrastra.

**No es un fallo del seguimiento.** El bucle cámara → detección → control →
DDS funciona; lo que va justo es la capa de locomoción.

`unitree_mujoco` no emula Sport Mode, así que en simulación no hay alternativa.
En el robot real, `--mode real` usa Sport Mode y el seguimiento será mucho más
vivo sin tocar una línea de código.

Por eso las ganancias están subidas para simulación. **Antes de la primera
prueba con el robot, bajarlas** a `kp_giro: 1.2` y `kp_avance: 1.0`, o el robot
irá demasiado brusco.

## Convención de signos

Referidos al punto de vista del ROBOT, no al de la persona:

| la persona | en la imagen | comando |
|---|---|---|
| se mueve a su derecha | aparece a la izquierda, `lateral` negativo | `wz` positivo, el robot gira a su izquierda |
| se aleja | `tamano` baja | `vx` positivo, avanza |
| se acerca | `tamano` sube | `vx` negativo, retrocede |
