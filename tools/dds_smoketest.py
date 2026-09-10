#!/usr/bin/env python3
"""
tools/dds_smoketest.py

Verificacion de SOLO LECTURA de la cadena DDS Unitree.
No publica nada. No mueve el robot. Es seguro ejecutarlo con el robot
encendido y en el suelo.

El mismo script sirve para:
  --mode sim   -> contra unitree_mujoco (domain 1, interfaz "lo")
  --mode real  -> contra el robot fisico (domain 0, interfaz Ethernet)

Asi la Fase A (sin robot) ensaya exactamente el mismo procedimiento que la
Fase B (con robot), y el dia del robot solo cambia un flag.

Uso:
    python3 tools/dds_smoketest.py --mode sim
    python3 tools/dds_smoketest.py --mode real --iface enp0s31f6
    python3 tools/dds_smoketest.py --mode real --iface enp0s31f6 --duration 20 --json out.json
"""

import argparse
import json
import statistics
import sys
import time

try:
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_
except ImportError:
    sys.exit("ERROR: falta unitree_sdk2_python. Activa el venv: source ~/venvs/go2/bin/activate")

GREEN, YELLOW, RED, BLUE, RESET = "\033[32m", "\033[33m", "\033[31m", "\033[34m", "\033[0m"

N_JOINTS = 12
EXPECTED_HZ = 500.0


class Collector:
    """Acumula muestras de rt/lowstate sin bloquear el hilo principal."""

    def __init__(self):
        self.stamps = []
        self.last = None
        self.count = 0

    def __call__(self, msg):
        self.stamps.append(time.perf_counter())
        self.last = msg
        self.count += 1


def check(label, passed, detail="", warn_only=False):
    if passed:
        mark, color = "ok", GREEN
    elif warn_only:
        mark, color = "??", YELLOW
    else:
        mark, color = " x", RED
    print(f"  [{color}{mark}{RESET}] {label:<34} {detail}")
    return bool(passed)


def as_list(x):
    try:
        return list(x)
    except TypeError:
        return []


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=["sim", "real"], required=True)
    p.add_argument("--iface", default=None, help="interfaz de red (obligatorio en --mode real)")
    p.add_argument("--domain", type=int, default=None, help="sobrescribe el domain id")
    p.add_argument("--duration", type=float, default=10.0, help="segundos de escucha (def. 10)")
    p.add_argument("--json", default=None, help="guardar el informe en un fichero JSON")
    args = p.parse_args()

    if args.mode == "sim":
        iface = args.iface or "lo"
        domain = args.domain if args.domain is not None else 1
    else:
        if not args.iface:
            sys.exit("ERROR: en --mode real hay que indicar --iface (usa: env/go2_net.sh detect)")
        iface = args.iface
        domain = args.domain if args.domain is not None else 0

    print(f"\n{BLUE}=== Smoke test DDS (solo lectura) ==={RESET}")
    print(f"  modo: {args.mode} | domain: {domain} | interfaz: {iface} | escucha: {args.duration}s\n")

    ChannelFactoryInitialize(domain, iface)
    collector = Collector()
    sub = ChannelSubscriber("rt/lowstate", LowState_)
    sub.Init(collector, 10)

    t0 = time.perf_counter()
    while time.perf_counter() - t0 < args.duration:
        time.sleep(0.1)
        elapsed = time.perf_counter() - t0
        print(f"\r  recibiendo... {collector.count} mensajes en {elapsed:4.1f}s", end="", flush=True)
    print("\n")

    if collector.count == 0:
        print(f"{RED}No se ha recibido ni un solo mensaje en rt/lowstate.{RESET}\n")
        print("  Comprueba, en este orden:")
        if args.mode == "sim":
            print("   1. unitree_mujoco esta corriendo (simulate_python/unitree_mujoco.py)")
            print("   2. su config.py tiene DOMAIN_ID=1 e INTERFACE='lo'")
            print("   3. has hecho: source ~/unitree_ros2/setup_sim.sh")
        else:
            print("   1. env/go2_net.sh probe pasa los 4 pasos")
            print("   2. la app movil Unitree esta CERRADA y desconectada")
            print("   3. has hecho: source ~/unitree_ros2/setup_real.sh <IFACE>")
            print("   4. el contenedor ve la interfaz del host (ip -br a dentro y fuera)")
        sys.exit(2)

    # -----------------------------------------------------------------
    # Metricas de transporte
    # -----------------------------------------------------------------
    deltas = [b - a for a, b in zip(collector.stamps, collector.stamps[1:])]
    hz = collector.count / (collector.stamps[-1] - collector.stamps[0]) if len(deltas) else 0.0
    jitter_ms = statistics.pstdev(deltas) * 1e3 if len(deltas) > 1 else 0.0
    worst_gap_ms = max(deltas) * 1e3 if deltas else 0.0

    print(f"{BLUE}--- Transporte ---{RESET}")
    results = {}
    results["hz"] = check(
        "frecuencia de rt/lowstate", hz > 0.5 * EXPECTED_HZ,
        f"{hz:7.1f} Hz (esperado ~{EXPECTED_HZ:.0f})",
        warn_only=(args.mode == "sim"),
    )
    results["jitter"] = check("jitter (desv. tipica)", jitter_ms < 2.0, f"{jitter_ms:7.2f} ms", warn_only=True)
    results["gap"] = check("peor hueco entre mensajes", worst_gap_ms < 50.0, f"{worst_gap_ms:7.2f} ms", warn_only=True)

    if args.mode == "real" and hz < 0.5 * EXPECTED_HZ:
        print(f"\n  {YELLOW}Frecuencia baja en robot real: casi siempre son los buffers del kernel.{RESET}")
        print("  Revisa en el HOST: sysctl net.core.rmem_max (debe ser 8388608)\n")

    # -----------------------------------------------------------------
    # Contenido del ultimo lowstate
    # -----------------------------------------------------------------
    m = collector.last
    print(f"\n{BLUE}--- Contenido de lowstate ---{RESET}")

    quat = as_list(getattr(m.imu_state, "quaternion", []))
    rpy = as_list(getattr(m.imu_state, "rpy", []))
    gyro = as_list(getattr(m.imu_state, "gyroscope", []))
    results["imu"] = check(
        "IMU: cuaternion normalizado",
        len(quat) == 4 and abs(sum(c * c for c in quat) - 1.0) < 0.05,
        f"q={[round(c, 3) for c in quat]}",
    )
    if rpy:
        print(f"       rpy = {[round(v, 3) for v in rpy]}   gyro = {[round(v, 3) for v in gyro]}")

    motors = as_list(m.motor_state)[:N_JOINTS]
    q = [mo.q for mo in motors]
    tau = [getattr(mo, "tau_est", 0.0) for mo in motors]
    temps = [getattr(mo, "temperature", 0) for mo in motors]

    results["joints"] = check(
        "12 posiciones articulares", len(q) == N_JOINTS and any(abs(v) > 1e-6 for v in q),
        f"q[0:3]={[round(v, 3) for v in q[:3]]}",
    )
    results["tau"] = check(
        "par estimado por motor", any(abs(v) > 1e-6 for v in tau),
        f"tau[0:3]={[round(v, 2) for v in tau[:3]]}",
    )

    # Estos tres campos SOLO tienen valores realistas en el robot fisico.
    # En el simulador salen a cero y eso es correcto, no un fallo.
    real_only = args.mode == "real"
    results["temp"] = check(
        "temperatura de motores", all(20 <= t <= 80 for t in temps) if temps else False,
        f"min={min(temps) if temps else '-'} max={max(temps) if temps else '-'} C",
        warn_only=not real_only,
    )

    foot = as_list(m.foot_force)
    results["foot"] = check(
        "sensores de fuerza en pies", len(foot) == 4 and any(f != 0 for f in foot),
        f"{list(foot)}", warn_only=not real_only,
    )

    soc = getattr(getattr(m, "bms_state", None), "soc", None)
    power_v = getattr(m, "power_v", None)
    results["battery"] = check(
        "bateria (SOC y tension)",
        soc is not None and 0 < soc <= 100 and power_v is not None and 20.0 < power_v < 34.0,
        f"soc={soc}%  V={power_v}", warn_only=not real_only,
    )

    mode_machine = getattr(m, "mode_machine", None)
    print(f"\n  mode_machine = {mode_machine}   tick = {getattr(m, 'tick', None)}   crc = {getattr(m, 'crc', None)}")
    print(f"  {YELLOW}Anota mode_machine: determina si el robot acepta control de bajo nivel.{RESET}")

    # -----------------------------------------------------------------
    # Veredicto
    # -----------------------------------------------------------------
    critical = ["hz", "imu", "joints"] if args.mode == "real" else ["imu", "joints"]
    passed = all(results[k] for k in critical)

    print(f"\n{BLUE}--- Veredicto ---{RESET}")
    if passed:
        print(f"  {GREEN}Cadena DDS de lectura VALIDADA en modo {args.mode}.{RESET}")
        if args.mode == "sim":
            print("  Siguiente: repite este mismo test con --mode real cuando llegue el robot.")
        else:
            print("  Siguiente: Fase B paso 6 (estado del servicio sport_mode).")
    else:
        fails = [k for k in critical if not results[k]]
        print(f"  {RED}FALLO en: {', '.join(fails)}. No pases a la siguiente fase.{RESET}")

    if args.json:
        report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "mode": args.mode, "domain": domain, "iface": iface,
            "messages": collector.count, "hz": round(hz, 2),
            "jitter_ms": round(jitter_ms, 3), "worst_gap_ms": round(worst_gap_ms, 3),
            "mode_machine": mode_machine, "soc": soc, "power_v": power_v,
            "checks": {k: bool(v) for k, v in results.items()},
            "passed": bool(passed),
        }
        with open(args.json, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n  informe guardado en {args.json}")

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
