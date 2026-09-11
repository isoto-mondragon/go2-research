#!/usr/bin/env python3
"""tools/teleop.py

Teleoperacion por teclado publicando WirelessController_ por DDS.

Sustituye a src/go2core/comms/teleop_wireless.py, que nacio en el workspace
WSL2 con el dominio DDS 0 cableado. Aquel simulador (play_dds.py) usaba el
dominio 0; unitree_mujoco usa el 1 y el robot real el 0. Aqui el dominio y la
interfaz salen del bloque `dds` del contrato, asi que el mismo comando vale
para simulacion y para el robot cambiando solo --mode.

Mapeo (identico al de go2_controller.py y al mando del Go2):
    ly = vx   adelante / atras     W / S
    lx = vy   lateral izq / der    A / D
    rx = wz   giro izq / der       Q / E
    espacio   parada total
    x         cero y salir
    +/-       cambia el incremento por pulsacion

Uso:
    python3 tools/teleop.py --mode sim
    python3 tools/teleop.py --mode real --iface enp3s0
"""

from __future__ import annotations

import argparse
import select
import sys
import termios
import time
import tty
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from go2core.control import contract as ct          # noqa: E402

from unitree_sdk2py.core.channel import (           # noqa: E402
    ChannelFactoryInitialize,
    ChannelPublisher,
)
from unitree_sdk2py.idl.unitree_go.msg.dds_ import WirelessController_  # noqa: E402

DEFAULT_CONTRACT = REPO_ROOT / "usecases/uc01_locomotion/configs/robot_go2.yaml"


class RawKeyboard:
    """Lector de teclado no bloqueante en modo raw."""

    def __enter__(self) -> "RawKeyboard":
        self.fd = sys.stdin.fileno()
        self.old = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        return self

    def __exit__(self, *exc) -> None:
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)

    def get(self) -> str | None:
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1)
        return None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=["sim", "real"], default="sim")
    p.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    p.add_argument("--iface", default=None, help="anula la interfaz del contrato")
    p.add_argument("--domain", type=int, default=None, help="anula el dominio del contrato")
    p.add_argument("--step", type=float, default=0.1, help="incremento por pulsacion")
    p.add_argument("--rate", type=float, default=50.0, help="Hz de publicacion")
    args = p.parse_args()

    c = ct.load_contract(args.contract)
    dds = c["dds"][args.mode]
    domain = args.domain if args.domain is not None else dds["domain_id"]
    iface = args.iface or dds["interface"]

    lo = np.asarray([c["commands"]["vx_range"][0], c["commands"]["vy_range"][0],
                     c["commands"]["wz_range"][0]], dtype=np.float32)
    hi = np.asarray([c["commands"]["vx_range"][1], c["commands"]["vy_range"][1],
                     c["commands"]["wz_range"][1]], dtype=np.float32)

    print(f"teleop | modo {args.mode} | domain {domain} | iface {iface}")
    print(f"rangos del contrato: vx {lo[0]}..{hi[0]}  vy {lo[1]}..{hi[1]}  wz {lo[2]}..{hi[2]}")
    print("  W/S  adelante/atras   A/D  lateral   Q/E  giro")
    print("  espacio  parar        x  salir       +/-  incremento\n")

    ChannelFactoryInitialize(domain, iface)
    pub = ChannelPublisher("rt/wirelesscontroller", WirelessController_)
    pub.Init()

    msg = WirelessController_(lx=0.0, ly=0.0, rx=0.0, ry=0.0, keys=0)
    cmd = np.zeros(3, dtype=np.float32)   # vx, vy, wz
    step = args.step
    dt = 1.0 / args.rate
    sent = 0
    next_t = time.monotonic()

    try:
        with RawKeyboard() as kb:
            while True:
                k = kb.get()
                if k is not None:
                    k = k.lower()
                    if k == "w":
                        cmd[0] += step
                    elif k == "s":
                        cmd[0] -= step
                    elif k == "a":
                        cmd[1] += step
                    elif k == "d":
                        cmd[1] -= step
                    elif k == "q":
                        cmd[2] += step
                    elif k == "e":
                        cmd[2] -= step
                    elif k == " ":
                        cmd[:] = 0.0
                    elif k == "+":
                        step = min(step * 2, 0.5)
                    elif k == "-":
                        step = max(step / 2, 0.01)
                    elif k in ("x", "\x03"):
                        break
                    cmd = np.clip(cmd, lo, hi)
                    print(f"\r  vx={cmd[0]:+.2f}  vy={cmd[1]:+.2f}  wz={cmd[2]:+.2f}   "
                          f"(paso {step:.2f})   ", end="", flush=True)

                # Mapeo a los ejes del mando
                msg.ly, msg.lx, msg.rx = float(cmd[0]), float(cmd[1]), float(cmd[2])
                pub.Write(msg)
                sent += 1

                next_t += dt
                time.sleep(max(0.0, next_t - time.monotonic()))
    except KeyboardInterrupt:
        pass
    finally:
        msg.lx = msg.ly = msg.rx = msg.ry = 0.0
        for _ in range(10):
            pub.Write(msg)
            time.sleep(0.01)
        print(f"\n\nparada enviada. {sent} mensajes publicados en rt/wirelesscontroller.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
