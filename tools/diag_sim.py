#!/usr/bin/env python3
"""
tools/diag_sim.py

Diagnostico para cuando un LowCmd "no hace nada". Responde tres preguntas
que juntas localizan el fallo sin ambiguedad:

  1. ¿El simulador esta integrando fisica?     -> las 12 q cambian con el tiempo
  2. ¿El estado es plausible o son ceros?      -> pose de pie vs todo a cero
  3. ¿Mi LowCmd sale de verdad a la red?       -> escucha rt/lowcmd de terceros

Uso:
    # Terminal 1: unitree_mujoco corriendo
    # Terminal 2:
    python3 tools/diag_sim.py
    # Terminal 3 (mientras el anterior escucha):
    python3 tools/check_write_path.py --joint 0 --kp 100 --offset 0.2
"""

import argparse
import time
import sys

try:
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowCmd_, LowState_
except ImportError:
    sys.exit("ERROR: activa el venv: source ~/venvs/go2/bin/activate")

G, Y, R, B, Z = "\033[32m", "\033[33m", "\033[31m", "\033[34m", "\033[0m"

JOINTS = ["FR_hip", "FR_thigh", "FR_calf", "FL_hip", "FL_thigh", "FL_calf",
          "RR_hip", "RR_thigh", "RR_calf", "RL_hip", "RL_thigh", "RL_calf"]

# Pose de pie tipica del Go2. Sirve de referencia de plausibilidad.
NOMINAL = [0.1, 0.8, -1.5, -0.1, 0.8, -1.5, 0.1, 1.0, -1.5, -0.1, 1.0, -1.5]


class Cache:
    def __init__(self):
        self.msg = None
        self.n = 0

    def __call__(self, m):
        self.msg = m
        self.n += 1


def snapshot(c):
    m = c.msg
    return (
        [m.motor_state[i].q for i in range(12)],
        [m.motor_state[i].dq for i in range(12)],
        [getattr(m.motor_state[i], "tau_est", 0.0) for i in range(12)],
        getattr(m, "tick", None),
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--domain", type=int, default=1)
    p.add_argument("--iface", default="lo")
    p.add_argument("--listen", type=float, default=20.0, help="segundos escuchando rt/lowcmd")
    args = p.parse_args()

    print(f"\n{B}=== Diagnostico del simulador ==={Z}")
    print(f"  domain {args.domain} | iface {args.iface}\n")

    ChannelFactoryInitialize(args.domain, args.iface)

    st = Cache()
    ChannelSubscriber("rt/lowstate", LowState_).Init(st, 10)

    cm = Cache()
    ChannelSubscriber("rt/lowcmd", LowCmd_).Init(cm, 10)

    t0 = time.time()
    while st.msg is None and time.time() - t0 < 5:
        time.sleep(0.05)
    if st.msg is None:
        sys.exit(f"{R}No llega rt/lowstate. El simulador no esta publicando.{Z}")

    # --- P1 y P2 -----------------------------------------------------
    q1, dq1, tau1, tick1 = snapshot(st)
    n1 = st.n
    time.sleep(2.0)
    q2, dq2, tau2, tick2 = snapshot(st)
    hz = (st.n - n1) / 2.0

    print(f"{B}--- Estado articular ---{Z}")
    print(f"  {'articulacion':<10} {'q(t0)':>9} {'q(t0+2s)':>10} {'delta':>9} {'dq':>8} {'tau':>8} {'nominal':>8}")
    moved = 0
    for i, name in enumerate(JOINTS):
        d = q2[i] - q1[i]
        if abs(d) > 1e-4:
            moved += 1
        print(f"  {name:<10} {q1[i]:9.4f} {q2[i]:10.4f} {d:9.4f} {dq2[i]:8.3f} {tau2[i]:8.3f} {NOMINAL[i]:8.2f}")

    all_zero = all(abs(v) < 1e-6 for v in q2)
    plausible = sum(abs(q2[i] - NOMINAL[i]) < 0.5 for i in range(12)) >= 8
    tick_moves = tick1 != tick2

    print(f"\n  frecuencia lowstate : {hz:.0f} Hz")
    print(f"  tick avanza         : {'si' if tick_moves else 'NO'}")
    print(f"  articulaciones que se movieron en 2 s: {moved}/12")

    print(f"\n{B}--- P1: ¿el simulador integra fisica? ---{Z}")
    if all_zero:
        print(f"  {R}NO. Las 12 articulaciones estan a cero exacto.{Z}")
        print("  El simulador publica lowstate pero no hay estado real detras.")
        print("  Causas: hilo de mujoco caido, viewer en pausa (barra espaciadora),")
        print("  o el bridge publica un mensaje por defecto.")
    elif plausible:
        print(f"  {G}SI. La pose se parece a la nominal de pie.{Z} El estado es real.")
        if moved == 0:
            print(f"  {Y}Pero nada se mueve: el robot esta en equilibrio estatico o congelado.{Z}")
    else:
        print(f"  {Y}Estado no nulo pero raro. Compara la columna 'nominal'.{Z}")

    # --- P3 ----------------------------------------------------------
    print(f"\n{B}--- P3: ¿sale algun rt/lowcmd a la red? ---{Z}")
    print(f"  Escuchando {args.listen:.0f}s. Lanza AHORA check_write_path.py en otra terminal.\n")
    base = cm.n
    t0 = time.time()
    while time.time() - t0 < args.listen:
        time.sleep(0.25)
        print(f"\r  lowcmd recibidos: {cm.n - base:6d}", end="", flush=True)
    print("\n")

    got = cm.n - base
    if got == 0:
        print(f"  {R}CERO comandos vistos.{Z} El emisor no esta publicando, o publica")
        print("  en otro domain/interfaz. El problema esta en el lado EMISOR.")
    else:
        c = cm.msg
        print(f"  {G}{got} comandos vistos.{Z} El LowCmd SI sale a la red.")
        print(f"  head={list(c.head)} level_flag={c.level_flag} crc={c.crc}")
        print(f"  motor_cmd[0]: mode={c.motor_cmd[0].mode} q={c.motor_cmd[0].q:.4f} "
              f"kp={c.motor_cmd[0].kp} kd={c.motor_cmd[0].kd} tau={c.motor_cmd[0].tau}")

    # --- Veredicto ---------------------------------------------------
    print(f"\n{B}--- Veredicto ---{Z}")
    if got > 0 and (all_zero or not tick_moves):
        print(f"  {R}El comando sale pero el simulador no lo aplica.{Z}")
        print("  Fallo del lado SIMULADOR. Pasa al simulador C++ (ver instrucciones).")
    elif got > 0 and plausible and moved == 0:
        print(f"  {Y}El comando sale, el estado es real, pero no hay reaccion.{Z}")
        print("  El bridge de lowcmd del simulador Python no esta aplicando el PD.")
        print("  Fallo del lado SIMULADOR. Pasa al simulador C++.")
    elif got == 0:
        print(f"  {R}Fallo del lado EMISOR: revisa domain id e interfaz.{Z}")
    else:
        print(f"  {G}Cadena aparentemente sana. Repite check_write_path.py.{Z}")


if __name__ == "__main__":
    main()
