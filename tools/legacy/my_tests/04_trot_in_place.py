"""04_trot_in_place.py — Trote en el sitio (version 2 corregida)."""
import sys, time, math
import numpy as np

sys.path.insert(0, "/home/isoto/robotics/my_tests/lib")
from go2_robot import Go2Interface, STAND_POSE, interpolate

RATE_HZ = 200
DT = 1.0 / RATE_HZ

PAIR_A = [0, 3]   # FR + RL
PAIR_B = [1, 2]   # FL + RR


def leg_in_swing(swing_amount, base_q):
    """
    Dada la postura base de la pata (3 angulos) y un swing en [0,1]:
    - swing=0: postura base (apoyo)
    - swing=1: pata levantada con flexion EQUILIBRADA en thigh y calf

    Es importante que al levantar la pata, el pie no se vaya hacia atras
    (eso provocaba que el robot caminase hacia atras).
    """
    h, t, c = base_q
    # Pata levantada: flexionamos thigh hacia DELANTE (mas negativo)
    # y plegamos calf. El pie sube cerca del cuerpo, sin empujar atras.
    return [
        h,
        t - 0.25 * swing_amount,   # cadera retrae LIGERAMENTE hacia delante
        c - 0.50 * swing_amount,   # rodilla pliega
    ]


def trot_pose(t, freq=1.2):
    """Postura de trote a frecuencia 'freq' Hz, fase 50/50."""
    q = STAND_POSE.copy()
    phase = 2 * math.pi * freq * t

    swing_a = max(0.0, math.sin(phase))
    swing_b = max(0.0, math.sin(phase + math.pi))

    for leg in PAIR_A:
        base = STAND_POSE[leg*3:leg*3+3]
        h, t_, c = leg_in_swing(swing_a, base)
        q[leg*3 + 0] = h
        q[leg*3 + 1] = t_
        q[leg*3 + 2] = c
    for leg in PAIR_B:
        base = STAND_POSE[leg*3:leg*3+3]
        h, t_, c = leg_in_swing(swing_b, base)
        q[leg*3 + 0] = h
        q[leg*3 + 1] = t_
        q[leg*3 + 2] = c
    return q


def main():
    robot = Go2Interface(domain_id=1, interface="lo")
    q_now = robot.read_joint_positions()

    # Activar suave
    for i in range(int(1.0 * RATE_HZ)):
        ramp = i / (1.0 * RATE_HZ)
        robot.send_joint_targets(q_now, kp=30.0 * ramp, kd=3.0)
        time.sleep(DT)

    # Levantar
    n = int(3.0 * RATE_HZ)
    for i in range(n):
        q = interpolate(q_now, STAND_POSE, i/n)
        robot.send_joint_targets(q, kp=100.0, kd=6.0)
        time.sleep(DT)

    # Asentar
    for _ in range(int(2.0 * RATE_HZ)):
        robot.send_joint_targets(STAND_POSE, kp=100.0, kd=6.0)
        time.sleep(DT)

    # Trotar — frecuencia BAJA (1.2 Hz) y kp alto
    print("[INFO] Trotando 6 s...")
    t0 = time.time()
    while time.time() - t0 < 6.0:
        t = time.time() - t0
        q = trot_pose(t, freq=1.2)
        robot.send_joint_targets(q, kp=120.0, kd=7.0)
        time.sleep(DT)

    # Stand final
    for _ in range(int(2.0 * RATE_HZ)):
        robot.send_joint_targets(STAND_POSE, kp=100.0, kd=6.0)
        time.sleep(DT)
    for _ in range(int(1.0 * RATE_HZ)):
        robot.send_damping(kd=2.0)
        time.sleep(DT)


if __name__ == "__main__":
    main()