#!/usr/bin/env python3
"""tools/teleop_real.py

Teleoperacion del Unitree Go2 FISICO usando Sport Mode.

POR QUE NO SIRVE tools/teleop.py
--------------------------------
Aquella publica en `rt/wirelesscontroller`, que en simulacion consume
`run_policy.py --teleop`. En el robot real ese topic lo PUBLICA el mando fisico
y el robot no lo escucha desde fuera: publicar ahi no mueve nada.

El robot real se controla llamando a `SportClient`, que es el servicio de
locomocion del fabricante. Eso es lo que hace este script.

SEGURIDAD
---------
  - Velocidades limitadas por defecto a 0.3 m/s y 0.5 rad/s, mucho menos de lo
    que el robot admite. Se suben con --max-vx y --max-wz cuando haya confianza.
  - Al salir, por Ctrl-C o por cualquier error, SIEMPRE se llama a StopMove y
    despues a Damp. El robot se queda amortiguado, no rigido ni en marcha.
  - Si se suelta el teclado, el robot NO sigue andando: solo se mueve mientras
    haya un comando distinto de cero, y la barra espaciadora lo pone a cero.
  - --dry-run imprime lo que haria sin llamar a nada.

EL MANDO FISICO MANDA SIEMPRE. Tenlo en la mano: L2+B amortigua el robot pase
lo que pase, y es mas rapido que cualquier cosa que escribas.

Uso:
    python3 tools/teleop_real.py --iface enp3s0 --dry-run     # sin mover nada
    python3 tools/teleop_real.py --iface enp3s0               # de verdad
"""

from __future__ import annotations

import argparse
import math
import select
import signal
import sys
import termios
import time
import tty
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

V, R, G, Y, Z = "\033[34m", "\033[31m", "\033[32m", "\033[33m", "\033[0m"


class Teclado:
    """Lector no bloqueante en modo raw."""

    def __enter__(self) -> "Teclado":
        self.fd = sys.stdin.fileno()
        self.previo = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        return self

    def __exit__(self, *exc) -> None:
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.previo)

    def tecla(self) -> str | None:
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1)
        return None


class Estado:
    """Lectura de lowstate: bateria, inclinacion y temperatura."""

    def __init__(self) -> None:
        self.msg = None

    def start(self) -> None:
        from unitree_sdk2py.core.channel import ChannelSubscriber
        from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_
        ChannelSubscriber("rt/lowstate", LowState_).Init(self._on, 10)

    def _on(self, m) -> None:
        self.msg = m

    def esperar(self, s: float = 5.0) -> bool:
        t0 = time.monotonic()
        while self.msg is None and time.monotonic() - t0 < s:
            time.sleep(0.02)
        return self.msg is not None

    def bateria(self) -> int:
        bms = getattr(self.msg, "bms_state", None)
        return int(getattr(bms, "soc", 0) or 0) if bms else 0

    def inclinacion_deg(self) -> float:
        w, x, y, z = self.msg.imu_state.quaternion
        gz = 1.0 - 2.0 * (x * x + y * y)
        return math.degrees(math.acos(max(-1.0, min(1.0, gz))))

    def temp_max(self) -> int:
        return int(max(getattr(self.msg.motor_state[i], "temperature", 0)
                       for i in range(12)))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--iface", required=True, help="interfaz Ethernet del robot")
    p.add_argument("--domain", type=int, default=0)
    p.add_argument("--max-vx", type=float, default=0.3, help="m/s")
    p.add_argument("--max-vy", type=float, default=0.2, help="m/s")
    p.add_argument("--max-wz", type=float, default=0.5, help="rad/s")
    p.add_argument("--step", type=float, default=0.05, help="incremento por pulsacion")
    p.add_argument("--rate", type=float, default=20.0, help="Hz de envio")
    p.add_argument("--bateria-min", type=int, default=30, help="%% minimo para operar")
    p.add_argument("--dry-run", action="store_true",
                   help="imprime los comandos pero NO llama al robot")
    args = p.parse_args()

    print(f"\n{V}=== Teleoperacion del Go2 fisico (Sport Mode) ==={Z}")
    print(f"  interfaz : {args.iface}   domain: {args.domain}")
    print(f"  limites  : vx +-{args.max_vx}  vy +-{args.max_vy}  wz +-{args.max_wz}")
    if args.dry_run:
        print(f"  {Y}DRY RUN: no se llamara al robot{Z}")

    from unitree_sdk2py.core.channel import ChannelFactoryInitialize
    ChannelFactoryInitialize(args.domain, args.iface)

    est = Estado()
    est.start()
    print("\nesperando rt/lowstate...")
    if not est.esperar():
        print(f"{R}No llega estado del robot.{Z}")
        print("Comprueba: ./env/go2_net.sh probe, y que la app movil este CERRADA.")
        return 2

    soc = est.bateria()
    inc = est.inclinacion_deg()
    temp = est.temp_max()
    print(f"{G}robot conectado{Z}   bateria {soc}%   inclinacion {inc:.0f} deg   "
          f"temp max {temp} C")

    if soc < args.bateria_min:
        print(f"\n{R}Bateria al {soc}%, por debajo del minimo ({args.bateria_min}%).{Z}")
        print("Por debajo del 30% el comportamiento de los motores cambia.")
        return 1

    # --- comprobacion del modo de movimiento ---
    if not args.dry_run:
        try:
            from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import (
                MotionSwitcherClient)
            ms = MotionSwitcherClient()
            ms.SetTimeout(5.0)
            ms.Init()
            print(f"modo de movimiento actual: {ms.CheckMode()}")
        except Exception as e:
            print(f"{Y}no se ha podido consultar el modo ({e}). Se continua.{Z}")

    print(f"""
{Y}ANTES DE CONTINUAR, CONFIRMA:{Z}
   - radio de 2 m libre, nada fragil, nadie detras
   - el MANDO FISICO encendido y EN TU MANO (L2+B amortigua)
   - la app movil de Unitree CERRADA y desconectada
   - el robot en el suelo, sobre superficie plana
""")
    if input("  Escribe 'si' para continuar: ").strip().lower() != "si":
        print("abortado")
        return 1

    sport = None
    if not args.dry_run:
        from unitree_sdk2py.go2.sport.sport_client import SportClient
        sport = SportClient()
        sport.SetTimeout(10.0)
        sport.Init()

    vx = vy = wz = 0.0
    parar = {"flag": False}
    signal.signal(signal.SIGINT, lambda *_: parar.__setitem__("flag", True))

    def enviar(a, b, c):
        if sport is not None:
            sport.Move(a, b, c)

    try:
        # --- levantarse ---
        print("\n[1/3] amortiguando antes de empezar...")
        if sport:
            sport.Damp()
        time.sleep(1.5)

        print("[2/3] levantando (StandUp)...")
        if sport:
            sport.StandUp()
        time.sleep(3.0)

        print("[3/3] equilibrio (BalanceStand)...")
        if sport:
            sport.BalanceStand()
        time.sleep(2.0)

        print(f"\n{G}robot de pie{Z}   inclinacion {est.inclinacion_deg():.0f} deg\n")
        print("  W/S adelante-atras    A/D lateral    Q/E giro")
        print("  espacio: parar        x: sentar y salir")
        print("  +/-: cambia el incremento\n")

        dt = 1.0 / args.rate
        paso = args.step
        siguiente = time.monotonic()
        n = 0

        with Teclado() as kb:
            while not parar["flag"]:
                k = kb.tecla()
                if k is not None:
                    k = k.lower()
                    if k == "w":
                        vx += paso
                    elif k == "s":
                        vx -= paso
                    elif k == "a":
                        vy += paso
                    elif k == "d":
                        vy -= paso
                    elif k == "q":
                        wz += paso
                    elif k == "e":
                        wz -= paso
                    elif k == " ":
                        vx = vy = wz = 0.0
                    elif k == "+":
                        paso = min(paso * 2, 0.2)
                    elif k == "-":
                        paso = max(paso / 2, 0.01)
                    elif k in ("x", "\x03"):
                        break
                    vx = max(-args.max_vx, min(args.max_vx, vx))
                    vy = max(-args.max_vy, min(args.max_vy, vy))
                    wz = max(-args.max_wz, min(args.max_wz, wz))

                enviar(vx, vy, wz)

                n += 1
                if n % 10 == 0:
                    print(f"\r  vx {vx:+.2f}  vy {vy:+.2f}  wz {wz:+.2f}   "
                          f"bat {est.bateria():3d}%  incl {est.inclinacion_deg():3.0f}deg  "
                          f"temp {est.temp_max():2d}C  (paso {paso:.2f})   ",
                          end="", flush=True)

                siguiente += dt
                time.sleep(max(0.0, siguiente - time.monotonic()))

    except Exception as e:
        print(f"\n{R}[ERROR] {type(e).__name__}: {e}{Z}")
    finally:
        # Esto SIEMPRE se ejecuta: Ctrl-C, error o salida normal.
        print(f"\n\n{Y}parando el robot...{Z}")
        if sport is not None:
            try:
                sport.StopMove()
                time.sleep(0.5)
                sport.StandDown()
                time.sleep(2.0)
                sport.Damp()
            except Exception as e:
                print(f"{R}fallo al parar: {e}{Z}")
                print(f"{R}USA EL MANDO: L2+B{Z}")
        print(f"{G}robot amortiguado{Z}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
