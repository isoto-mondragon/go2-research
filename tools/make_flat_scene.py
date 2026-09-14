#!/usr/bin/env python3
"""tools/make_flat_scene.py

Inspecciona una escena de unitree_mujoco y genera una version PLANA.

Por que hace falta: los rollouts de evaluacion solo son comparables entre si
si el terreno es identico y sin obstaculos. Un choque contra una escalera
contamina la medida de seguimiento de velocidad y no se distingue de una
politica mala.

Que hace:
  --inspect  lista todo lo que hay en el worldbody de la escena
  (sin flag)  escribe scene_flat.xml conservando luces, camaras, materiales,
              texturas y la fricción del suelo, y quitando geoms que no sean
              plano, cuerpos sueltos y campos de altura

No modifica la escena original. Escribe un fichero nuevo al lado.

Uso:
    python3 tools/make_flat_scene.py --inspect
    python3 tools/make_flat_scene.py
    python3 tools/make_flat_scene.py --scene ~/opt/unitree_mujoco/unitree_robots/go2/scene.xml
"""

from __future__ import annotations

import argparse
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

DEFAULT_SCENE = Path("~/opt/unitree_mujoco/unitree_robots/go2/scene.xml").expanduser()
REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_COPY = REPO_ROOT / "usecases/uc01_locomotion/configs/scene_flat.xml"


def describe(el: ET.Element) -> str:
    parts = [el.tag]
    for k in ("name", "type", "pos", "size", "material", "hfield", "friction"):
        if k in el.attrib:
            parts.append(f'{k}="{el.attrib[k]}"')
    return "  ".join(parts)


def is_floor(el: ET.Element) -> bool:
    """Un geom es suelo si es un plano."""
    return el.tag == "geom" and el.attrib.get("type") == "plane"


def is_obstacle(el: ET.Element) -> bool:
    """Geoms solidos que no son el suelo, cuerpos sueltos y campos de altura."""
    if el.tag == "geom":
        return not is_floor(el)
    if el.tag == "body":
        return True
    return False


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scene", default=str(DEFAULT_SCENE))
    p.add_argument("--inspect", action="store_true",
                   help="solo listar el contenido, no escribir nada")
    p.add_argument("--out", default=None,
                   help="ruta de salida (defecto: scene_flat.xml junto a la original)")
    args = p.parse_args()

    scene = Path(args.scene).expanduser()
    if not scene.exists():
        print(f"No existe: {scene}")
        return 2

    tree = ET.parse(scene)
    root = tree.getroot()
    world = root.find("worldbody")
    if world is None:
        print("La escena no tiene <worldbody>.")
        return 2

    print(f"escena: {scene}\n")
    print("--- includes ---")
    for inc in root.findall("include"):
        print(f"  {inc.attrib.get('file')}")

    hfields = root.findall(".//hfield")
    if hfields:
        print("\n--- campos de altura declarados ---")
        for h in hfields:
            print(f"  {describe(h)}")

    print("\n--- worldbody ---")
    floors, obstacles, others = [], [], []
    for el in list(world):
        if is_floor(el):
            floors.append(el)
            print(f"  [SUELO]     {describe(el)}")
        elif is_obstacle(el):
            obstacles.append(el)
            print(f"  [OBSTACULO] {describe(el)}")
        else:
            others.append(el)
            print(f"  [conserva]  {describe(el)}")

    print(f"\nresumen: {len(floors)} suelo, {len(obstacles)} obstaculos, "
          f"{len(others)} otros (luces, camaras)")

    if not floors:
        print("\nAVISO: no hay ningun geom de tipo plane. Si el suelo es un hfield,")
        print("quitarlo dejaria al robot cayendo al vacio. Parate y revisalo.")
        if not args.inspect:
            return 3

    if args.inspect:
        return 0

    if not obstacles:
        print("\nLa escena ya es plana. No hace falta generar nada.")
        return 0

    # --- generar la version plana ---
    for el in obstacles:
        world.remove(el)

    out = Path(args.out).expanduser() if args.out else scene.with_name("scene_flat.xml")
    if root.attrib.get("model"):
        root.set("model", root.attrib["model"] + " flat")

    comment = (" Generado por tools/make_flat_scene.py a partir de "
               f"{scene.name}. Obstaculos retirados para que los rollouts de "
               "evaluacion sean comparables. No editar a mano: regenerar. ")
    tree.write(out, encoding="utf-8", xml_declaration=True)
    txt = out.read_text()
    lines = txt.split("\n")
    for i, ln in enumerate(lines):
        if "<mujoco" in ln:
            lines.insert(i, f"<!--{comment}-->")
            break
    out.write_text("\n".join(lines))

    print(f"\nescrito: {out}")
    print(f"retirados {len(obstacles)} elementos:")
    for el in obstacles:
        print(f"  - {describe(el)}")

    REPO_COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out, REPO_COPY)
    print(f"\ncopia versionada: {REPO_COPY.relative_to(REPO_ROOT)}")

    print("\nPara usarla, en ~/opt/unitree_mujoco/simulate_python/config.py:")
    print('  ROBOT_SCENE = "../unitree_robots/" + ROBOT + "/scene_flat.xml"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
