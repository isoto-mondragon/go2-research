# go2-research

Infraestructura de investigación sobre el Unitree Go2 EDU.
Grupo DANZ, Escuela Politécnica Superior, Mondragon Unibertsitatea.

## Empezar

**Nunca has usado esto**: [`docs/QUICKSTART.md`](docs/QUICKSTART.md)
Del ordenador en blanco a mover el robot en el simulador, en 45 minutos.
Funciona en Linux, Windows y macOS, con cualquier tarjeta gráfica.

```bash
git clone git@github.com:isoto-mondragon/go2-research.git
cd go2-research
docker compose --profile sim build     # una vez, 20-40 min
docker compose --profile sim up        # navegador: localhost:6080/vnc.html
```

**Vas a desarrollar**: [`docs/GUIA_COMPLETA.md`](docs/GUIA_COMPLETA.md)

**Vas a tocar el robot físico**: [`docs/SAFETY.md`](docs/SAFETY.md), obligatorio.

## Qué hay aquí

Simulación y robot real comparten la misma cadena de control: el código no
cambia, solo una variable de entorno. Todo va dentro de un contenedor Docker,
sin instalar ROS, Python ni CUDA en tu máquina.

| | |
|---|---|
| Comunicación | CycloneDDS 0.10.2, la versión del robot |
| Control alto nivel | Sport Mode del fabricante, vía `Go2Controller` |
| Control bajo nivel | `LowCmd` con CRC, watchdog y límites de par |
| Simulador | unitree_mujoco, escena plana, visor en el navegador |
| Despliegue | políticas ONNX |
| Evaluación | protocolo reproducible con métricas de marcha |

## Casos de uso

| id | tema | estado |
|----|------|--------|
| uc01_locomotion | locomoción RL y sim2real con recursos de consumo | cerrado, en pausa |
| uc02_room_exit | navegación de salida de sala | planificado |
| uc03_energy_aware | coste de transporte y selección de marcha | siguiente |
| uc04_person_following | seguimiento de personas con YOLO | base montada |

## Reglas

1. Ningún parámetro de control se cablea: todo en `usecases/*/configs/`
2. Un experimento sin `manifest.json` no existe
3. Las figuras se generan con un comando, nunca se editan a mano
4. Pesos y rosbags por DVC, nunca por git
5. Antes de tocar el robot físico se lee `docs/SAFETY.md`. Sin excepciones.

## Repositorios relacionados

- `go2-perception-stack` (público): superficie de publicación, con tags por paper
- `go2-robotics-workspace-archive` (privado, archivado): montaje original en WSL2
