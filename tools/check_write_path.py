#!/usr/bin/env python3
"""
tools/check_write_path.py

Valida el camino de ESCRITURA DDS (rt/lowcmd) de forma medible.

El problema que resuelve: cuando mandas un LowCmd y "no pasa nada", no puedes
distinguir entre (a) el comando llego pero pedia una pose casi identica a la
actual, y (b) el comando se descarto en silencio (CRC malo, level_flag, mode
del motor, domain id equivocado). Este script lo distingue: lee q, comanda
q + offset, y comprueba en lowstate que q se mueve de verdad.

Por defecto SOLO funciona contra el simulador. Para el robot real hay que
pasar --real-robot-i-have-read-safety y el robot debe estar SUSPENDIDO o
tumbado de lado, con las patas sin carga.

Uso:
    python3 tools/check_write_path.py                       # sim, articulacion FR_thigh
    python3 tools/check_write_path.py --joint 1 --offset 0.2
    python3 tools/check_write_path.py --list-joints
"""

import argparse
import sys
import time

try:
    from unitree_sdk2py.core.channel import (
        ChannelFactoryInitialize,
        ChannelPublisher,
        ChannelSubscriber,
    )
    from unitree_sdk2py.idl.default import unitree_go_msg_dds__LowCmd_
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowCmd_, LowState_
    from unitree_sdk2py.utils.crc import CRC
except ImportError:
    sys.exit("ERROR: falta unitree_sdk2_python. Activa el venv: source ~/venvs/go2/bin/activate")

GREEN, YELLOW, RED, BLUE, RESET = "\033[32m", "\033[33m", "\033[31m", "\033[34m", "\033[0m"

# Orden de motores del Go2 (unitree_go). Los 12 primeros son las articulaciones.
JOINT_NAMES = [
    "FR_hip", "FR_thigh", "FR_calf",
    "FL_hip", "FL_thigh", "FL_calf",
    "RR_hip", "RR_thigh", "RR_calf",
    "RL_hip", "RL_thigh", "RL_calf",
]
N_JOINTS = 12


class StateCache:
    def __init__(self):
        self.msg = None
        self.count = 0

    def __call__(self, msg):
        self.msg = msg
        self.count += 1

    def wait(self, timeout=5.0):
        t0 = time.time()
        while self.msg is None and time.time() - t0 < timeout:
            time.sleep(0.02)
        return self.msg


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--joint", type=int, default=1, help="indice 0-11 (def. 1 = FR_thigh)")
    p.add_argument("--offset", type=float, default=0.15, help="rad a sumar sobre la posicion actual")
    p.add_argument("--kp", type=float, default=20.0)
    p.add_argument("--kd", type=float, default=0.8)
    p.add_argument("--ramp", type=float, default=2.0, help="segundos de rampa")
    p.add_argument("--iface", default=None)
    p.add_argument("--domain", type=int, default=None)
    p.add_argument("--list-joints", action="store_true")
    p.add_argument("--real-robot-i-have-read-safety", action="store_true",
                   help="permite ejecutar contra el robot fisico (domain 0)")
    args = p.parse_args()

    if args.list_joints:
        for i, n in enumerate(JOINT_NAMES):
            print(f"  {i:2d}  {n}")
        return

    real = args.real_robot_i_have_read_safety
    iface = args.iface or ("lo" if not real else None)
    domain = args.domain if args.domain is not None else (1 if not real else 0)

    if real and not iface:
        sys.exit("ERROR: en modo real hay que indicar --iface")
    if not (0 <= args.joint < N_JOINTS):
        sys.exit(f"ERROR: --joint debe estar entre 0 y {N_JOINTS - 1}")

    print(f"\n{BLUE}=== Test del camino de escritura (rt/lowcmd) ==={RESET}")
    print(f"  {'ROBOT REAL' if real else 'simulador'} | domain {domain} | iface {iface}")
    print(f"  articulacion: {args.joint} ({JOINT_NAMES[args.joint]})  offset: {args.offset:+.3f} rad")

    if real:
        print(f"\n{RED}  ROBOT FISICO. Antes de continuar confirma:{RESET}")
        print("   - robot SUSPENDIDO o tumbado de lado, patas sin carga")
        print("   - sport_mode liberado (MotionSwitcher.ReleaseMode)")
        print("   - mando en la mano")
        if input("\n  Escribe 'si' para continuar: ").strip().lower() != "si":
            sys.exit("Abortado.")

    ChannelFactoryInitialize(domain, iface)

    cache = StateCache()
    sub = ChannelSubscriber("rt/lowstate", LowState_)
    sub.Init(cache, 10)

    print("\n  Esperando rt/lowstate...")
    if cache.wait() is None:
        sys.exit(f"{RED}  No llega lowstate. Arregla primero la lectura (dds_smoketest.py).{RESET}")
    print(f"  {GREEN}lowstate recibido{RESET} ({cache.count} mensajes)")

    pub = ChannelPublisher("rt/lowcmd", LowCmd_)
    pub.Init()
    crc = CRC()

    # Pose de partida: la actual. Mantenemos TODAS las articulaciones en su
    # posicion actual y solo movemos la elegida. Asi el test es minimamente
    # invasivo tambien en el robot real.
    start_q = [cache.msg.motor_state[i].q for i in range(N_JOINTS)]
    q0 = start_q[args.joint]
    target = q0 + args.offset
    print(f"\n  q inicial = {q0:+.4f} rad   ->   objetivo = {target:+.4f} rad")

    cmd = unitree_go_msg_dds__LowCmd_()
    cmd.head[0], cmd.head[1] = 0xFE, 0xEF
    cmd.level_flag = 0xFF
    cmd.gpio = 0

    dt = 0.002                      # 500 Hz
    n_steps = int(args.ramp / dt)
    print(f"  Rampa de {args.ramp:.1f}s a 500 Hz ({n_steps} pasos)...\n")

    for step in range(n_steps):
        alpha = (step + 1) / n_steps
        for i in range(N_JOINTS):
            m = cmd.motor_cmd[i]
            m.mode = 0x01                                  # servo (PMSM) habilitado
            m.q = start_q[i] if i != args.joint else (1 - alpha) * q0 + alpha * target
            m.dq = 0.0
            m.kp = args.kp
            m.kd = args.kd
            m.tau = 0.0
        cmd.crc = crc.Crc(cmd)
        pub.Write(cmd)
        time.sleep(dt)

    time.sleep(0.5)                                        # dejar asentar
    q_final = cache.msg.motor_state[args.joint].q
    tau_final = getattr(cache.msg.motor_state[args.joint], "tau_est", 0.0)

    moved = q_final - q0
    error = target - q_final
    ratio = moved / args.offset if args.offset else 0.0

    print(f"{BLUE}--- Resultado ---{RESET}")
    print(f"  q final           = {q_final:+.4f} rad")
    print(f"  desplazamiento    = {moved:+.4f} rad  ({ratio * 100:5.1f}% del comandado)")
    print(f"  error de posicion = {error:+.4f} rad")
    print(f"  par estimado      = {tau_final:+.3f} Nm")

    # Volver suavemente a la posicion de partida
    print("\n  Volviendo a la posicion inicial...")
    for step in range(n_steps):
        alpha = (step + 1) / n_steps
        for i in range(N_JOINTS):
            m = cmd.motor_cmd[i]
            m.mode = 0x01
            m.q = start_q[i] if i != args.joint else (1 - alpha) * q_final + alpha * q0
            m.dq, m.kp, m.kd, m.tau = 0.0, args.kp, args.kd, 0.0
        cmd.crc = crc.Crc(cmd)
        pub.Write(cmd)
        time.sleep(dt)

    print(f"\n{BLUE}--- Veredicto ---{RESET}")
    if ratio > 0.5:
        print(f"  {GREEN}CAMINO DE ESCRITURA VALIDADO.{RESET} El comando llega y se ejecuta.")
        print("  El CRC, el level_flag y el mode de motor son correctos.")
        sys.exit(0)
    elif ratio > 0.05:
        print(f"  {YELLOW}El comando LLEGA pero el seguimiento es pobre ({ratio * 100:.0f}%).{RESET}")
        print("  Prueba a subir --kp. El DDS esta bien; es un tema de ganancias o de carga.")
        sys.exit(0)
    else:
        print(f"  {RED}EL COMANDO NO SURTE EFECTO.{RESET} Revisa, en este orden:")
        print("   1. CRC: cmd.crc = CRC().Crc(cmd) DESPUES de rellenar todos los campos")
        print("   2. cmd.head = [0xFE, 0xEF] y cmd.level_flag = 0xFF")
        print("   3. motor_cmd[i].mode = 0x01 en las 12 articulaciones")
        print("   4. domain id e interfaz iguales en el emisor y en el simulador/robot")
        print("   5. en robot real: sport_mode NO liberado es la causa mas frecuente")
        sys.exit(1)


if __name__ == "__main__":
    main()
