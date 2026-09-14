#!/usr/bin/env python3
"""Despliegue de la politica de locomocion Go2 (ONNX) sobre DDS.

Cadena completa:

    tools/teleop.py  --rt/wirelesscontroller-->  run_policy.py
                                                       |
                                                ONNX + seguridad
                                                       |
                                                 rt/lowcmd
                                                       |
                                     unitree_mujoco  o  Go2 fisico

El mismo codigo sirve para simulacion y para el robot. Lo unico que cambia es
--mode, que selecciona domain id e interfaz desde el contrato.

RENDIMIENTO EN TIEMPO REAL
--------------------------
El bucle de politica debe cumplir su plazo (20 ms a 50 Hz). Tres cosas compiten
por la CPU en este portatil:

  1. El hilo publicador de LowCmd. El CRC de unitree_sdk2py esta en Python puro
     y recorre el mensaje byte a byte, asi que 500 Hz cuesta una fraccion
     grande de un nucleo. En simulacion 200 Hz sobran: usa --publish-hz 200.
     Para el robot real, dejar 500.
  2. onnxruntime abre un hilo por nucleo por defecto. Para una MLP de 47
     entradas eso es contraproducente: sincronizar los hilos cuesta mas que el
     calculo. Aqui se fuerza a 1 hilo.
  3. El visor de MuJoCo redibuja en el mismo proceso que la fisica. Subir
     VIEWER_DT en simulate_python/config.py libera CPU.

Al terminar se informa del porcentaje de pasos fuera de plazo y de la
frecuencia real de publicacion, para saber cual de los tres es el cuello.

MODOS DE LEVANTARSE (--stand-mode)
----------------------------------
    direct  (defecto) rampa a default_joint_pos con ganancias de politica.
            Es lo que hacia python_onnx_ctrl.py en WSL2 y es lo que funciona.
    fsm     crouch y stand con las ganancias rigidas del deploy C++. En
            simulacion produce temblor: con kd=5, 4.7 rad/s ya saturan el
            actuador. En el robot real el PD va dentro del motor y no ocurre.
    none    el robot ya esta de pie.

Uso tipico:
    # Terminal A: simulador
    cd ~/opt/unitree_mujoco/simulate_python && python3 unitree_mujoco.py
    # Terminal B: politica
    python3 .../run_policy.py --mode sim --teleop --publish-hz 200 --duration 300
    # Terminal C: teclado
    python3 tools/teleop.py --mode sim
"""

from __future__ import annotations

import os

# Debe ir ANTES de importar numpy y onnxruntime: si no, ya han creado sus pools.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import argparse       # noqa: E402
import csv            # noqa: E402
import math           # noqa: E402
import signal         # noqa: E402
import sys            # noqa: E402
import threading      # noqa: E402
import time           # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np    # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from go2core.control import contract as ct          # noqa: E402
from go2core.control.lowlevel import LowLevel, SafetyTrip  # noqa: E402

DEFAULT_CONTRACT = REPO_ROOT / "usecases/uc01_locomotion/configs/robot_go2.yaml"


# ---------------------------------------------------------------------------
class TeleopSource:
    """Comando de velocidad leido de rt/wirelesscontroller.

    Mapeo identico al de tools/teleop.py, go2_controller.py y el mando:
        ly -> vx    lx -> vy    rx -> wz
    """

    def __init__(self) -> None:
        self._cmd = np.zeros(3, dtype=np.float32)
        self._lock = threading.Lock()
        self.msgs = 0
        self.last_t = 0.0

    def start(self) -> None:
        from unitree_sdk2py.core.channel import ChannelSubscriber
        from unitree_sdk2py.idl.unitree_go.msg.dds_ import WirelessController_
        # ChannelFactoryInitialize ya lo hizo LowLevel: se comparte participante,
        # asi que este suscriptor usa el MISMO domain id. Si el publicador usa
        # otro dominio, los mensajes no llegan nunca (fallo silencioso).
        ChannelSubscriber("rt/wirelesscontroller", WirelessController_).Init(self._on, 10)

    def _on(self, m) -> None:
        with self._lock:
            self._cmd = np.asarray([m.ly, m.lx, m.rx], dtype=np.float32)
            self.msgs += 1
            self.last_t = time.monotonic()

    def get(self) -> np.ndarray:
        with self._lock:
            return self._cmd.copy()

    def age_s(self) -> float:
        with self._lock:
            return float("inf") if self.msgs == 0 else time.monotonic() - self.last_t


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
    return float(np.mean(np.abs(ll.joint_q()[[0, 3, 6, 9]])))


def ramp(ll: LowLevel, q_to: np.ndarray, kp: np.ndarray, kd: np.ndarray,
         seconds: float, label: str = "", diag: bool = False,
         dt: float = 0.004) -> dict:
    """Interpolacion smoothstep desde la pose ACTUAL hasta q_to (orden MOTOR)."""
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
            print(f"  [diag {label} t={now - t0:.1f}s h~{ll.height_proxy():.3f}m]")
            print(ll.tau_table())
            next_diag = now + 1.0
        if a >= 1.0:
            break
        time.sleep(dt)

    time.sleep(0.3)   # la rampa termina, la fisica no
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


def clamp_cmd(v, c: dict) -> np.ndarray:
    lo = [c["commands"]["vx_range"][0], c["commands"]["vy_range"][0], c["commands"]["wz_range"][0]]
    hi = [c["commands"]["vx_range"][1], c["commands"]["vy_range"][1], c["commands"]["wz_range"][1]]
    return np.clip(np.asarray(v, dtype=np.float32), lo, hi).astype(np.float32)


def command_at(t: float, args, c: dict, teleop: TeleopSource | None) -> np.ndarray:
    if teleop is not None:
        return clamp_cmd(teleop.get(), c)
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
    return clamp_cmd(v, c)


def stand_verdict(res: dict, min_height: float, max_spread: float) -> tuple[bool, str]:
    if res["altura"] < min_height:
        return False, f"altura {res['altura']:.3f} m < {min_height} m: no se ha levantado"
    if res["caderas"] > max_spread:
        return False, (f"caderas abiertas {res['caderas']:.3f} rad > {max_spread}: spagat. "
                       "Por encima de 0.395 rad la cadera ya no puede cerrarse con kp=60.")
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
    p.add_argument("--teleop", action="store_true",
                   help="comando desde rt/wirelesscontroller (tools/teleop.py o mando)")
    p.add_argument("--vx", type=float, default=0.0)
    p.add_argument("--vy", type=float, default=0.0)
    p.add_argument("--wz", type=float, default=0.0)
    p.add_argument("--auto", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--stand-only", action="store_true")
    p.add_argument("--stand-mode", choices=["direct", "fsm", "none"], default="direct")
    p.add_argument("--ramp-s", type=float, default=1.5)
    p.add_argument("--kp-scale", type=float, default=1.0)
    p.add_argument("--min-height", type=float, default=0.20)
    p.add_argument("--max-spread", type=float, default=0.25)
    p.add_argument("--force", action="store_true")
    p.add_argument("--publish-hz", type=float, default=None,
                   help="frecuencia del hilo de LowCmd. 200 en sim, 500 en robot real.")
    p.add_argument("--onnx-threads", type=int, default=1,
                   help="hilos de onnxruntime. 1 es lo optimo para una MLP pequena.")
    p.add_argument("--no-torque-trip", action="store_true")
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
        so = ort.SessionOptions()
        so.intra_op_num_threads = args.onnx_threads
        so.inter_op_num_threads = 1
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        sess = ort.InferenceSession(str(policy_path), sess_options=so,
                                    providers=["CPUExecutionProvider"])
        in_name = sess.get_inputs()[0].name
        out_name = sess.get_outputs()[0].name
        in_shape = sess.get_inputs()[0].shape
        if int(in_shape[-1]) != c["obs"]["total_dim"]:
            print(f"\nEl ONNX espera {in_shape[-1]} dims y el contrato declara "
                  f"{c['obs']['total_dim']}. No se continua.")
            return 2
        print(f"\nONNX OK: {in_name}{in_shape} -> {out_name} "
              f"({args.onnx_threads} hilo/s)")

        # Medida del coste de inferencia, para saber si es el cuello de botella.
        dummy = np.zeros((1, c["obs"]["total_dim"]), dtype=np.float32)
        for _ in range(20):
            sess.run([out_name], {in_name: dummy})
        t0 = time.perf_counter()
        for _ in range(200):
            sess.run([out_name], {in_name: dummy})
        infer_ms = (time.perf_counter() - t0) / 200 * 1e3
        budget_ms = float(c["policy"]["step_dt"]) * 1e3
        print(f"inferencia: {infer_ms:.2f} ms por paso "
              f"({100 * infer_ms / budget_ms:.1f} % del plazo de {budget_ms:.0f} ms)")

    if args.mode == "real":
        print("\n  ROBOT FISICO. Confirma antes de continuar:")
        print("   - docs/SAFETY.md leido")
        print("   - sport_mode liberado (MotionSwitcher.ReleaseMode)")
        print("   - mando en la mano, radio de 2 m libre, bateria > 50%")
        if input("\n  Escribe 'si' para continuar: ").strip().lower() != "si":
            return 1

    ll = LowLevel(c, mode=args.mode, iface=args.iface, domain=args.domain)
    if args.publish_hz:
        ll.publish_dt = 1.0 / float(args.publish_hz)
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

        cmd = command_at(10.0, args, c, None)
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
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["t", "vx_cmd", "vy_cmd", "wz_cmd", "tilt_rad",
                         "height", "hip_spread", "tau_max", "q_err_max"])

    exit_code = 0
    teleop = None
    try:
        ll.start()
        print(f"\n{ll.summary()}")
        print(f"publicacion de LowCmd a {1.0 / ll.publish_dt:.0f} Hz objetivo")

        if args.teleop:
            teleop = TeleopSource()
            teleop.start()
            print(f"teleop: escuchando rt/wirelesscontroller en domain {ll.domain}.")
            print("        Si el publicador usa otro dominio, no llegara nada.")

        kp_fs, kd_fs = ct.fsm_gains(c, "fix_stand")
        kp_fs = kp_fs * args.kp_scale
        kp_pol, kd_pol = ct.policy_gains_motor(c)
        offset_motor = ct.policy_defaults_motor(c)

        print(f"levantarse: modo={args.stand_mode} rampa={args.ramp_s:.2f}s\n")

        res = None
        if args.stand_mode == "direct":
            print("[DIRECT] rampa al offset de la politica...")
            res = ramp(ll, offset_motor, kp_pol, kd_pol, args.ramp_s, "offset", args.diag)
        elif args.stand_mode == "fsm":
            print("[FIXSTAND] crouch...")
            ramp(ll, ct.fsm_pose(c, "crouch"), kp_fs, kd_fs, args.ramp_s, "crouch", args.diag)
            print("[FIXSTAND] stand...")
            res = ramp(ll, ct.fsm_pose(c, "stand"), kp_fs, kd_fs, args.ramp_s, "stand", args.diag)

        if res is not None:
            ok, why = stand_verdict(res, args.min_height, args.max_spread)
            print(f"\n[VEREDICTO] {'OK' if ok else 'FALLO'}: {why}")
            if not ok and not args.force and not args.stand_only:
                print("[VEREDICTO] no se entrega el control a la politica desde una pose")
                print("            invalida. Usa --force para continuar igualmente.")
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
                    nxt = time.monotonic() + 1.0
                time.sleep(0.05)
            return 0

        if args.stand_mode == "fsm":
            print("\n[VELOCITY] rampa al offset de la politica...")
            ramp(ll, offset_motor, kp_fs, kd_fs, float(c["safety"]["ramp_in_s"]), "offset")

        # ---- bucle de politica ----
        scale = np.asarray(c["policy"]["action"]["scale"], dtype=np.float32)
        offset_p = np.asarray(c["policy"]["action"]["offset"], dtype=np.float32)
        step_dt = float(c["policy"]["step_dt"])
        period = float(c["obs"]["gait_phase"]["period_s"])

        last_action = np.zeros(12, dtype=np.float32)
        last_cmd = np.zeros(3, dtype=np.float32)
        phase = 0.0
        t_start = time.monotonic()
        next_tick = t_start
        pub0 = ll.published
        tick = late = 0
        work_s = 0.0
        print(f"[VELOCITY] politica a {c['policy']['ctrl_hz']} Hz. Ctrl-C para parar.\n")

        while not stop["flag"] and (time.monotonic() - t_start) < args.duration:
            w0 = time.perf_counter()
            t = time.monotonic() - t_start
            ll.check_safety()

            cmd = command_at(t, args, c, teleop)
            if teleop is not None and not np.allclose(cmd, last_cmd, atol=1e-3):
                print(f"  [teleop] cmd={np.round(cmd, 2).tolist()}")
                last_cmd = cmd

            phase = (phase + step_dt / period) % 1.0
            obs = build_obs(ll, c, cmd, phase, last_action)
            act = sess.run([out_name], {in_name: obs})[0].reshape(-1)[:12]
            last_action = act.astype(np.float32)

            target_motor = ct.policy_to_motor(act * scale + offset_p, c)
            applied = ll.set_command_clamped(target_motor, kp_pol, kd_pol, offset_motor)

            if writer is not None:
                writer.writerow([f"{t:.3f}", *[f"{v:.3f}" for v in cmd],
                                 f"{ll.tilt_rad():.4f}", f"{ll.height_proxy():.4f}",
                                 f"{hip_spread(ll):.4f}",
                                 f"{np.abs(ll.joint_tau()).max():.2f}",
                                 f"{np.abs(applied - ll.joint_q()).max():.4f}"])
            if tick % (c["policy"]["ctrl_hz"] * 2) == 0:
                extra = ""
                if teleop is not None:
                    extra = f" teleop={teleop.msgs}msg"
                print(f"  t={t:5.1f}s cmd={np.round(cmd, 2).tolist()} "
                      f"tilt={np.degrees(ll.tilt_rad()):4.0f}deg "
                      f"h~{ll.height_proxy():.3f}m "
                      f"tau={np.abs(ll.joint_tau()).max():5.1f}Nm{extra}")
                if args.diag:
                    print(ll.tau_table())

            work_s += time.perf_counter() - w0
            tick += 1
            next_tick += step_dt
            sleep_s = next_tick - time.monotonic()
            if sleep_s < 0:
                late += 1
                next_tick = time.monotonic()
            time.sleep(max(0.0, sleep_s))

        dur = time.monotonic() - t_start
        pub_hz = (ll.published - pub0) / max(dur, 1e-6)
        print(f"\n[FIN] {'interrumpido' if stop['flag'] else 'duracion completada'} tras {dur:.1f} s")
        print(f"      pasos            : {tick} | fuera de plazo {late} "
              f"({100.0 * late / max(tick, 1):.1f} %)")
        print(f"      trabajo por paso : {work_s / max(tick, 1) * 1e3:.2f} ms "
              f"de {step_dt * 1e3:.0f} ms disponibles")
        print(f"      LowCmd real      : {pub_hz:.0f} Hz "
              f"(objetivo {1.0 / ll.publish_dt:.0f})")
        if teleop is not None:
            print(f"      teleop recibidos : {teleop.msgs} mensajes")
            if teleop.msgs == 0:
                print("      NINGUN mensaje de teleop. Casi siempre es un dominio DDS")
                print("      distinto entre publicador y suscriptor. Comprueba que el")
                print("      teleop usa el mismo --mode que este proceso.")
        if late > 0.1 * tick:
            print("\n      Cuello de botella: si 'trabajo por paso' es pequeno pero hay")
            print("      muchos fuera de plazo, la CPU se la lleva otro proceso (visor")
            print("      de MuJoCo o el hilo de LowCmd). Baja --publish-hz o sube")
            print("      VIEWER_DT en simulate_python/config.py.")

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
