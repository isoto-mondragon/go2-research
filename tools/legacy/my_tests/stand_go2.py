"""
stand_go2.py
Hace que el Go2 pase de tumbado a de pie usando control PD a nivel
de motor, comunicándose con unitree_mujoco vía DDS.

Este MISMO código corre en el Go2 real cambiando 'ChannelFactoryInitialize'
de domain_id=1 (sim) a domain_id=0 (real) y la interface de 'lo' a 'eth0'.
"""
import time
import math
import sys

from unitree_sdk2py.core.channel import (
    ChannelPublisher, ChannelSubscriber, ChannelFactoryInitialize
)
from unitree_sdk2py.idl.default import unitree_go_msg_dds__LowCmd_
from unitree_sdk2py.idl.default import unitree_go_msg_dds__LowState_
from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowCmd_, LowState_
from unitree_sdk2py.utils.crc import CRC

# Mapa de motores del Go2 (12 articulaciones, 3 por pata)
# Convención: FR=0, FL=1, RR=2, RL=3 ; hip=0, thigh=1, calf=2
# Índice global = pata*3 + tipo
LEG_FR, LEG_FL, LEG_RR, LEG_RL = 0, 1, 2, 3

# Postura objetivo "de pie" (radianes)
STAND_POSE = [
    0.0,  0.78, -1.50,   # FR: hip, thigh, calf
    0.0,  0.78, -1.50,   # FL
    0.0,  0.78, -1.50,   # RR
    0.0,  0.78, -1.50,   # RL
]

# Postura "tumbado" (lo que el robot tiene al iniciar)
LIE_POSE = [
    0.0,  1.30, -2.70,
    0.0,  1.30, -2.70,
    0.0,  1.30, -2.70,
    0.0,  1.30, -2.70,
]

# Ganancias PD por articulación
KP = 60.0
KD = 5.0


def main():
    # Domain id = 1 -> simulador. Para el Go2 real sería 0.
    ChannelFactoryInitialize(1, "lo")

    pub = ChannelPublisher("rt/lowcmd", LowCmd_)
    pub.Init()

    cmd = unitree_go_msg_dds__LowCmd_()
    cmd.head = [0xFE, 0xEF]
    cmd.level_flag = 0xFF        # low-level mode
    cmd.gpio = 0
    crc = CRC()

    # Inicializa los 20 motor commands a "no hacer nada"
    for i in range(20):
        cmd.motor_cmd[i].mode = 0x01    # servo mode
        cmd.motor_cmd[i].q = 0.0
        cmd.motor_cmd[i].dq = 0.0
        cmd.motor_cmd[i].kp = 0.0
        cmd.motor_cmd[i].kd = 0.0
        cmd.motor_cmd[i].tau = 0.0

    # Interpolación suave de tumbado -> de pie en 3 segundos
    duration = 3.0
    rate_hz = 200
    n_steps = int(duration * rate_hz)
    dt = 1.0 / rate_hz

    print("Iniciando transición a postura de pie...")
    for step in range(n_steps):
        alpha = step / n_steps          # 0 -> 1
        for j in range(12):
            q_target = (1 - alpha) * LIE_POSE[j] + alpha * STAND_POSE[j]
            cmd.motor_cmd[j].q = q_target
            cmd.motor_cmd[j].dq = 0.0
            cmd.motor_cmd[j].kp = KP
            cmd.motor_cmd[j].kd = KD
            cmd.motor_cmd[j].tau = 0.0
        cmd.crc = crc.Crc(cmd)
        pub.Write(cmd)
        time.sleep(dt)

    print("De pie. Manteniendo postura 5 s...")
    for _ in range(5 * rate_hz):
        for j in range(12):
            cmd.motor_cmd[j].q = STAND_POSE[j]
            cmd.motor_cmd[j].kp = KP
            cmd.motor_cmd[j].kd = KD
        cmd.crc = crc.Crc(cmd)
        pub.Write(cmd)
        time.sleep(dt)

    print("Test completado.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDetenido por el usuario.")
        sys.exit(0)
