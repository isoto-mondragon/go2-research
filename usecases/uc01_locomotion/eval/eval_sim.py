#!/usr/bin/env python3
"""usecases/uc01_locomotion/eval/eval_sim.py

Evaluacion reproducible de una politica de locomocion en unitree_mujoco.

Ejecuta N rollouts con la MISMA secuencia de comandos y mide:

  - error de seguimiento de velocidad (vx, vy, wz) contra verdad-terreno
  - tasa de caida
  - coste de transporte (CoT), la metrica de la linea de investigacion
    energetica
  - par maximo por articulacion

VERDAD-TERRENO
--------------
`lowstate` no da velocidad de la base. En simulacion, unitree_mujoco publica
`rt/sportmodestate` con la posicion real del tronco: de ahi se deriva la
velocidad por diferencias finitas y se rota al sistema del cuerpo con el
cuaternion de `lowstate`. La velocidad angular sale del giroscopo, que si esta
en `lowstate` y es directa.

En el ROBOT REAL esto NO esta disponible: al liberar sport_mode el servicio
deja de publicar. El protocolo real es distinto (distancia recorrida en tiempo
fijo, medida con marcas en el suelo) y va en eval_real.py.

LIMITACION CONOCIDA
-------------------
No se puede reiniciar el simulador desde fuera, asi que los rollouts sucesivos
parten del estado en que quedo el anterior. Entre rollouts se pasa por passive
y se vuelve a levantar, y se registra la pose de partida de cada uno. Para
comparaciones estrictas entre politicas, relanzar el simulador entre
invocaciones y usar --rollouts 1.

Uso:
    python3 usecases/uc01_locomotion/eval/eval_sim.py \\
        --policy experiments/uc01_locomotion/<run_id>/checkpoints/policy.onnx \\
        --rollouts 3 --out experiments/uc01_locomotion/<run_id>/
"""

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse       # noqa: E402
import csv            # noqa: E402
import json           # noqa: E402
import math           # noqa: E402
import statistics as st  # noqa: E402
import sys            # noqa: E402
import threading      # noqa: E402
import time           # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path       # noqa: E402

import numpy as np    # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from go2core.control import contract as ct                 # noqa: E402
from go2core.control.lowlevel import LowLevel, SafetyTrip  # noqa: E402

DEFAULT_CONTRACT = REPO_ROOT / "usecases/uc01_locomotion/configs/robot_go2.yaml"

# Secuencia fija de comandos. Identica en todos los rollouts y todas las
# politicas: es lo que hace los resultados comparables.
# (vx, vy, wz, segundos)
SCHEDULE = [
    (0.0, 0.0, 0.0, 3.0),    # asentarse
    (0.3, 0.0, 0.0, 6.0),
    (0.6, 0.0, 0.0, 6.0),
    (0.0, 0.0, 0.5, 6.0),
    (0.0, 0.3, 0.0, 6.0),
    (0.0, 0.0, 0.0, 3.0),
]


class GroundTruth:
    """Posicion del tronco desde rt/sportmodestate (solo simulacion)."""

    def __init__(self) -> None:
        self.pos = np.zeros(3, dtype=np.float64)
        self.t = 0.0
        self.n = 0
        self._lock = threading.Lock()

    def start(self) -> bool:
        try:
            from unitree_sdk2py.core.channel import ChannelSubscriber
            from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_
        except ImportError:
            return False
        ChannelSubscriber("rt/sportmodestate", SportModeState_).Init(self._on, 10)
        return True

    def _on(self, m) -> None:
        with self._lock:
            self.pos = np.asarray(m.position, dtype=np.float64)
            self.t = time.monotonic()
            self.n += 1

    def get(self) -> tuple[np.ndarray, float]:
        with self._lock:
            return self.pos.copy(), self.t


def yaw_from_quat(q: np.ndarray) -> float:
    w, x, y, z = q
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def body_velocity(dp: np.ndarray, dt: float, yaw: float) -> np.ndarray:
    """Velocidad mundial rotada al plano del cuerpo (vx adelante, vy izquierda)."""
    if dt <= 0:
        return np.zeros(2, dtype=np.float32)
    vw = dp[:2] / dt
    cy, sy = math.cos(-yaw), math.sin(-yaw)
    return np.asarray([cy * vw[0] - sy * vw[1], sy * vw[0] + cy * vw[1]], dtype=np.float32)


def build_obs(ll: LowLevel, c: dict, cmd: np.ndarray, phase: float,
              last_action: np.ndarray) -> np.ndarray:
    """Identico a run_policy.py. Si cambia alli, cambia aqui."""
    obs_cfg = c["obs"]
    gait = np.asarray([math.sin(phase * 2 * math.pi),
                       math.cos(phase * 2 * math.pi)], dtype=np.float32)
    if float(np.linalg.norm(cmd)) < float(obs_cfg["gait_phase"]["zero_below_cmd_norm"]):
        gait[:] = 0.0

    default_p = np.asarray(c["policy"]["default_joint_pos"], dtype=np.float32)
    blocks = {
        "base_ang_vel": ll.gyro(),
        "projected_gravity": ll.projected_gravity(),
        "velocity_commands": cmd,
        "gait_phase": gait,
        "joint_pos_rel": ct.motor_to_policy(ll.joint_q(), c) - default_p,
        "joint_vel_rel": ct.motor_to_policy(ll.joint_dq(), c),
        "last_action": last_action,
    }
    parts = [np.asarray(blocks[t["name"]], dtype=np.float32) * float(t["scale"])
             for t in obs_cfg["terms"]]
    return np.concatenate(parts).astype(np.float32)[None, :]


def ramp_to(ll: LowLevel, q_to: np.ndarray, kp: np.ndarray, kd: np.ndarray,
            seconds: float) -> None:
    q_from = ll.joint_q()
    t0 = time.monotonic()
    while True:
        a = min((time.monotonic() - t0) / seconds, 1.0)
        a = a * a * (3.0 - 2.0 * a)
        ll.set_command((1 - a) * q_from + a * q_to, kp, kd)
        ll.check_safety(check_tilt=False, transient=True)
        if a >= 1.0:
            break
        time.sleep(0.004)
    time.sleep(0.3)


def run_rollout(idx: int, ll: LowLevel, gt: GroundTruth, c: dict, sess, in_name: str,
                out_name: str, mass_kg: float, fall_tilt_rad: float,
                rows: list) -> dict:
    """Un rollout completo. Devuelve metricas agregadas por segmento."""
    kp_pol, kd_pol = ct.policy_gains_motor(c)
    offset_motor = ct.policy_defaults_motor(c)
    scale = np.asarray(c["policy"]["action"]["scale"], dtype=np.float32)
    offset_p = np.asarray(c["policy"]["action"]["offset"], dtype=np.float32)
    step_dt = float(c["policy"]["step_dt"])
    period = float(c["obs"]["gait_phase"]["period_s"])

    print(f"\n--- rollout {idx} ---")
    print(f"  pose de partida: altura ~{ll.height_proxy():.3f} m")
    ramp_to(ll, offset_motor, kp_pol, kd_pol, 1.5)
    h0 = ll.height_proxy()
    if h0 < 0.18:
        print(f"  ABORTADO: no se ha levantado (altura {h0:.3f} m)")
        return {"rollout": idx, "valid": False, "reason": "no se levanta", "segments": []}

    last_action = np.zeros(12, dtype=np.float32)
    phase = 0.0
    fell = False
    segments = []
    t_roll = time.monotonic()

    prev_pos, prev_t = gt.get()
    next_tick = time.monotonic()

    for seg_i, (vx, vy, wz, secs) in enumerate(SCHEDULE):
        cmd = np.asarray([vx, vy, wz], dtype=np.float32)
        meas_vx, meas_vy, meas_wz, power, tilts = [], [], [], [], []
        t_seg = time.monotonic()

        while time.monotonic() - t_seg < secs:
            try:
                ll.check_safety()
            except SafetyTrip as e:
                print(f"  caida/disparo en segmento {seg_i}: {e}")
                fell = True
                break

            phase = (phase + step_dt / period) % 1.0
            obs = build_obs(ll, c, cmd, phase, last_action)
            act = sess.run([out_name], {in_name: obs})[0].reshape(-1)[:12]
            last_action = act.astype(np.float32)
            ll.set_command_clamped(ct.policy_to_motor(act * scale + offset_p, c),
                                   kp_pol, kd_pol, offset_motor)

            # --- medidas ---
            pos, t_now = gt.get()
            dt_gt = t_now - prev_t
            if dt_gt > 1e-3:
                v_body = body_velocity(pos - prev_pos, dt_gt, yaw_from_quat(ll.quaternion()))
                meas_vx.append(float(v_body[0]))
                meas_vy.append(float(v_body[1]))
                prev_pos, prev_t = pos, t_now
            meas_wz.append(float(ll.gyro()[2]))

            tau, dq = ll.joint_tau(), ll.joint_dq()
            power.append(float(np.sum(np.abs(tau * dq))))    # W mecanicos
            tilt = ll.tilt_rad()
            tilts.append(tilt)
            if tilt > fall_tilt_rad:
                print(f"  caida en segmento {seg_i}: inclinacion "
                      f"{np.degrees(tilt):.0f} deg")
                fell = True
                break

            rows.append([idx, seg_i, f"{time.monotonic() - t_roll:.3f}",
                         vx, vy, wz,
                         f"{meas_vx[-1] if meas_vx else 0.0:.4f}",
                         f"{meas_vy[-1] if meas_vy else 0.0:.4f}",
                         f"{meas_wz[-1]:.4f}", f"{tilt:.4f}",
                         f"{ll.height_proxy():.4f}", f"{power[-1]:.2f}",
                         f"{np.abs(tau).max():.2f}"])

            next_tick += step_dt
            time.sleep(max(0.0, next_tick - time.monotonic()))

        speed = math.hypot(vx, vy)
        mean_p = st.mean(power) if power else 0.0
        cot = (mean_p / (mass_kg * 9.81 * speed)) if speed > 0.05 and mean_p > 0 else None

        segments.append({
            "segment": seg_i,
            "cmd": [vx, vy, wz],
            "vx_med": round(st.mean(meas_vx), 4) if meas_vx else None,
            "vy_med": round(st.mean(meas_vy), 4) if meas_vy else None,
            "wz_med": round(st.mean(meas_wz), 4) if meas_wz else None,
            "err_vx": round(abs(vx - st.mean(meas_vx)), 4) if meas_vx else None,
            "err_wz": round(abs(wz - st.mean(meas_wz)), 4) if meas_wz else None,
            "potencia_media_W": round(mean_p, 2),
            "CoT": round(cot, 3) if cot else None,
            "inclinacion_max_deg": round(math.degrees(max(tilts)), 1) if tilts else None,
        })
        print(f"  seg {seg_i} cmd=({vx:+.1f},{vy:+.1f},{wz:+.1f}) "
              f"medido=({segments[-1]['vx_med']},{segments[-1]['vy_med']},"
              f"{segments[-1]['wz_med']}) "
              f"P={mean_p:.0f}W CoT={segments[-1]['CoT']}")
        if fell:
            break

    ll.go_passive()
    time.sleep(1.0)
    return {"rollout": idx, "valid": True, "fell": fell,
            "duracion_s": round(time.monotonic() - t_roll, 1), "segments": segments}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--policy", default=None, help="ruta al .onnx (defecto: el del contrato)")
    p.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    p.add_argument("--rollouts", type=int, default=3)
    p.add_argument("--publish-hz", type=float, default=200.0)
    p.add_argument("--mass-kg", type=float, default=None,
                   help="masa del robot para el CoT (defecto: hardware.mass_kg o 15.0)")
    p.add_argument("--fall-tilt-deg", type=float, default=50.0)
    p.add_argument("--out", default=None, help="carpeta donde escribir metricas y resumen")
    args = p.parse_args()

    c = ct.load_contract(args.contract)
    mass = args.mass_kg or float(c.get("hardware", {}).get("mass_kg", 15.0))

    import onnxruntime as ort
    policy_path = Path(args.policy) if args.policy else REPO_ROOT / c["policy"]["path"]
    if not policy_path.exists():
        print(f"No existe la politica: {policy_path}")
        return 2
    so = ort.SessionOptions()
    so.intra_op_num_threads = 1
    so.inter_op_num_threads = 1
    sess = ort.InferenceSession(str(policy_path), sess_options=so,
                                providers=["CPUExecutionProvider"])
    in_name, out_name = sess.get_inputs()[0].name, sess.get_outputs()[0].name
    if int(sess.get_inputs()[0].shape[-1]) != c["obs"]["total_dim"]:
        print("El ONNX no cuadra con el contrato. No se evalua.")
        return 2

    print(f"politica : {policy_path}")
    print(f"masa     : {mass} kg | rollouts: {args.rollouts}")
    print(f"secuencia: {len(SCHEDULE)} segmentos, "
          f"{sum(s[3] for s in SCHEDULE):.0f} s por rollout\n")

    ll = LowLevel(c, mode="sim")
    ll.publish_dt = 1.0 / args.publish_hz
    gt = GroundTruth()

    rows: list = []
    results: list = []
    try:
        ll.start()
        if not gt.start():
            print("No se puede suscribir a rt/sportmodestate.")
            return 2
        time.sleep(0.5)
        if gt.n == 0:
            print("rt/sportmodestate no publica. Sin verdad-terreno no hay evaluacion.")
            return 2
        print(f"verdad-terreno OK ({gt.n} mensajes)\n")

        for i in range(1, args.rollouts + 1):
            results.append(run_rollout(i, ll, gt, c, sess, in_name, out_name,
                                       mass, math.radians(args.fall_tilt_deg), rows))
    except KeyboardInterrupt:
        print("\ninterrumpido")
    finally:
        ll.stop()

    # --- agregado ---
    valid = [r for r in results if r.get("valid")]
    fells = sum(1 for r in valid if r.get("fell"))
    print("\n" + "=" * 60)
    print(f"rollouts validos : {len(valid)}/{args.rollouts}")
    print(f"caidas           : {fells}/{max(len(valid), 1)} "
          f"({100.0 * fells / max(len(valid), 1):.0f} %)")

    by_seg: dict[int, dict[str, list]] = {}
    for r in valid:
        for s in r["segments"]:
            d = by_seg.setdefault(s["segment"], {"err_vx": [], "err_wz": [], "cot": []})
            for k, key in (("err_vx", "err_vx"), ("err_wz", "err_wz"), ("cot", "CoT")):
                if s.get(key) is not None:
                    d[k].append(s[key])

    print(f"\n  {'seg':>3} {'comando':<18} {'err vx':>8} {'err wz':>8} {'CoT':>8}")
    for seg_i, d in sorted(by_seg.items()):
        vx, vy, wz, _ = SCHEDULE[seg_i]
        ev = f"{st.mean(d['err_vx']):.3f}" if d["err_vx"] else "-"
        ew = f"{st.mean(d['err_wz']):.3f}" if d["err_wz"] else "-"
        ct_ = f"{st.mean(d['cot']):.3f}" if d["cot"] else "-"
        print(f"  {seg_i:>3} ({vx:+.1f},{vy:+.1f},{wz:+.1f})       {ev:>8} {ew:>8} {ct_:>8}")

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        with open(out / "metrics_sim.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["rollout", "segment", "t", "vx_cmd", "vy_cmd", "wz_cmd",
                        "vx_med", "vy_med", "wz_med", "tilt_rad", "height",
                        "power_W", "tau_max"])
            w.writerows(rows)
        summary = {
            "fecha": datetime.now().isoformat(timespec="seconds"),
            "politica": str(policy_path),
            "masa_kg": mass,
            "rollouts": args.rollouts,
            "rollouts_validos": len(valid),
            "tasa_caida": round(fells / max(len(valid), 1), 3),
            "schedule": [list(s) for s in SCHEDULE],
            "resultados": results,
            "entorno": "unitree_mujoco simulate_python, domain 1, lo",
            "limitacion": ("los rollouts sucesivos parten del estado del anterior; "
                           "para comparaciones estrictas relanzar el simulador y usar "
                           "--rollouts 1"),
        }
        (out / "eval_sim.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
        print(f"\nescrito: {out / 'metrics_sim.csv'}")
        print(f"         {out / 'eval_sim.json'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
