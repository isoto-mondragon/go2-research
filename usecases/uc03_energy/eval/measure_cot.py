#!/usr/bin/env python3
"""usecases/uc03_energy/eval/measure_cot.py

uc03 — Coste de transporte del Unitree Go2.

PREGUNTA DE INVESTIGACION
-------------------------
Cuanta energia gasta el robot por metro recorrido, y como depende de la
velocidad. El coste de transporte, CoT = P / (m g v), es adimensional y por
tanto comparable entre robots y entre especies animales.

Para cuadrupedos comerciales hay muy pocos datos empiricos publicados: casi
todo lo que existe es simulacion o plataformas de laboratorio a medida. Un
barrido medido sobre un Go2 de serie, con protocolo reproducible, es un dato
citable por si mismo.

DOS MOTORES DE LOCOMOCION
-------------------------
    --locomotion policy   politica RL propia por LowCmd (unica opcion en
                          simulacion: unitree_mujoco no emula Sport Mode)
    --locomotion sport    Sport Mode del fabricante (recomendado en el robot
                          real: es robusto y no hay que entrenar nada)

IMPORTANTE con Sport Mode: NUNCA se publica LowCmd. Los dos niveles de control
son excluyentes y hacerlo a la vez provoca que dos controladores peleen por los
mismos motores. Por eso este script usa un suscriptor de solo lectura en ese
modo, en lugar de la capa LowLevel.

DOS MEDIDAS DE POTENCIA
-----------------------
    mecanica    suma de |tau * dq| sobre las 12 articulaciones. Disponible
                siempre, tambien en simulacion.
    electrica   corriente x voltaje de la bateria (bms_state). SOLO en el
                robot real: en simulacion sale cero.

Comparar ambas da el rendimiento de la cadena de transmision, que es un
resultado en si mismo.

USO
    # Simulacion, con el simulador ya arrancado
    python3 usecases/uc03_energy/eval/measure_cot.py --mode sim

    # Robot real con Sport Mode
    python3 usecases/uc03_energy/eval/measure_cot.py \\
        --mode real --iface enp3s0 --locomotion sport
"""

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse          # noqa: E402
import csv               # noqa: E402
import json              # noqa: E402
import math              # noqa: E402
import statistics as st  # noqa: E402
import subprocess        # noqa: E402
import sys               # noqa: E402
import threading         # noqa: E402
import time              # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path       # noqa: E402

import numpy as np       # noqa: E402

# Asi es como un caso de uso encuentra la libreria compartida. `paths` deduce
# la raiz del repositorio desde su propia ubicacion, de modo que esto funciona
# igual en /workspace dentro del contenedor y en ~/go2-research fuera.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from go2core import paths                                  # noqa: E402
from go2core.control import contract as ct                 # noqa: E402
from go2core.control.lowlevel import LowLevel, SafetyTrip  # noqa: E402

UC = Path(__file__).resolve().parents[1]
CONFIG = UC / "configs" / "experiment.yaml"


# ===========================================================================
# Telemetria de solo lectura
# ===========================================================================
class Telemetria:
    """Suscriptor de rt/lowstate que NO publica nada.

    Con Sport Mode activo no se puede usar LowLevel: su hilo publicador
    emitiria LowCmd y entraria en conflicto con el controlador del fabricante.
    """

    def __init__(self) -> None:
        self.msg = None
        self.t = 0.0
        self.n = 0
        self._lock = threading.Lock()

    def start(self, domain: int, iface: str) -> None:
        from unitree_sdk2py.core.channel import (ChannelFactoryInitialize,
                                                 ChannelSubscriber)
        from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_
        ChannelFactoryInitialize(domain, iface)
        ChannelSubscriber("rt/lowstate", LowState_).Init(self._on, 10)

    def _on(self, m) -> None:
        with self._lock:
            self.msg, self.t, self.n = m, time.monotonic(), self.n + 1

    def esperar(self, s: float = 5.0) -> bool:
        t0 = time.monotonic()
        while self.msg is None and time.monotonic() - t0 < s:
            time.sleep(0.02)
        return self.msg is not None

    # -- lecturas --
    def tau(self) -> np.ndarray:
        return np.asarray([getattr(self.msg.motor_state[i], "tau_est", 0.0)
                           for i in range(12)], dtype=np.float32)

    def dq(self) -> np.ndarray:
        return np.asarray([self.msg.motor_state[i].dq for i in range(12)],
                          dtype=np.float32)

    def temperaturas(self) -> np.ndarray:
        return np.asarray([getattr(self.msg.motor_state[i], "temperature", 0)
                           for i in range(12)], dtype=np.float32)

    def bateria(self) -> tuple[float, float, float]:
        """(voltaje V, corriente A, carga %). En simulacion sale (0, 0, 0)."""
        bms = getattr(self.msg, "bms_state", None)
        v = float(getattr(self.msg, "power_v", 0.0) or 0.0)
        a = float(getattr(self.msg, "power_a", 0.0) or 0.0)
        soc = float(getattr(bms, "soc", 0) or 0) if bms else 0.0
        if a == 0.0 and bms is not None:
            a = float(getattr(bms, "current", 0) or 0) / 1000.0
        return v, a, soc

    def quaternion(self) -> np.ndarray:
        return np.asarray(self.msg.imu_state.quaternion, dtype=np.float32)

    def inclinacion(self) -> float:
        w, x, y, z = self.quaternion()
        gz = -(1.0 - 2.0 * (x * x + y * y))
        return float(np.arccos(np.clip(-gz, -1.0, 1.0)))

    def altura(self) -> float:
        q = np.asarray([self.msg.motor_state[i].q for i in range(12)],
                       dtype=np.float32)
        muslo, rodilla = q[[1, 4, 7, 10]], q[[2, 5, 8, 11]]
        return float(np.mean(0.213 * np.cos(muslo)
                             + 0.213 * np.cos(muslo + rodilla)))


class VerdadTerreno:
    """Posicion real del tronco desde rt/sportmodestate."""

    def __init__(self) -> None:
        self.pos = np.zeros(3, dtype=np.float64)
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
            self.n += 1

    def get(self) -> np.ndarray:
        with self._lock:
            return self.pos.copy()


def yaw(q: np.ndarray) -> float:
    w, x, y, z = q
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def a_cuerpo(dp: np.ndarray, ang: float) -> np.ndarray:
    c, s = math.cos(-ang), math.sin(-ang)
    return np.asarray([c * dp[0] - s * dp[1], s * dp[0] + c * dp[1]])


# ===========================================================================
# Motores de locomocion
# ===========================================================================
class MotorPolitica:
    """Politica RL por LowCmd. Unica opcion en simulacion."""

    nombre = "politica RL (LowCmd)"

    def __init__(self, c: dict, modo: str, iface: str | None, publish_hz: float):
        import onnxruntime as ort
        ruta = paths.ROOT / c["policy"]["path"]
        if not ruta.exists():
            raise SystemExit(f"No existe la politica: {ruta}")
        so = ort.SessionOptions()
        so.intra_op_num_threads = 1
        so.inter_op_num_threads = 1
        self.sess = ort.InferenceSession(str(ruta), sess_options=so,
                                         providers=["CPUExecutionProvider"])
        self.ent = self.sess.get_inputs()[0].name
        self.sal = self.sess.get_outputs()[0].name

        self.c = c
        self.ll = LowLevel(c, mode=modo, iface=iface)
        self.ll.publish_dt = 1.0 / publish_hz
        self.escala = np.asarray(c["policy"]["action"]["scale"], dtype=np.float32)
        self.offset = np.asarray(c["policy"]["action"]["offset"], dtype=np.float32)
        self.offset_motor = ct.policy_defaults_motor(c)
        self.kp, self.kd = ct.policy_gains_motor(c)
        self.dt = float(c["policy"]["step_dt"])
        self.periodo = float(c["obs"]["gait_phase"]["period_s"])
        self.fase = 0.0
        self.ultima = np.zeros(12, dtype=np.float32)

    def start(self) -> None:
        self.ll.start()

    def preparar(self, rampa: float = 1.5) -> None:
        q0 = self.ll.joint_q()
        t0 = time.monotonic()
        while True:
            a = min((time.monotonic() - t0) / rampa, 1.0)
            a = a * a * (3.0 - 2.0 * a)
            self.ll.set_command((1 - a) * q0 + a * self.offset_motor,
                                self.kp, self.kd)
            self.ll.check_safety(check_tilt=False, transient=True)
            if a >= 1.0:
                break
            time.sleep(0.004)
        time.sleep(0.3)

    def paso(self, cmd: np.ndarray) -> None:
        c = self.c
        gait = np.asarray([math.sin(self.fase * 2 * math.pi),
                           math.cos(self.fase * 2 * math.pi)], dtype=np.float32)
        if float(np.linalg.norm(cmd)) < float(c["obs"]["gait_phase"]["zero_below_cmd_norm"]):
            gait[:] = 0.0
        self.fase = (self.fase + self.dt / self.periodo) % 1.0

        por_defecto = np.asarray(c["policy"]["default_joint_pos"], dtype=np.float32)
        bloques = {
            "base_ang_vel": self.ll.gyro(),
            "projected_gravity": self.ll.projected_gravity(),
            "velocity_commands": cmd,
            "gait_phase": gait,
            "joint_pos_rel": ct.motor_to_policy(self.ll.joint_q(), c) - por_defecto,
            "joint_vel_rel": ct.motor_to_policy(self.ll.joint_dq(), c),
            "last_action": self.ultima,
        }
        obs = np.concatenate([np.asarray(bloques[t["name"]], dtype=np.float32)
                              * float(t["scale"]) for t in c["obs"]["terms"]])
        act = self.sess.run([self.sal], {self.ent: obs[None, :]})[0].reshape(-1)[:12]
        self.ultima = act.astype(np.float32)
        objetivo = ct.policy_to_motor(act * self.escala + self.offset, c)
        self.ll.set_command_clamped(objetivo, self.kp, self.kd, self.offset_motor)

    def comprobar(self) -> None:
        self.ll.check_safety()

    def parar(self) -> None:
        self.ll.stop()


class MotorSport:
    """Sport Mode del fabricante. Solo robot real. NUNCA publica LowCmd."""

    nombre = "Sport Mode (alto nivel)"

    def __init__(self, c: dict, modo: str, iface: str | None, publish_hz: float):
        if modo != "real":
            raise SystemExit(
                "Sport Mode solo existe en el robot real: unitree_mujoco no lo "
                "emula. En simulacion usa --locomotion policy."
            )
        from go2core.control.go2_controller import Go2Controller
        self.dog = Go2Controller(mode="real", network=iface)
        self.dt = 0.02

    def start(self) -> None:
        pass

    def preparar(self, rampa: float = 1.5) -> None:
        self.dog.stand_up()
        time.sleep(3.0)

    def paso(self, cmd: np.ndarray) -> None:
        self.dog.set_velocity(float(cmd[0]), float(cmd[1]), float(cmd[2]))

    def comprobar(self) -> None:
        pass

    def parar(self) -> None:
        try:
            self.dog.stop()
        except Exception:
            pass


# ===========================================================================
def medir_velocidad(motor, tel: Telemetria, gt: VerdadTerreno | None,
                    v: float, secs: float, settle: float, masa: float,
                    filas: list, caida_rad: float) -> dict:
    """Mantiene una velocidad y mide potencia y desplazamiento en regimen."""
    cmd = np.asarray([v, 0.0, 0.0], dtype=np.float32)
    p_mec, p_ele, alturas, inclin, temps = [], [], [], [], []
    pos0 = ang0 = t_reg = None
    cayo = False

    t0 = time.monotonic()
    siguiente = t0
    while time.monotonic() - t0 < secs:
        try:
            motor.comprobar()
        except SafetyTrip as e:
            print(f"    disparo de seguridad: {e}")
            cayo = True
            break

        motor.paso(cmd)

        incl = tel.inclinacion()
        if incl > caida_rad:
            print(f"    CAIDA (inclinacion {math.degrees(incl):.0f} grados)")
            cayo = True
            break

        transcurrido = time.monotonic() - t0
        if transcurrido >= settle:
            if pos0 is None:
                pos0 = gt.get() if gt else None
                ang0 = yaw(tel.quaternion())
                t_reg = time.monotonic()
            pm = float(np.sum(np.abs(tel.tau() * tel.dq())))
            volt, amp, _ = tel.bateria()
            p_mec.append(pm)
            p_ele.append(volt * amp)
            alturas.append(tel.altura())
            inclin.append(incl)
            temps.append(float(tel.temperaturas().max()))
            filas.append([f"{v:.2f}", f"{transcurrido:.3f}", f"{pm:.2f}",
                          f"{volt * amp:.2f}", f"{volt:.2f}", f"{amp:.3f}",
                          f"{incl:.4f}", f"{alturas[-1]:.4f}"])

        siguiente += motor.dt
        time.sleep(max(0.0, siguiente - time.monotonic()))

    # --- velocidad real por desplazamiento neto en regimen ---
    v_med = None
    if gt is not None and pos0 is not None:
        dur = max(time.monotonic() - t_reg, 1e-6)
        d = a_cuerpo(gt.get() - pos0, ang0)
        v_med = float(d[0] / dur)

    pm = st.mean(p_mec) if p_mec else 0.0
    pe = st.mean(p_ele) if p_ele else 0.0
    v_ref = v_med if (v_med is not None and abs(v_med) > 0.03) else None

    cot_mec = pm / (masa * 9.81 * abs(v_ref)) if v_ref and pm > 0 else None
    cot_ele = pe / (masa * 9.81 * abs(v_ref)) if v_ref and pe > 0 else None

    return {
        "v_cmd": v,
        "v_med": round(v_med, 4) if v_med is not None else None,
        "seguimiento": round(v_med / v, 3) if (v_med and v > 0.01) else None,
        "P_mecanica_W": round(pm, 2),
        "P_electrica_W": round(pe, 2) if pe > 0 else None,
        "CoT_mecanico": round(cot_mec, 3) if cot_mec else None,
        "CoT_electrico": round(cot_ele, 3) if cot_ele else None,
        "rendimiento": round(pm / pe, 3) if (pe > 0 and pm > 0) else None,
        "h_sd": round(st.pstdev(alturas), 4) if len(alturas) > 1 else None,
        "inclinacion_max_deg": round(math.degrees(max(inclin)), 1) if inclin else None,
        "temp_max_C": round(max(temps), 1) if temps else None,
        "muestras": len(p_mec),
        "cayo": cayo,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=["sim", "real"], default="sim")
    p.add_argument("--iface", default=None)
    p.add_argument("--locomotion", choices=["policy", "sport"], default="policy")
    p.add_argument("--contract", default=None)
    # Se empieza en 0.2: con 0.1 la politica heredada solo alcanza 0.019 m/s,
    # titubea y acaba volcando. Es un dato sobre la politica, no un fallo del
    # protocolo, pero arruina el barrido entero al caerse en el primer punto.
    p.add_argument("--speeds", default="0.2,0.3,0.4,0.5,0.6,0.8",
                   help="velocidades en m/s, separadas por comas")
    p.add_argument("--secs", type=float, default=12.0, help="segundos por velocidad")
    p.add_argument("--settle", type=float, default=3.0,
                   help="segundos iniciales descartados de cada velocidad")
    p.add_argument("--mass-kg", type=float, default=None)
    p.add_argument("--publish-hz", type=float, default=200.0)
    p.add_argument("--fall-tilt-deg", type=float, default=50.0)
    p.add_argument("--tag", default="cot")
    p.add_argument("--out", default=None)
    args = p.parse_args()

    contrato = Path(args.contract) if args.contract else paths.CONTRACT
    c = ct.load_contract(contrato)
    masa = args.mass_kg or float(c.get("hardware", {}).get("mass_kg", 15.0))
    vels = [float(x) for x in args.speeds.split(",")]

    dds = c["dds"][args.mode]
    iface = args.iface or paths.iface() or dds["interface"]
    domain = paths.domain() if paths.domain() is not None else dds["domain_id"]

    print("uc03 — coste de transporte")
    print(f"  modo        : {args.mode} (domain {domain}, {iface})")
    print(f"  locomocion  : {args.locomotion}")
    print(f"  masa        : {masa} kg")
    print(f"  velocidades : {vels}")
    print(f"  por punto   : {args.secs} s, descartando {args.settle} s\n")

    if args.mode == "real":
        print("  ROBOT FISICO. Confirma:")
        print("   - docs/SAFETY.md leido")
        print("   - pista despejada de al menos 5 m")
        print("   - mando en la mano, bateria > 60 %")
        if args.locomotion == "policy":
            print("   - sport_mode LIBERADO (MotionSwitcher.ReleaseMode)")
        if input("\n  Escribe 'si' para continuar: ").strip().lower() != "si":
            return 1

    Motor = MotorPolitica if args.locomotion == "policy" else MotorSport
    motor = Motor(c, args.mode, iface, args.publish_hz)
    print(f"motor de locomocion: {motor.nombre}\n")

    tel = Telemetria()
    filas: list = []
    resultados: list = []
    codigo = 0

    try:
        motor.start()
        # LowLevel ya inicializo el ChannelFactory en modo politica; con Sport
        # Mode hay que hacerlo aqui.
        if args.locomotion == "sport":
            tel.start(domain, iface)
        else:
            from unitree_sdk2py.core.channel import ChannelSubscriber
            from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_
            ChannelSubscriber("rt/lowstate", LowState_).Init(tel._on, 10)

        if not tel.esperar():
            print("No llega rt/lowstate. ¿Esta el simulador o el robot activo?")
            return 2
        print(f"telemetria OK ({tel.n} mensajes)")

        gt = VerdadTerreno()
        tiene_gt = gt.start()
        time.sleep(0.5)
        if tiene_gt and gt.n == 0:
            tiene_gt = False
        print(f"verdad-terreno: {'si' if tiene_gt else 'NO (velocidad no medible)'}\n")
        if not tiene_gt:
            gt = None
            print("  AVISO: sin rt/sportmodestate no hay velocidad real y por")
            print("  tanto no hay CoT. En el robot real hay que medir la")
            print("  distancia de otra forma (marcas en el suelo).\n")

        print("levantando el robot...")
        motor.preparar()
        print(f"altura tras levantarse: {tel.altura():.3f} m\n")

        cab = (f"  {'v cmd':>6} {'v med':>7} {'segui':>7} {'P mec':>8} "
               f"{'P ele':>8} {'CoT mec':>8} {'CoT ele':>8} {'h sd':>7} {'T':>5}")
        print(cab)
        print("  " + "-" * (len(cab) - 2))

        for v in vels:
            r = medir_velocidad(motor, tel, gt, v, args.secs, args.settle,
                                masa, filas, math.radians(args.fall_tilt_deg))
            resultados.append(r)
            def fmt(x, n=2):
                return "-" if x is None else f"{x:.{n}f}"

            seg = "-" if r["seguimiento"] is None else f"{100 * r['seguimiento']:.0f}%"
            print(f"  {v:6.2f} {fmt(r['v_med'], 3):>7} {seg:>7} "
                  f"{fmt(r['P_mecanica_W'], 1):>8} {fmt(r['P_electrica_W'], 1):>8} "
                  f"{fmt(r['CoT_mecanico'], 3):>8} {fmt(r['CoT_electrico'], 3):>8} "
                  f"{fmt(r['h_sd'], 4):>7} {fmt(r['temp_max_C'], 0):>5}")
            if r["cayo"]:
                print("  el robot se ha caido: se interrumpe el barrido")
                break

    except KeyboardInterrupt:
        print("\ninterrumpido")
        codigo = 1
    except SafetyTrip as e:
        print(f"\n[SEGURIDAD] {e}")
        codigo = 3
    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        codigo = 1
    finally:
        print("\nparando el robot...")
        motor.parar()

    # ------------------------------------------------------------------
    validos = [r for r in resultados if r["CoT_mecanico"]]
    if validos:
        mejor = min(validos, key=lambda r: r["CoT_mecanico"])
        print(f"\nCoT mecanico minimo: {mejor['CoT_mecanico']} "
              f"a {mejor['v_med']} m/s (comando {mejor['v_cmd']})")

    if args.out or resultados:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           cwd=paths.ROOT, capture_output=True, text=True)
        sha = r.stdout.strip()
        if not sha:
            # Sin sha el experimento NO es trazable: no se sabe con que codigo
            # se genero. Avisar en alto, porque el run se crearia igual y el
            # fallo pasaria desapercibido.
            sha = "unknown"
            print("\n  AVISO: no se ha podido leer el commit de git.")
            print("  El experimento quedara SIN TRAZABILIDAD.")
            if r.stderr.strip():
                print(f"  git dice: {r.stderr.strip().splitlines()[0]}")
            print()
        if args.out:
            destino = Path(args.out)
        else:
            # Segundos en el identificador: con resolucion de minuto, dos runs
            # seguidos con el mismo sha y la misma etiqueta colisionan y el
            # segundo SOBRESCRIBE al primero, perdiendo la medida.
            base = (paths.EXPERIMENTS / "uc03_energy"
                    / f"{datetime.now():%Y-%m-%dT%H%M%S}_{sha}_{args.tag}")
            destino = base
            n = 1
            while destino.exists():
                n += 1
                destino = base.with_name(f"{base.name}_{n}")
        destino.mkdir(parents=True, exist_ok=False)

        with open(destino / "metrics.csv", "w", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["v_cmd", "t", "P_mecanica_W", "P_electrica_W",
                        "voltaje_V", "corriente_A", "inclinacion_rad", "altura_m"])
            w.writerows(filas)

        manifest = {
            "usecase": "uc03_energy",
            "fecha": datetime.now().isoformat(timespec="seconds"),
            "git_sha": sha,
            "modo": args.mode,
            "locomocion": args.locomotion,
            "masa_kg": masa,
            "velocidades": vels,
            "segundos_por_punto": args.secs,
            "settle_s": args.settle,
            "contrato": str(contrato),
            "resultados": resultados,
            "limitaciones": (
                "En simulacion no hay bms_state: la potencia electrica y el "
                "rendimiento salen vacios. La potencia mecanica es una "
                "estimacion desde tau_est, que en el robot real tampoco es un "
                "par medido con celula de carga."
            ),
        }
        (destino / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False))
        print(f"\nescrito: {destino}")
        print(f"  metrics.csv y manifest.json")
        print(f"\nGrafica:\n  python3 usecases/uc03_energy/eval/plot_cot.py {destino}")

    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
