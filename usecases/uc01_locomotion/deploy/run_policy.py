#!/usr/bin/env python3
"""Despliegue de la politica de locomocion Go2 (ONNX) sobre DDS.

FSM de tres estados, igual que la config heredada del workspace WSL2:

    PASSIVE  -> amortiguacion pura (kp=0, kd=3). Estado seguro de entrada y salida.
    FIXSTAND -> rampa a crouch y luego a stand, con las ganancias del FSM.
    VELOCITY -> rampa al offset de la politica y bucle de inferencia ONNX.

SOBRE LEVANTARSE
----------------
Levantarse depende del IMPULSO: las patas tienen que meterse bajo el cuerpo y
empujar antes de que la gravedad las abra. Una rampa lenta da tiempo a que el
robot se abra de patas y se quede atascado: una vez abiertas 0.5 rad, cerrar la
cadera exige 60*0.5 = 30 Nm y el tope de la cadera son 23.7. Por eso Unitree
usa 1 segundo por tramo, y por eso la duracion de la rampa es un parametro que
se mide, no que se supone.

Antes de entregar el control a la politica se comprueba que el robot esta
realmente de pie. Arrancar la politica desde una pose desparramada la mete en
una observacion fuera de distribucion y el resultado no informa de nada.

DEPURACION
----------
    --stand-only        solo el FSM, sin cargar la politica
    --stand-mode direct rampa directa al offset de la politica, sin FIXSTAND
    --ramp-s 1.0        duracion de cada tramo de rampa (anula el contrato)
    --kp-scale 1.5      multiplica las ganancias de FIXSTAND
    --no-torque-trip    no aborta por saturacion de par (SOLO simulacion)
    --diag              tabla de par por articulacion cada segundo

Barrido tipico para encontrar la combinacion que levanta al robot:
    for R in 0.5 0.8 1.0 1.5; do
      python3 .../run_policy.py --mode sim --stand-only --ramp-s $R --duration 3
    done
"""

from __future__ import annotations

import argparse
import csv
import math
import signal
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from go2core.control import contract as ct          # noqa: E402
from go2core.control.lowlevel import LowLevel, SafetyTrip  # noqa: E402

DEFAULT_CONTRACT = REPO_ROOT / "usecases/uc01_locomotion/configs/robot_go2.yaml"


# ---------------------------------------------------------------------------
def build_obs(ll: LowLevel, c: dict, cmd: np.ndarray, phase: float,
              last_action: np.ndarray) -> np.ndarray:
    """Vector de 47 dimensiones en el orden EXACTO del contrato.

    Los bloques articulares van en ORDEN POLITICA; la conversion se hace aqui
    y solo aqui, via go2core.control.contract.
    """
    obs_cfg = c["obs"]
    thresh = float(obs_cfg["gait_phase"]["zero_below_cmd_norm"])

    gait = np.asarray([math.sin(phase * 2 * math.pi),
                       math.cos(phase * 2 * math.pi)], dtype=np.float32)
    if float(np.linalg.norm(cmd)) < thresh:
        gait[:] = 0.0

    default_p = np.asarray(c["policy"]["default_joint_pos"], dtype=np.float32)
    q_p = ct.motor_to_policy(ll.joint_q(), c)
    dq_p = ct.motor_to_policy(ll.joint_dq(), c)

    blocks = {
        "base_ang_vel": ll.gyro(),
        "projected_gravity": ll.projected_gravity(),
        "velocity_commands": cmd,
        "gait_phase": gait,
        "joint_pos_rel": q_p - default_p,
        "joint_vel_rel": dq_p,
        "last_action": last_action,
    }

    parts = []
    for term in obs_cfg["terms"]:
        v = np.asarray(blocks[term["name"]], dtype=np.float32) * float(term["scale"])
        if v.shape != (term["dim"],):
            raise RuntimeError(
                f"bloque '{term['name']}': se esperaban {term['dim']} dims, hay {v.shape[0]}"
            )
        parts.append(v)

    obs = np.concatenate(parts).astype(np.float32)
    if obs.shape[0] != obs_cfg["total_dim"]:
        raise RuntimeError(f"obs tiene {obs.shape[0]} dims, el contrato dice {obs_cfg['total_dim']}")
    if obs_cfg.get("clip"):
        obs = np.clip(obs, -obs_cfg["clip"], obs_cfg["clip"])
    return obs[None, :]


def hip_spread(ll: LowLevel) -> float:
    """Apertura media de las caderas. Sirve para detectar el spagat."""
    return float(np.mean(np.abs(ll.joint_q()[[0, 3, 6, 9]])))


def ramp(ll: LowLevel, q_to: np.ndarray, kp: np.ndarray, kd: np.ndarray,
         seconds: float, label: str = "", diag: bool = False,
         dt: float = 0.004) -> dict:
    """Interpolacion suave (smoothstep) desde la pose ACTUAL hasta q_to.

    No comprueba inclinacion: durante una rampa el tronco puede estar
    legitimamente inclinado. Devuelve un resumen de lo ocurrido.
    """
    q_from = ll.joint_q()
    t0 = time.monotonic()
    next_diag = t0 + 1.0
    while True:
        now = time.monotonic()
        a = min((now - t0) / seconds, 1.0)
        a = a * a * (3.0 - 2.0 * a)
        ll.set_command((1 - a) * q_from + a * q_to, kp, kd)
        ll.check_safety(check_tilt=False, transient=True)
        if diag and now >= next_diag:
            print(f"  [diag {label} t={now - t0:.1f}s altura~{ll.height_proxy():.3f}m "
                  f"caderas~{hip_spread(ll):.3f}rad]")
            print(ll.tau_table())
            next_diag = now + 1.0
        if a >= 1.0:
            break
        time.sleep(dt)

    # Dejar asentar antes de medir: la rampa termina, la fisica no.
    time.sleep(0.3)
    res = {
        "altura": ll.height_proxy(),
        "caderas": hip_spread(ll),
        "inclinacion_deg": float(np.degrees(ll.tilt_rad())),
        "tau_pico": float(ll.tau_peak.max()),
        "q_err_max": float(np.abs(q_to - ll.joint_q()).max()),
    }
    print(f"  {label}: altura ~{res['altura']:.3f} m | caderas ~{res['caderas']:.3f} rad | "
          f"inclinacion {res['inclinacion_deg']:.0f} deg | error max {res['q_err_max']:.3f} rad")
    return res


def command_at(t: float, args, c: dict) -> np.ndarray:
    """Comando de velocidad (vx, vy, wz), recortado a los rangos del contrato."""
    if args.auto:
        if t < 5.0:
            v = (0.0, 0.0, 0.0)
        elif t < 25.0:
            v = (0.3, 0.0, 0.0)
        elif t < 35.0:
            v = (0.0, 0.0, 0.5)
        elif t < 55.0:
            v = (0.5, 0.0, 0.0)
        else:
            v = (0.0, 0.0, 0.0)
    else:
        v = (args.vx, args.vy, args.wz)

    lo = [c["commands"]["vx_range"][0], c["commands"]["vy_range"][0], c["commands"]["wz_range"][0]]
    hi = [c["commands"]["vx_range"][1], c["commands"]["vy_range"][1], c["commands"]["wz_range"][1]]
    return np.clip(np.asarray(v, dtype=np.float32), lo, hi).astype(np.float32)


def stand_verdict(res: dict, min_height: float, max_spread: float) -> tuple[bool, str]:
    """Decide si el robot esta realmente de pie y explica por que no, si no."""
    if res["altura"] < min_height:
        return False, (f"altura {res['altura']:.3f} m < {min_height} m: no se ha levantado")
    if res["caderas"] > max_spread:
        return False, (f"caderas abiertas {res['caderas']:.3f} rad > {max_spread}: "
                       "spagat. Prueba una rampa mas corta (--ramp-s 0.8)")
    if res["inclinacion_deg"] > 25:
        return False, f"inclinacion {res['inclinacion_deg']:.0f} deg: tronco mal orientado"
    return True, "de pie y estable"


# ---------------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=["sim", "real"], default="sim")
    p.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    p.add_argument("--iface", default=None)
    p.add_argument("--domain", type=int, default=None)
    p.add_argument("--policy", default=None)
    p.add_argument("--duration", type=float, default=60.0)
    p.add_argument("--vx", type=float, default=0.0)
    p.add_argument("--vy", type=float, default=0.0)
    p.add_argument("--wz", type=float, default=0.0)
    p.add_argument("--auto", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--stand-only", action="store_true",
                   help="ejecuta solo el levantarse. No carga la politica.")
    p.add_argument("--stand-mode", choices=["fsm", "direct", "none"], default="direct",
                   help="fsm: crouch y stand. direct: rampa al offset de la politica. "
                        "none: no hacer nada (el robot ya esta de pie).")
    p.add_argument("--ramp-s", type=float, default=None,
                   help="segundos por tramo de rampa. Anula stand_ramp_s del contrato.")
    p.add_argument("--kp-scale", type=float, default=1.0,
                   help="multiplica las ganancias de FIXSTAND")
    p.add_argument("--min-height", type=float, default=0.24,
                   help="altura minima para dar por bueno el levantarse")
    p.add_argument("--max-spread", type=float, default=0.25,
                   help="apertura maxima de cadera admisible (rad)")
    p.add_argument("--force", action="store_true",
                   help="continuar a la politica aunque el levantarse no sea valido")
    p.add_argument("--no-torque-trip", action="store_true",
                   help="no abortar por saturacion de par. SOLO en simulacion.")
    p.add_argument("--diag", action="store_true")
    p.add_argument("--log", default=None)
    args = p.parse_args()

    if args.no_torque_trip and args.mode == "real":
        print("--no-torque-trip no esta permitido con el robot fisico.")
        return 1

    c = ct.load_contract(args.contract)
    print(ct.describe(c))

    sess = in_name = out_name = None
    if not args.stand_only:
        import onnxruntime as ort
        policy_path = Path(args.policy) if args.policy else REPO_ROOT / c["policy"]["path"]
        if not policy_path.exists():
            print(f"\nNo existe la politica: {policy_path}\nSi viene de DVC:  dvc pull")
            return 2
        sess = ort.InferenceSession(str(policy_path), providers=["CPUExecutionProvider"])
        in_name = sess.get_inputs()[0].name
        out_name = sess.get_outputs()[0].name
        in_shape = sess.get_inputs()[0].shape
        if int(in_shape[-1]) != c["obs"]["total_dim"]:
            print(f"\nEl ONNX espera {in_shape[-1]} dims y el contrato declara "
                  f"{c['obs']['total_dim']}. No se continua.")
            return 2
        print(f"\nONNX OK: {in_name}{in_shape} -> {out_name}")

    if args.mode == "real":
        print("\n  ROBOT FISICO. Confirma antes de continuar:")
        print("   - docs/SAFETY.md leido")
        print("   - sport_mode liberado (MotionSwitcher.ReleaseMode)")
        print("   - mando en la mano, radio de 2 m libre, bateria > 50%")
        if input("\n  Escribe 'si' para continuar: ").strip().lower() != "si":
            return 1

    ll = LowLevel(c, mode=args.mode, iface=args.iface, domain=args.domain)
    if args.no_torque_trip:
        ll.torque_trip = False
        print("\n  AVISO: disparo por par DESACTIVADO. Solo para depurar en simulacion.")

    stop = {"flag": False}
    signal.signal(signal.SIGINT, lambda *_: stop.__setitem__("flag", True))

    # --- dry run ---------------------------------------------------------
    if args.dry_run:
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
        from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_
        ChannelFactoryInitialize(ll.domain, ll.iface)
        box = {}
        ChannelSubscriber("rt/lowstate", LowState_).Init(lambda m: box.__setitem__("m", m), 10)
        t0 = time.monotonic()
        while "m" not in box and time.monotonic() - t0 < 5:
            time.sleep(0.02)
        if "m" not in box:
            print(f"\nNo llega rt/lowstate en domain {ll.domain} por '{ll.iface}'.")
            return 2
        ll._state, ll._state_t = box["m"], time.monotonic()

        cmd = command_at(10.0, args, c)
        obs = build_obs(ll, c, cmd, 0.25, np.zeros(12, dtype=np.float32))
        act = sess.run([out_name], {in_name: obs})[0].reshape(-1)[:12]
        scale = np.asarray(c["policy"]["action"]["scale"], dtype=np.float32)
        offset = np.asarray(c["policy"]["action"]["offset"], dtype=np.float32)
        target_motor = ct.policy_to_motor(act * scale + offset, c)

        print("\n--- DRY RUN: nada publicado ---")
        for name, a, b in ct.obs_layout(c):
            print(f"  {name:<18} [{a:2d}:{b:2d}] {np.round(obs[0, a:b], 3).tolist()}")
        print(f"\n  accion cruda      : {np.round(act, 3).tolist()}")
        print(f"  objetivo (motor)  : {np.round(target_motor, 3).tolist()}")
        print(f"  q actual (motor)  : {np.round(ll.joint_q(), 3).tolist()}")
        print(f"  altura aprox      : {ll.height_proxy():.3f} m")
        print(f"  caderas           : {hip_spread(ll):.3f} rad")
        print(f"  inclinacion       : {np.degrees(ll.tilt_rad()):.1f} deg")
        return 0

    # --- ejecucion -------------------------------------------------------
    writer = fh = None
    if args.log:
        fh = open(args.log, "w", newline="")
        writer = csv.writer(fh)
        writer.writerow(["t", "state", "vx_cmd", "vy_cmd", "wz_cmd",
                         "tilt_rad", "height", "hip_spread", "tau_max", "q_err_max"])

    exit_code = 0
    try:
        ll.start()
        print(f"\n{ll.summary()}")

        ts = c["fsm"]["stand_ramp_s"]
        seg = args.ramp_s if args.ramp_s is not None else max(ts[1] - ts[0], 0.5)
        kp_fs, kd_fs = ct.fsm_gains(c, "fix_stand")
        kp_fs = kp_fs * args.kp_scale
        kp_pol, kd_pol = ct.policy_gains_motor(c)
        offset_motor = ct.policy_defaults_motor(c)

        print(f"levantarse: modo={args.stand_mode} rampa={seg:.2f}s/tramo "
              f"kp_scale={args.kp_scale}\n")

        res = None
        if args.stand_mode == "fsm":
            print("[FIXSTAND] crouch...")
            ramp(ll, ct.fsm_pose(c, "crouch"), kp_fs, kd_fs, seg, "crouch", args.diag)
            print("[FIXSTAND] stand...")
            res = ramp(ll, ct.fsm_pose(c, "stand"), kp_fs, kd_fs, seg, "stand", args.diag)
        elif args.stand_mode == "direct":
            print("[DIRECT] rampa al offset de la politica con ganancias de politica...")
            res = ramp(ll, offset_motor, kp_pol, kd_pol, seg, "offset", args.diag)

        if res is not None:
            ok, why = stand_verdict(res, args.min_height, args.max_spread)
            print(f"\n[VEREDICTO] {'OK' if ok else 'FALLO'}: {why}")
            if not ok and not args.force and not args.stand_only:
                print("[VEREDICTO] no se entrega el control a la politica desde una pose")
                print("            invalida: la observacion quedaria fuera de distribucion")
                print("            y el resultado no informaria de nada.")
                print("            Usa --force si quieres continuar igualmente.")
                return 4

        if args.stand_only:
            print("\n[HOLD] manteniendo la pose. Ctrl-C para amortiguar y salir.")
            nxt = time.monotonic() + 1.0
            while not stop["flag"]:
                ll.check_safety(check_tilt=False, transient=True)
                if time.monotonic() >= nxt:
                    print(f"  altura ~{ll.height_proxy():.3f} m | "
                          f"caderas ~{hip_spread(ll):.3f} rad | "
                          f"inclinacion {np.degrees(ll.tilt_rad()):.0f} deg")
                    if args.diag:
                        print(ll.tau_table())
                    nxt = time.monotonic() + 1.0
                time.sleep(0.05)
            return 0

        if args.stand_mode == "fsm":
            print(f"\n[VELOCITY] rampa al offset de la politica...")
            ramp(ll, offset_motor, kp_fs, kd_fs,
                 float(c["safety"]["ramp_in_s"]), "offset", args.diag)

        # ---- bucle de politica ----
        scale = np.asarray(c["policy"]["action"]["scale"], dtype=np.float32)
        offset_p = np.asarray(c["policy"]["action"]["offset"], dtype=np.float32)
        step_dt = float(c["policy"]["step_dt"])
        period = float(c["obs"]["gait_phase"]["period_s"])

        last_action = np.zeros(12, dtype=np.float32)
        phase = 0.0
        t_start = time.monotonic()
        next_tick = t_start
        tick = 0
        print(f"[VELOCITY] politica a {c['policy']['ctrl_hz']} Hz. Ctrl-C para parar.\n")

        while not stop["flag"] and (time.monotonic() - t_start) < args.duration:
            t = time.monotonic() - t_start
            ll.check_safety()

            cmd = command_at(t, args, c)
            phase = (phase + step_dt / period) % 1.0
            obs = build_obs(ll, c, cmd, phase, last_action)
            act = sess.run([out_name], {in_name: obs})[0].reshape(-1)[:12]
            last_action = act.astype(np.float32)

            target_motor = ct.policy_to_motor(act * scale + offset_p, c)
            applied = ll.set_command_clamped(target_motor, kp_pol, kd_pol, offset_motor)

            if writer is not None:
                writer.writerow([f"{t:.3f}", "velocity", *[f"{v:.3f}" for v in cmd],
                                 f"{ll.tilt_rad():.4f}", f"{ll.height_proxy():.4f}",
                                 f"{hip_spread(ll):.4f}",
                                 f"{np.abs(ll.joint_tau()).max():.2f}",
                                 f"{np.abs(applied - ll.joint_q()).max():.4f}"])
            if tick % c["policy"]["ctrl_hz"] == 0:
                print(f"  t={t:5.1f}s cmd={np.round(cmd, 2).tolist()} "
                      f"tilt={np.degrees(ll.tilt_rad()):4.0f}deg "
                      f"h~{ll.height_proxy():.3f}m "
                      f"tau={np.abs(ll.joint_tau()).max():5.1f}Nm")
                if args.diag:
                    print(ll.tau_table())

            tick += 1
            next_tick += step_dt
            time.sleep(max(0.0, next_tick - time.monotonic()))

        print(f"\n[FIN] {'interrumpido' if stop['flag'] else 'duracion completada'} "
              f"tras {time.monotonic() - t_start:.1f} s")

    except SafetyTrip as e:
        print(f"\n[SEGURIDAD] {e}")
        print("\n--- estado en el momento del disparo ---")
        try:
            print(ll.tau_table())
        except Exception:
            pass
        exit_code = 3
    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        exit_code = 1
    finally:
        print("[PASSIVE] amortiguando...")
        ll.stop()
        if fh is not None:
            fh.close()
            print(f"[LOG] metricas en {args.log}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
