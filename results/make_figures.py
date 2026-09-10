#!/usr/bin/env python3
"""Genera TODAS las figuras del proyecto a partir de experiments/.

Regla: si una figura no se puede regenerar con un comando, no entra en el paper.

Uso:
    python3 results/make_figures.py --usecase uc01_locomotion
"""

import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = REPO_ROOT / "experiments"
FIGURES = REPO_ROOT / "results" / "figures"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--usecase", default=None, help="limitar a un caso de uso")
    args = p.parse_args()

    FIGURES.mkdir(parents=True, exist_ok=True)
    roots = [EXPERIMENTS / args.usecase] if args.usecase else sorted(EXPERIMENTS.glob("uc*"))

    for root in roots:
        if not root.is_dir():
            continue
        runs = sorted(d for d in root.iterdir() if (d / "manifest.json").exists())
        print(f"{root.name}: {len(runs)} runs con manifest")
        # TODO: cargar metrics.csv de cada run y generar las figuras del caso de uso.


if __name__ == "__main__":
    main()
