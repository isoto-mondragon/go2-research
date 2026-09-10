"""Carga y validacion del contrato sim2real (esquema v2).

Este modulo debe ser el UNICO punto por el que entrenamiento y despliegue
leen poses, ganancias, escalado de acciones y orden de observaciones.
Si estos valores se duplican en dos sitios, tarde o temprano divergen y el
sim2real falla por una razon que no es el algoritmo.
"""

from __future__ import annotations

from pathlib import Path

import yaml

N_JOINTS = 12


class ContractError(ValueError):
    """El contrato existe pero no es utilizable para lo que se pide."""


def load_contract(path: str | Path) -> dict:
    """Carga el contrato y valida lo que siempre debe estar completo."""
    path = Path(path)
    with open(path) as f:
        c = yaml.safe_load(f)

    if c.get("meta", {}).get("version") != 2:
        raise ContractError(f"{path}: se esperaba meta.version = 2")

    for key in ("joint_order", "default_angles"):
        v = c.get(key)
        if not isinstance(v, list) or len(v) != N_JOINTS:
            raise ContractError(f"{path}: '{key}' debe ser una lista de {N_JOINTS} elementos")

    for pose in ("stand", "crouch"):
        v = c.get("poses", {}).get(pose)
        if not isinstance(v, list) or len(v) != N_JOINTS:
            raise ContractError(f"{path}: poses.{pose} debe tener {N_JOINTS} elementos")

    if c["default_angles"] != c["poses"]["stand"]:
        raise ContractError(f"{path}: default_angles debe coincidir con poses.stand")

    for state in ("passive", "fix_stand"):
        for g in ("kp", "kd"):
            v = c.get("gains", {}).get(state, {}).get(g)
            if not isinstance(v, list) or len(v) != N_JOINTS:
                raise ContractError(f"{path}: gains.{state}.{g} debe tener {N_JOINTS} elementos")

    return c


def require_policy_ready(c: dict) -> dict:
    """Valida ademas lo que hace falta para EJECUTAR la politica.

    Se separa de load_contract para que el FSM (passive, fix_stand) pueda
    usarse antes de tener el contrato de observaciones cerrado.
    """
    pend: list[str] = []

    for g in ("kp", "kd"):
        v = c.get("gains", {}).get("velocity", {}).get(g)
        if not isinstance(v, list) or len(v) != N_JOINTS:
            pend.append(f"gains.velocity.{g}")

    for k in ("action_scale", "ctrl_hz"):
        if c.get("policy", {}).get(k) is None:
            pend.append(f"policy.{k}")

    obs = c.get("obs", {})
    if not obs.get("order"):
        pend.append("obs.order")
    for k in ("ang_vel", "joint_pos", "joint_vel"):
        if obs.get("scales", {}).get(k) is None:
            pend.append(f"obs.scales.{k}")

    if pend:
        raise ContractError(
            "El contrato aun no permite ejecutar la politica. Campos PENDIENTE:\n  "
            + "\n  ".join(pend)
            + "\nRellenalos desde train/legacy_mjlab_go2/deploy_params.yaml"
        )
    return c
