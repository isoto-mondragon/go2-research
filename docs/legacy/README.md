# Documentación archivada

> **Para quién:** quien busque de dónde salió una decisión antigua.
> **Cuándo:** casi nunca. **No sigas estos documentos.**

Estos documentos describen el montaje ORIGINAL en WSL2 sobre Windows (rutas tipo
`~/robotics`, instalación manual de las dependencias), o son guías que se han
fusionado o sustituido. El entorno actual es la imagen Docker: empieza en
[`../GUIA.md`](../GUIA.md).

Se conservan porque documentan decisiones y problemas que siguen siendo válidos
(configuración de red del robot, primeros pasos con el hardware, opciones del
stack de percepción), y porque son el registro del punto de partida del
proyecto. **Pueden contradecir a la guía principal**; si es así, manda la guía.
Cada fichero lleva un aviso arriba.

En `docs/` solo queda lo que alguien va a abrir:

| fichero | para quién |
|---|---|
| [`GUIA.md`](../GUIA.md) | punto de entrada, de cero al robot |
| [`SAFETY.md`](../SAFETY.md) | obligatorio antes del robot |
| [`ESTRATEGIA_CASOS_USO.md`](../ESTRATEGIA_CASOS_USO.md) | quien desarrolla |
| [`API.md`](../API.md) | referencia técnica |
| [`DOCKER.md`](../DOCKER.md) | detalles del contenedor |

## Qué hay aquí, por qué, y qué lo sustituye

| fichero | por qué está aquí | lo sustituye |
|---|---|---|
| `EMPEZAR.md` | Primera guía de puesta en marcha. Sustituida por una única guía. | `docs/GUIA.md` |
| `GUIA_COMPLETA.md` | Guía para desarrolladores. Repetía `GUIA_USUARIO.md` y `ESTRATEGIA_CASOS_USO.md`, y recomendaba `Go2Controller` para el robot real. | `docs/ESTRATEGIA_CASOS_USO.md` (cómo desarrollar), `docs/API.md` (referencia) y `docs/DOCKER.md` (el contenedor) |
| `GUIA_USUARIO.md` | Guía de usuario de 700 líneas. Repetía `GUIA.md` y `DOCKER.md`, y traía instrucciones de Windows/Mac anteriores a la guía única. | `docs/GUIA.md` (empezar) y `docs/DOCKER.md` (puertos, variables, contenedor) |
| `INSTALL_legacy_wsl2.md` | Instalación manual sobre WSL2 (rutas `~/robotics`). | `docs/GUIA.md`, partes 1 y 3. La instalación manual en WSL2 ya no se usa: el entorno es la imagen Docker |
| `QUICKSTART.md` | Guía rápida anterior; repetía en parte a `EMPEZAR.md`. | `docs/GUIA.md` |
| `REAL_ROBOT_FIRST_STEPS.md` | Primeros pasos con el robot, con `Go2Controller` y rutas del montaje antiguo. | `docs/GUIA.md`, partes 4 y 5, y `docs/SAFETY.md` |
| `RENDIMIENTO.md` | Rendimiento del visor. Repetía `DOCKER.md`. | `docs/DOCKER.md`, sección «Rendimiento del visor», donde está fusionado sin duplicar |
| `SIM_TO_REAL.md` | Cómo desplegar del simulador al robot. Anterior al contrato v3 y a la plantilla. | `docs/ESTRATEGIA_CASOS_USO.md` (qué transfiere del simulador al robot) y `docs/API.md` |
| `STUDENT_GUIDE.md` | Guía de alumnos del montaje WSL2 original. | `docs/GUIA.md` (empezar) y `docs/API.md` (referencia) |
| `USAGE_GUIDE.md` | Comandos del día a día del montaje WSL2 con `usbipd`. | `docs/GUIA.md` (comandos del día a día) y `docs/API.md` |
| `USAGE_perception_stack.md` | Stack de percepción del montaje antiguo. | `usecases/uc00_plantilla/LEEME.md` (cámara y detección) y `docs/API.md`, sección 5 |
