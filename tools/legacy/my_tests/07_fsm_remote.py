"""
07_fsm_remote.py
================
Publica pulsaciones virtuales en AMBAS variantes del topic de wireless
controller (con y sin guion bajo), para disparar transiciones del FSM.
"""
import sys
import time
sys.path.insert(0, "/home/isoto/robotics/unitree_sdk2_python")

from unitree_sdk2py.core.channel import (
    ChannelPublisher, ChannelFactoryInitialize,
)
from unitree_sdk2py.idl.unitree_go.msg.dds_ import WirelessController_
from unitree_sdk2py.idl.default import unitree_go_msg_dds__WirelessController_


# Bits segun WirelessController_ de Unitree:
# bit 0: R1     bit 1: L1     bit 2: start  bit 3: select
# bit 4: R2     bit 5: L2     bit 6: F1     bit 7: F2
# bit 8: A      bit 9: B      bit 10: X     bit 11: Y
# bit 12: up    bit 13: right bit 14: down  bit 15: left
KEY_BITS = {
    "R1": 0, "L1": 1, "start": 2, "select": 3,
    "R2": 4, "L2": 5, "F1": 6, "F2": 7,
    "A": 8, "B": 9, "X": 10, "Y": 11,
    "up": 12, "right": 13, "down": 14, "left": 15,
}


def make_mask(buttons):
    mask = 0
    for b in buttons:
        mask |= (1 << KEY_BITS[b])
    return mask


def main():
    ChannelFactoryInitialize(0, "lo")

    # Publica en ambas variantes del nombre del topic
    pub_underscore = ChannelPublisher("rt/wireless_controller", WirelessController_)
    pub_underscore.Init()
    pub_nounder = ChannelPublisher("rt/wirelesscontroller", WirelessController_)
    pub_nounder.Init()

    msg = unitree_go_msg_dds__WirelessController_()
    msg.lx = 0.0
    msg.ly = 0.0
    msg.rx = 0.0
    msg.ry = 0.0
    msg.keys = 0

    # Primero publicamos keys=0 durante 1 segundo, para que el FSM tenga
    # un "estado base" del que detectar el edge.
    print("Estableciendo estado base (keys=0) durante 1s...")
    for _ in range(50):
        pub_underscore.Write(msg)
        pub_nounder.Write(msg)
        time.sleep(0.02)

    def press_and_release(buttons, hold_s=0.6):
        # Pulsa
        msg.keys = make_mask(buttons)
        n = int(hold_s * 50)
        for _ in range(n):
            pub_underscore.Write(msg)
            pub_nounder.Write(msg)
            time.sleep(0.02)
        # Suelta
        msg.keys = 0
        for _ in range(int(0.4 * 50)):
            pub_underscore.Write(msg)
            pub_nounder.Write(msg)
            time.sleep(0.02)

    print("\n=== Botonera virtual lista. Domain=0 ===")
    print("Publicando en rt/wirelesscontroller Y rt/wireless_controller\n")

    print("[1/2] L2 + up  -> Passive a FixStand")
    input("    Pulsa Enter para enviar...")
    press_and_release(["L2", "up"])
    print("    Enviado. Mira go2_ctrl: deberia decir 'FSM: Change state from Passive to FixStand'.\n")

    time.sleep(2.0)

    print("[2/2] R2 + A   -> FixStand a Velocity (politica RL)")
    input("    Pulsa Enter cuando el robot este de pie y estable...")
    press_and_release(["R2", "A"])
    print("    Enviado. Mira go2_ctrl: deberia decir 'FSM: Change state from FixStand to Velocity'.\n")

    print("=== FSM en Velocity (idealmente) ===")
    print("Manteniendo keys=0. Ctrl+C para salir.")

    try:
        while True:
            msg.keys = 0
            pub_underscore.Write(msg)
            pub_nounder.Write(msg)
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nSaliendo.")


if __name__ == "__main__":
    main()