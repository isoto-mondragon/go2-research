"""03_squat.py — Sentadillas verticales del Go2 (version 2)."""
import sys, time, math
import numpy as np

sys.path.insert(0, "/home/isoto/robotics/my_tests/lib")
from go2_robot import Go2Interface, STAND_POSE, interpolate

RATE_HZ = 200
DT = 1.0 / RATE_HZ


def squat_pose(depth):
    """
    depth en [0, 1]: 0 = stand, 1 = agachado.
    Modificamos thigh y calf manteniendo la simetria delante/detras.
    """
    q = STAND_POSE.copy()
    extra_thigh = 0.25 * depth   # antes 0.4, ahora reducido
    extra_calf  = -0.45 * depth  # antes -0.7, ahora reducido
    for leg in range(4):
        q[leg*3 + 1] += extra_thigh
        q[leg*3 + 2] += extra_calf
    return q


def main():
    robot = Go2Interface(domain_id=1, interface="lo")
    q_now = robot.read_joint_positions()

    # 1. Activar motores suavemente en postura actual
    print("[INFO] Activando motores...")
    for i in range(int(1.0 * RATE_HZ)):
        ramp = i / (1.0 * RATE_HZ)
        robot.send_joint_targets(q_now, kp=30.0 * ramp, kd=3.0)
        time.sleep(DT)

    # 2. Levantar a STAND_POSE con kp ALTO
    print("[INFO] Levantando con kp=100...")
    n = int(3.5 * RATE_HZ)
    for i in range(n):
        q = interpolate(q_now, STAND_POSE, i/n)
        robot.send_joint_targets(q, kp=100.0, kd=6.0)
        time.sleep(DT)

    # 3. Mantener 2 s para asentar
    print("[INFO] Asentando...")
    for _ in range(int(2.0 * RATE_HZ)):
        robot.send_joint_targets(STAND_POSE, kp=100.0, kd=6.0)
        time.sleep(DT)

    # 4. Sentadillas a 0.4 Hz (mas lentas = menos inercia)
    print("[INFO] Sentadillas...")
    t0 = time.time()
    while time.time() - t0 < 8.0:
        t = time.time() - t0
        depth = 0.5 * (1 - math.cos(2 * math.pi * 0.4 * t))
        q = squat_pose(depth)
        robot.send_joint_targets(q, kp=120.0, kd=8.0)
        time.sleep(DT)

    # 5. Volver a stand y damping
    for _ in range(int(2.0 * RATE_HZ)):
        robot.send_joint_targets(STAND_POSE, kp=100.0, kd=6.0)
        time.sleep(DT)
    for _ in range(int(1.0 * RATE_HZ)):
        robot.send_damping(kd=2.0)
        time.sleep(DT)


if __name__ == "__main__":
    main()
