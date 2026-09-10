# go2-research

Infraestructura de investigacion sobre Unitree Go2 EDU.
Grupo DANZ, Escuela Politecnica Superior, Mondragon Unibertsitatea.

## Arranque rapido

```bash
./env/bootstrap_host.sh            # host Ubuntu 26.04
distrobox enter go2-humble
./env/bootstrap_container.sh       # ROS2 Humble + CycloneDDS 0.10.2 + SDK2
```

Simulacion: `source ~/unitree_ros2/setup_sim.sh` (domain 1, interfaz `lo`)
Robot real: `source ~/unitree_ros2/setup_real.sh <IFACE>` (domain 0)

## Casos de uso

| id | tema | estado |
|----|------|--------|
| uc01_locomotion  | locomocion RL y sim2real con recursos de consumo | en curso |
| uc02_room_exit   | navegacion de salida de sala con percepcion minima | planificado |
| uc03_energy_aware| coste de transporte y seleccion de marcha | planificado |

## Reglas del repositorio

1. Ningun parametro de control se hardcodea. Todo vive en `usecases/*/configs/`.
2. Un experimento sin `manifest.json` no existe.
3. Las figuras se generan con `results/make_figures.py`. Nunca se editan a mano.
4. Los pesos y los rosbags van por DVC, nunca por git.
5. Antes de tocar el robot fisico se lee `docs/SAFETY.md`. Sin excepciones.

## Repositorios relacionados

- `go2-perception-stack` (publico): superficie de publicacion, con tags por paper.
- `go2-robotics-workspace-archive` (privado, archivado): backup historico previo.
