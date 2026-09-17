#!/usr/bin/env python3
"""usecases/uc01_locomotion/eval/eval_sim.py  (v3)

Evaluacion reproducible de una politica de locomocion en unitree_mujoco.

CAMBIOS DE LA v3
----------------
1. La tabla muestra COMANDO, MEDIDO y SEGUIMIENTO %, no el error. La v2
   imprimia una columna `err vx` que se confundio con la velocidad medida: un
   0.293 de error con comando 0.3 se leyo como "sigue el comando al 98 %"
   cuando significaba justo lo contrario.

2. La velocidad se calcula por DESPLAZAMIENTO NETO del segmento dividido por
   su duracion, no promediando diferencias finitas paso a paso. Un solo numero,
   sin depender de cuantas muestras de sportmodestate lleguen. Se calcula
   tambien la media de diferencias finitas y se marca si discrepan.

3. Metricas de MARCHA ademas de seguimiento. El seguimiento por si solo no
   mide lo que parece: una politica que desliza el cuerpo con las patas rigidas
   puede puntuar bien, gastar poca energia y no caerse, y en el robot real se
   caeria o destrozaria los pies. El discriminador es la desviacion tipica de
   la altura del tronco, calculada desde los angulos articulares: si el robot
   da pasos, oscila.

   Umbrales calibrados con tres politicas reales (2026-09-16):
       caminan (15 min, legacy) -> h_sd 0.006 a 0.010
       no camina (5 min)        -> h_sd 0.0005 a 0.0016
   Frontera en 0.004.

4. Veredicto de validez por politica. Una politica que no camina queda
   registrada como tal en vez de aportar una fila enganosa a la curva.

VERDAD-TERRENO
--------------
`lowstate` no da velocidad de la base. En simulacion, unitree_mujoco publica
`rt/sportmodestate` con la posicion real del tronco. La velocidad angular sale
del giroscopo, que si esta en `lowstate`.

En el ROBOT REAL nada de esto esta disponible: al liberar sport_mode el
servicio deja de publicar. El protocolo real es distinto (distancia recorrida
en tiempo fijo, con marcas en el suelo) y va en eval_real.py.

Uso:
    python3 usecases/uc01_locomotion/eval/eval_sim.py \\
        --policy experiments/uc01_locomotion/<run_id>/checkpoints/policy.onnx \\
        --rollouts 3 --out experiments/uc01_locomotion/<run_id>/
"""

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse          # noqa: E402
import csv               # noqa: E402
import json              # noqa: E402
import math              # noqa: E402
import statistics as st  # noqa: E402
import sys               # noqa: E402
import threading         # noqa: E402
import time              # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path       # noqa: E402

import numpy as np       # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from go2core.control import contract as ct                 # noqa: E402
from go2core.control.lowlevel import LowLevel, SafetyTrip  # noqa: E402

DEFAULT_CONTRACT = REPO_ROOT / "usecases/uc01_locomotion/configs/robot_go2.yaml"

# Secuencia fija. Identica en todos los rollouts y todas las politicas: es lo
# que hace los resultados comparables.  (vx, vy, wz, segundos)
SCHEDULE = [
    (0.0, 0.0, 0.0, 3.0),
    (0.3, 0.0, 0.0, 6.0),
    (0.6, 0.0, 0.0, 6.0),
    (0.0, 0.0, 0.5, 6.0),
    (0.0, 0.3, 0.0, 6.0),
    (0.0, 0.0, 0.0, 3.0),
]

H_SD_CAMINA = 0.004      # frontera calibrada con datos reales
P_MIN_CAMINA = 8.0       # W mecanicos minimos de una marcha real


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


def to_body(dp: np.ndarray, yaw: float) -> np.ndarray:
    """Desplazamiento mundial rotado al plano del cuerpo (x adelante, y izq)."""
    cy, sy = math.cos(-yaw), math.sin(-yaw)
    return np.asarray([cy * dp[0] - sy * dp[1], sy * dp[0] + cy * dp[1]],
                      dtype=np.float64)


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


def veredicto_segmento(cmd_speed: float, cmd_yaw: float, h_sd: float,
                       potencia: float, seguimiento: float | None) -> str:
    """Etiqueta el segmento. Se decide por el COMANDO, no por lo medido: un
    segmento donde se pidio andar y el robot no se movio es un FALLO, no un
    'quieto esperado'."""
    if cmd_speed < 0.05 and abs(cmd_yaw) < 0.05:
        return "reposo (sin comando)"
    if seguimiento is not None and seguimiento < 0.15:
        return "NO OBEDECE"
    if h_sd < H_SD_CAMINA and potencia < P_MIN_CAMINA:
        return "DESLIZA (patas rigidas)"
    if h_sd < H_SD_CAMINA:
        return "SOSPECHOSO (altura plana)"
    if seguimiento is not None and seguimiento < 0.4:
        return "camina, seguimiento pobre"
    return "camina"


def run_rollout(idx: int, ll: LowLevel, gt: GroundTruth, c: dict, sess,
                in_name: str, out_name: str, mass_kg: float,
                fall_tilt: float, rows: list) -> dict:
    kp_pol, kd_pol = ct.policy_gains_motor(c)
    offset_motor = ct.policy_defaults_motor(c)
    scale = np.asarray(c["policy"]["action"]["scale"], dtype=np.float32)
    offset_p = np.asarray(c["policy"]["action"]["offset"], dtype=np.float32)
    step_dt = float(c["policy"]["step_dt"])
    period = float(c["obs"]["gait_phase"]["period_s"])

    print(f"\n--- rollout {idx} ---")
    ramp_to(ll, offset_motor, kp_pol, kd_pol, 1.5)
    if ll.height_proxy() < 0.18:
        print(f"  ABORTADO: no se levanta (altura {ll.height_proxy():.3f} m)")
        return {"rollout": idx, "valid": False, "motivo": "no se levanta",
                "segments": []}

    last_action = np.zeros(12, dtype=np.float32)
    phase = 0.0
    fell = False
    segments = []
    t_roll = time.monotonic()
    next_tick = time.monotonic()

    for seg_i, (vx, vy, wz, secs) in enumerate(SCHEDULE):
        cmd = np.asarray([vx, vy, wz], dtype=np.float32)
        fd_vx, wz_meas, power, tilts, heights = [], [], [], [], []

        # Referencia para el desplazamiento NETO del segmento.
        pos0, _ = gt.get()
        yaw0 = yaw_from_quat(ll.quaternion())
        t_seg0 = time.monotonic()
        prev_pos, prev_t = pos0, t_seg0

        while time.monotonic() - t_seg0 < secs:
            try:
                ll.check_safety()
            except SafetyTrip as e:
                print(f"  disparo de seguridad en seg {seg_i}: {e}")
                fell = True
                break

            phase = (phase + step_dt / period) % 1.0
            obs = build_obs(ll, c, cmd, phase, last_action)
            act = sess.run([out_name], {in_name: obs})[0].reshape(-1)[:12]
            last_action = act.astype(np.float32)
            ll.set_command_clamped(ct.policy_to_motor(act * scale + offset_p, c),
                                   kp_pol, kd_pol, offset_motor)

            pos, t_now = gt.get()
            dt_gt = t_now - prev_t
            if dt_gt > 1e-3:
                v = to_body(pos - prev_pos, yaw_from_quat(ll.quaternion())) / dt_gt
                fd_vx.append(float(v[0]))
                prev_pos, prev_t = pos, t_now
            wz_meas.append(float(ll.gyro()[2]))

            tau, dq = ll.joint_tau(), ll.joint_dq()
            power.append(float(np.sum(np.abs(tau * dq))))
            h = ll.height_proxy()
            heights.append(h)
            tilt = ll.tilt_rad()
            tilts.append(tilt)
            if tilt > fall_tilt:
                print(f"  CAIDA en seg {seg_i} (inclinacion "
                      f"{math.degrees(tilt):.0f} deg)")
                fell = True
                break

            rows.append([idx, seg_i, f"{time.monotonic() - t_roll:.3f}",
                         vx, vy, wz,
                         f"{fd_vx[-1] if fd_vx else 0.0:.4f}",
                         f"{wz_meas[-1]:.4f}", f"{tilt:.4f}", f"{h:.4f}",
                         f"{power[-1]:.2f}", f"{np.abs(tau).max():.2f}"])

            next_tick += step_dt
            time.sleep(max(0.0, next_tick - time.monotonic()))

        # --- medida robusta: desplazamiento NETO / duracion ---
        dur = max(time.monotonic() - t_seg0, 1e-6)
        pos1, _ = gt.get()
        d_body = to_body(pos1 - pos0, yaw0)
        net_vx, net_vy = d_body[0] / dur, d_body[1] / dur

        h_sd = st.pstdev(heights) if len(heights) > 1 else 0.0
        p_mean = st.mean(power) if power else 0.0
        wz_mean = st.mean(wz_meas) if wz_meas else 0.0
        speed_cmd = math.hypot(vx, vy)

        if speed_cmd > 0.05:
            seguimiento = math.hypot(net_vx, net_vy) / speed_cmd
        elif abs(wz) > 0.05:
            seguimiento = abs(wz_mean) / abs(wz)
        else:
            seguimiento = None

        cot = (p_mean / (mass_kg * 9.81 * abs(net_vx))
               if abs(net_vx) > 0.05 and p_mean > 0 else None)

        v = veredicto_segmento(speed_cmd, wz, h_sd, p_mean, seguimiento)

        fd_mean = st.mean(fd_vx) if fd_vx else 0.0
        discrepa = abs(fd_mean - net_vx) > max(0.05, 0.25 * abs(net_vx))

        segments.append({
            "segment": seg_i, "cmd": [vx, vy, wz],
            "vx_neto": round(net_vx, 4), "vy_neto": round(net_vy, 4),
            "wz_medido": round(wz_mean, 4),
            "vx_dif_finitas": round(fd_mean, 4),
            "discrepancia_metodos": bool(discrepa),
            "seguimiento": round(seguimiento, 3) if seguimiento is not None else None,
            "distancia_m": round(float(math.hypot(d_body[0], d_body[1])), 3),
            "h_sd": round(h_sd, 4),
            "potencia_W": round(p_mean, 1),
            "CoT": round(cot, 3) if cot else None,
            "inclinacion_max_deg": round(math.degrees(max(tilts)), 1) if tilts else None,
            "veredicto": v,
        })
        if fell:
            break

    ll.go_passive()
    time.sleep(1.0)
    return {"rollout": idx, "valid": True, "fell": fell,
            "duracion_s": round(time.monotonic() - t_roll, 1),
            "segments": segments}


def tabla(segs: list[dict]) -> None:
    print(f"\n  {'seg':>3} {'comando':<17} {'medido':>9} {'segui':>7} "
          f"{'dist':>7} {'h sd':>7} {'P(W)':>6} {'CoT':>6}  veredicto")
    for s in segs:
        vx, vy, wz = s["cmd"]
        if abs(vx) > 0.05:
            med = f"{s['vx_neto']:+.3f}"
        elif abs(vy) > 0.05:
            med = f"{s['vy_neto']:+.3f}"
        else:
            med = f"{s['wz_medido']:+.3f}"
        seg = f"{100 * s['seguimiento']:5.0f}%" if s["seguimiento"] is not None else "    -"
        cot = f"{s['CoT']:.3f}" if s["CoT"] else "    -"
        flag = "  [!] metodos discrepan" if s["discrepancia_metodos"] else ""
        print(f"  {s['segment']:>3} ({vx:+.1f},{vy:+.1f},{wz:+.1f})      "
              f"{med:>9} {seg:>7} {s['distancia_m']:7.2f} {s['h_sd']:7.4f} "
              f"{s['potencia_W']:6.1f} {cot:>6}  {s['veredicto']}{flag}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--policy", default=None)
    p.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    p.add_argument("--rollouts", type=int, default=3)
    p.add_argument("--publish-hz", type=float, default=200.0)
    p.add_argument("--mass-kg", type=float, default=None)
    p.add_argument("--fall-tilt-deg", type=float, default=50.0)
    p.add_argument("--out", default=None)
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
          f"{sum(s[3] for s in SCHEDULE):.0f} s por rollout")
    print(f"umbral de marcha: h_sd >= {H_SD_CAMINA}, potencia >= {P_MIN_CAMINA} W\n")

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
        print(f"verdad-terreno OK ({gt.n} mensajes)")

        for i in range(1, args.rollouts + 1):
            r = run_rollout(i, ll, gt, c, sess, in_name, out_name, mass,
                            math.radians(args.fall_tilt_deg), rows)
            results.append(r)
            if r.get("segments"):
                tabla(r["segments"])
    except KeyboardInterrupt:
        print("\ninterrumpido")
    finally:
        ll.stop()

    # ---------------- agregado ----------------
    validos = [r for r in results if r.get("valid")]
    caidas = sum(1 for r in validos if r.get("fell"))

    por_seg: dict[int, dict[str, list]] = {}
    for r in validos:
        for s in r["segments"]:
            d = por_seg.setdefault(s["segment"],
                                   {"seg": [], "hsd": [], "cot": [], "ver": []})
            if s["seguimiento"] is not None:
                d["seg"].append(s["seguimiento"])
            d["hsd"].append(s["h_sd"])
            if s["CoT"]:
                d["cot"].append(s["CoT"])
            d["ver"].append(s["veredicto"])

    print("\n" + "=" * 78)
    print(f"rollouts validos: {len(validos)}/{args.rollouts} | "
          f"caidas: {caidas}/{max(len(validos), 1)}")
    print(f"\n  {'seg':>3} {'comando':<17} {'seguimiento':>12} {'h sd':>8} "
          f"{'CoT':>7}  veredicto dominante")
    for i, d in sorted(por_seg.items()):
        vx, vy, wz, _ = SCHEDULE[i]
        sg = f"{100 * st.mean(d['seg']):10.0f} %" if d["seg"] else "         -"
        cot = f"{st.mean(d['cot']):.3f}" if d["cot"] else "      -"
        dom = max(set(d["ver"]), key=d["ver"].count)
        print(f"  {i:>3} ({vx:+.1f},{vy:+.1f},{wz:+.1f})      {sg:>12} "
              f"{st.mean(d['hsd']):8.4f} {cot:>7}  {dom}")

    # ---------------- veredicto de la politica ----------------
    con_cmd = [s for r in validos for s in r["segments"]
               if s["veredicto"] != "reposo (sin comando)"]
    malos = [s for s in con_cmd
             if s["veredicto"].startswith(("NO OBEDECE", "DESLIZA", "SOSPECHOSO"))]
    camina = len(malos) < len(con_cmd) / 2 if con_cmd else False

    print(f"\n  segmentos con comando: {len(con_cmd)} | degenerados: {len(malos)}")
    print("=" * 78)
    if camina and caidas == 0:
        print("  VEREDICTO: la politica CAMINA. Sus metricas son comparables.")
    elif camina:
        print(f"  VEREDICTO: camina pero se cae ({caidas} de {len(validos)}).")
    else:
        print("  VEREDICTO: la politica NO CAMINA de forma fiable.")
        print("  Sus numeros de seguimiento NO son comparables con los de una")
        print("  politica que si camina. Registrar el run como no valido para la")
        print("  curva, no descartarlo: que un presupuesto no baste para aprender")
        print("  a andar ES un resultado.")

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        with open(out / "metrics_sim.csv", "w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["rollout", "segment", "t", "vx_cmd", "vy_cmd", "wz_cmd",
                        "vx_med", "wz_med", "tilt_rad", "height",
                        "power_W", "tau_max"])
            w.writerows(rows)
        resumen = {
            "fecha": datetime.now().isoformat(timespec="seconds"),
            "evaluador_version": 3,
            "politica": str(policy_path),
            "masa_kg": mass,
            "rollouts": args.rollouts,
            "rollouts_validos": len(validos),
            "caidas": caidas,
            "camina": camina,
            "umbral_h_sd": H_SD_CAMINA,
            "schedule": [list(s) for s in SCHEDULE],
            "resultados": results,
            "entorno": "unitree_mujoco simulate_python, domain 1, lo, escena plana",
        }
        (out / "eval_sim.json").write_text(
            json.dumps(resumen, indent=2, ensure_ascii=False))
        print(f"\n  escrito: {out / 'metrics_sim.csv'}")
        print(f"           {out / 'eval_sim.json'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
