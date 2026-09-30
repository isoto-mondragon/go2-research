#!/usr/bin/env python3
"""tools/gen_linux_override.py

Genera `docker-compose.linux.yml` con los valores REALES de esta maquina.

POR QUE HACE FALTA
------------------
Ese fichero comparte con el contenedor la tarjeta grafica y la webcam del
anfitrion. Ambas cosas dependen de la maquina:

  - los GID de los grupos `render` y `video` cambian entre distribuciones
    (990 y 44 en Ubuntu 26.04, otros en Debian o Fedora)
  - `/dev/video1` existe en un portatil y no en otro
  - puede no haber GPU accesible, o no haber webcam

Si el fichero trae los valores de otra maquina, docker compose falla con
mensajes poco claros: "Unable to find group render" o "error gathering device
information".

Los grupos van por GID NUMERICO, nunca por nombre: el nombre se resuelve en el
/etc/group del CONTENEDOR, que es un Ubuntu minimo y no los tiene.

SOBRE LA CAMARA DEL ROBOT
-------------------------
No necesita /dev/video. La imagen del Go2 llega por red, igual que el resto de
sensores. Los dispositivos de video solo hacen falta para la webcam del
portatil.

Solo aplica en Linux. En Windows y macOS lo dice y sale sin error. Usa solo la
biblioteca estandar.

Uso:
    python3 tools/gen_linux_override.py            # ver que detecta
    python3 tools/gen_linux_override.py --write    # escribir el fichero
"""

from __future__ import annotations

import argparse
import platform
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from go2core import paths  # noqa: E402

V, R, G, Y, Z = "\033[34m", "\033[31m", "\033[32m", "\033[33m", "\033[0m"


def nombre_de_grupo(gid: int) -> str:
    import grp   # solo existe en Unix; aqui ya se ha comprobado que es Linux
    try:
        return grp.getgrgid(gid).gr_name
    except KeyError:
        return "sin nombre"


def gids_de(ruta: Path) -> dict[int, str]:
    """GID de los grupos dueños de los dispositivos bajo una ruta."""
    encontrados: dict[int, str] = {}
    if not ruta.exists():
        return encontrados
    for d in sorted(ruta.iterdir()):
        if d.is_dir():
            continue
        try:
            g = d.stat().st_gid
            encontrados[g] = nombre_de_grupo(g)
        except OSError:
            pass
    return encontrados


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--write", action="store_true")
    args = p.parse_args()

    # Lo primero: en Windows y macOS no existe grp ni /dev/dri, y no hay nada
    # que generar. Salir limpio, sin traza, con el motivo.
    if platform.system() != "Linux":
        print("Esto solo aplica en Linux: comparte con el contenedor la GPU y la")
        print("webcam del anfitrion. En Windows y macOS no hay nada que hacer;")
        print("docker compose se usa sin este fichero.")
        return 0

    print(f"\n{V}=== Configuracion de esta maquina ==={Z}\n")

    # ---------------- GPU ----------------
    dri = Path("/dev/dri")
    nodos_gpu = sorted(d.name for d in dri.iterdir()
                       if d.is_file() or d.is_char_device()) if dri.exists() else []
    gids_gpu = gids_de(dri)

    print(f"{V}GPU{Z}")
    if nodos_gpu:
        print(f"  dispositivos  {', '.join(nodos_gpu)}")
        for g, n in sorted(gids_gpu.items()):
            print(f"  grupo         {g}  ({n})")
    else:
        print(f"  {Y}sin /dev/dri: no hay GPU accesible desde el contenedor{Z}")

    # ---------------- webcam ----------------
    videos = sorted(Path("/dev").glob("video*"))
    gids_video: dict[int, str] = {}
    for v in videos:
        try:
            g = v.stat().st_gid
            gids_video[g] = nombre_de_grupo(g)
        except OSError:
            pass

    print(f"\n{V}Webcam{Z}")
    if videos:
        print(f"  dispositivos  {', '.join(v.name for v in videos)}")
        for g, n in sorted(gids_video.items()):
            print(f"  grupo         {g}  ({n})")
        print(f"  {Y}Nota: solo hace falta para la webcam del portatil.")
        print(f"  La camara del ROBOT llega por red y no necesita esto.{Z}")
    else:
        print("  sin webcam (la camara del robot sigue funcionando)")

    # ---------------- red ----------------
    print(f"\n{V}Interfaces de red{Z}")
    import subprocess
    r = subprocess.run(["ip", "-br", "link"], capture_output=True, text=True)
    candidatas = []
    for linea in r.stdout.splitlines():
        campos = linea.split()
        if not campos or campos[0] == "lo":
            continue
        nombre = campos[0].split("@")[0]
        if nombre.startswith(("docker", "veth", "br-", "virbr")):
            continue
        estado = campos[1] if len(campos) > 1 else "?"
        marca = "  <-- candidata para el robot" if nombre.startswith("e") else ""
        print(f"  {nombre:<14} {estado}{marca}")
        if nombre.startswith("e"):
            candidatas.append(nombre)

    env = paths.ROOT / ".env"
    iface_env = None
    if env.exists():
        for l in env.read_text().splitlines():
            if l.startswith("GO2_IFACE="):
                iface_env = l.split("=", 1)[1].strip()

    print(f"\n  GO2_IFACE en .env: {iface_env or '(sin definir)'}")
    if iface_env and iface_env not in candidatas:
        print(f"  {R}AVISO: '{iface_env}' no existe en esta maquina.{Z}")
        if candidatas:
            print(f"  {Y}Corrigelo con:")
            print(f"    sed -i 's/^GO2_IFACE=.*/GO2_IFACE={candidatas[0]}/' .env{Z}")

    # ---------------- generar ----------------
    todos_gids = {}
    todos_gids.update(gids_gpu)
    todos_gids.update(gids_video)

    if not nodos_gpu and not videos:
        print(f"\n{Y}Sin GPU ni webcam: el override no aporta nada en esta")
        print(f"maquina. Usa docker compose sin el.{Z}")
        return 0

    disp_sim = [f"      - /dev/dri:/dev/dri"] if nodos_gpu else []
    disp_video = [f"      - /dev/{v.name}:/dev/{v.name}" for v in videos]
    grupos = [f'      - "{g}"          # {n}' for g, n in sorted(todos_gids.items())]

    def bloque(nombre: str, disp: list[str], extra: str = "") -> str:
        if not disp:
            return ""
        return (f"  {nombre}:\n"
                f"    devices:\n" + "\n".join(disp) + "\n"
                f"    group_add:\n" + "\n".join(grupos) + "\n" + extra + "\n")

    contenido = f"""# docker-compose.linux.yml
#
# GENERADO POR tools/gen_linux_override.py el {date.today().isoformat()}
# NO editar a mano: se regenera con
#     python3 tools/gen_linux_override.py --write
#
# Comparte con el contenedor la GPU y la webcam de ESTA maquina. Los valores
# dependen del ordenador, asi que cada usuario de Linux debe regenerarlo.
#
# Los grupos van por GID NUMERICO, no por nombre: el nombre se resolveria en el
# /etc/group del CONTENEDOR, que es un Ubuntu minimo y no tiene `render`.
#
# La camara del ROBOT no necesita nada de esto: llega por red.
#
# Detectado en esta maquina:
#   GPU     {', '.join(nodos_gpu) or 'ninguna'}
#   webcam  {', '.join(v.name for v in videos) or 'ninguna'}
#   grupos  {', '.join(f'{g} ({n})' for g, n in sorted(todos_gids.items())) or 'ninguno'}

services:

{bloque("shell", disp_video)}
{bloque("real", disp_video + disp_sim)}
{bloque("dev", disp_sim + disp_video)}"""

    destino = paths.ROOT / "docker-compose.linux.yml"
    print(f"\n{V}--- Fichero generado ---{Z}")
    print(contenido)

    if args.write:
        if destino.exists():
            copia = destino.with_suffix(".yml.bak")
            copia.write_text(destino.read_text())
            print(f"copia de seguridad: {copia}")
        destino.write_text(contenido)
        print(f"{G}escrito: {destino}{Z}")
        print("\nComprueba que es valido:")
        print("  docker compose -f docker-compose.yml "
              "-f docker-compose.linux.yml --profile sim config --quiet")
    else:
        print(f"{Y}No se ha escrito nada. Anade --write para guardarlo.{Z}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
