"""Carga del contrato sim2real.

Este modulo debe ser el UNICO punto por el que entrenamiento y despliegue
leen kp, kd, action_scale, orden de articulaciones y frecuencia de control.
Si estos valores se duplican en dos sitios, tarde o temprano divergen y el
sim2real falla por una razon que no es el algoritmo.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def load_contract(path: str | Path) -> dict:
    with open(path) as f:
        c = yaml.safe_load(f)

    required = ["joint_order", "default_angles", "kp", "kd", "action_scale", "ctrl_hz"]
    missing = [k for k in required if k not in c]
    if missing:
        raise ValueError(f"El contrato {path} no define: {missing}")

    n = len(c["joint_order"])
    if n != 12:
        raise ValueError(f"joint_order debe tener 12 entradas, tiene {n}")
    if len(c["default_angles"]) != 12:
        raise ValueError("default_angles debe tener 12 entradas")

    return c
