"""Carga, validacion y conversion de ordenes del contrato sim2real (esquema v3).

Este modulo es el UNICO punto por el que entrenamiento y despliegue leen poses,
ganancias, escalado de acciones y composicion de observaciones. Y es el UNICO
sitio donde se convierte entre orden de motor (firmware Unitree, FR/FL/RR/RL) y
orden de politica (mjlab, FL/FR/RL/RR).

Si estos valores o estas conversiones se duplican en otro fichero, tarde o
temprano divergen y el sim2real falla por una razon que no es el algoritmo.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

N_JOINTS = 12


class ContractError(ValueError):
    """El contrato existe pero no es utilizable para lo que se pide."""


# ---------------------------------------------------------------------------
# Carga y validacion
# ---------------------------------------------------------------------------
def load_contract(path: str | Path) -> dict:
    """Carga el contrato v3 y valida su coherencia interna."""
    path = Path(path)
    with open(path) as f:
        c = yaml.safe_load(f)

    def fail(msg: str) -> None:
        raise ContractError(f"{path}: {msg}")

    if c.get("meta", {}).get("version") != 3:
        fail("se esperaba meta.version = 3")

    if len(c.get("joint_order", [])) != N_JOINTS:
        fail(f"joint_order debe tener {N_JOINTS} nombres")

    # --- mapa de orden ---
    m = c.get("policy", {}).get("joint_ids_map")
    if not isinstance(m, list) or sorted(m) != list(range(N_JOINTS)):
        fail("policy.joint_ids_map debe ser una permutacion de 0..11")

    # --- vectores de 12 ---
    p = c["policy"]
    for key, vec in [
        ("policy.default_joint_pos", p.get("default_joint_pos")),
        ("policy.gains.kp", p.get("gains", {}).get("kp")),
        ("policy.gains.kd", p.get("gains", {}).get("kd")),
        ("policy.action.scale", p.get("action", {}).get("scale")),
        ("policy.action.offset", p.get("action", {}).get("offset")),
    ]:
        if not isinstance(vec, list) or len(vec) != N_JOINTS:
            fail(f"{key} debe ser una lista de {N_JOINTS} elementos")

    f_ = c.get("fsm", {})
    for pose in ("crouch", "stand"):
        if len(f_.get("poses", {}).get(pose, [])) != N_JOINTS:
            fail(f"fsm.poses.{pose} debe tener {N_JOINTS} elementos")
    for state in ("passive", "fix_stand"):
        for g in ("kp", "kd"):
            if len(f_.get("gains", {}).get(state, {}).get(g, [])) != N_JOINTS:
                fail(f"fsm.gains.{state}.{g} debe tener {N_JOINTS} elementos")

    # --- declaraciones de orden ---
    for key, expected in [
        ("policy.default_joint_pos_order", "policy"),
        ("policy.gains_order", "policy"),
        ("policy.action_order", "policy"),
    ]:
        got = p.get(key.split(".", 1)[1])
        if got != expected:
            fail(f"{key} debe ser '{expected}', es {got!r}")
    if f_.get("gains_order") != "motor" or f_.get("poses_order") != "motor":
        fail("fsm.gains_order y fsm.poses_order deben ser 'motor'")

    # --- observaciones ---
    total = sum(t["dim"] for t in c.get("obs", {}).get("terms", []))
    declared = c.get("obs", {}).get("total_dim")
    if total != declared:
        fail(f"obs.terms suma {total} pero obs.total_dim dice {declared}")

    return c


def require_policy_ready(c: dict) -> dict:
    """Compatibilidad con el esquema v2. En v3 load_contract ya valida todo."""
    return c


# ---------------------------------------------------------------------------
# Conversion de ordenes
# ---------------------------------------------------------------------------
def joint_map(c: dict) -> np.ndarray:
    """joint_ids_map como array: indice de motor para cada slot de politica."""
    return np.asarray(c["policy"]["joint_ids_map"], dtype=np.int64)


def motor_to_policy(vec_motor, c: dict) -> np.ndarray:
    """Reordena un vector de 12 de orden MOTOR a orden POLITICA."""
    v = np.asarray(vec_motor, dtype=np.float32)
    if v.shape[-1] != N_JOINTS:
        raise ContractError(f"se esperaban {N_JOINTS} elementos, hay {v.shape[-1]}")
    return v[joint_map(c)]


def policy_to_motor(vec_policy, c: dict) -> np.ndarray:
    """Reordena un vector de 12 de orden POLITICA a orden MOTOR."""
    v = np.asarray(vec_policy, dtype=np.float32)
    if v.shape[-1] != N_JOINTS:
        raise ContractError(f"se esperaban {N_JOINTS} elementos, hay {v.shape[-1]}")
    out = np.empty(N_JOINTS, dtype=np.float32)
    out[joint_map(c)] = v
    return out


# ---------------------------------------------------------------------------
# Accesos con el orden ya resuelto
# ---------------------------------------------------------------------------
def policy_defaults_motor(c: dict) -> np.ndarray:
    """default_joint_pos de la politica, expresado en orden MOTOR."""
    return policy_to_motor(c["policy"]["default_joint_pos"], c)


def policy_gains_motor(c: dict) -> tuple[np.ndarray, np.ndarray]:
    """(kp, kd) de la politica, en orden MOTOR."""
    g = c["policy"]["gains"]
    return policy_to_motor(g["kp"], c), policy_to_motor(g["kd"], c)


def fsm_gains(c: dict, state: str) -> tuple[np.ndarray, np.ndarray]:
    """(kp, kd) de un estado del FSM. Ya vienen en orden MOTOR."""
    g = c["fsm"]["gains"][state]
    return (np.asarray(g["kp"], dtype=np.float32),
            np.asarray(g["kd"], dtype=np.float32))


def fsm_pose(c: dict, name: str) -> np.ndarray:
    """Pose del FSM en orden MOTOR."""
    return np.asarray(c["fsm"]["poses"][name], dtype=np.float32)


def obs_layout(c: dict) -> list[tuple[str, int, int]]:
    """[(nombre, inicio, fin)] de cada bloque del vector de observaciones."""
    out, i = [], 0
    for t in c["obs"]["terms"]:
        out.append((t["name"], i, i + t["dim"]))
        i += t["dim"]
    return out


def _r(v, nd: int = 3) -> list:
    """Redondeo legible de un vector float32."""
    return [round(float(x), nd) for x in np.asarray(v).ravel()]


def describe(c: dict) -> str:
    """Resumen legible del contrato. Util para meterlo en el manifest de un run."""
    lines = [
        f"Contrato v{c['meta']['version']} - {c['meta']['robot']}",
        f"  politica     : {c['policy']['path']}  ({c['policy']['format']})",
        f"  obs          : {c['obs']['total_dim']} dims -> "
        + ", ".join(f"{n}[{a}:{b}]" for n, a, b in obs_layout(c)),
        f"  ctrl         : {c['policy']['ctrl_hz']} Hz politica / "
        f"{c['policy']['publish_hz']} Hz LowCmd",
        f"  offset (motor): {_r(policy_defaults_motor(c))}",
        f"  kp (motor)   : {_r(policy_gains_motor(c)[0])}",
        f"  kd (motor)   : {_r(policy_gains_motor(c)[1])}",
        f"  seguridad    : {c['safety']}",
    ]
    return "\n".join(lines)
