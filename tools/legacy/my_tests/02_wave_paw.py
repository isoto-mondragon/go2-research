"""02_wave_paw.py — Saludo con la pata FR (version 2)."""
import sys, time, math
import numpy as np

sys.path.insert(0, "/home/isoto/robotics/my_tests/lib")
from go2_robot import Go2Interface, STAND_POSE, interpolate

RATE_HZ = 200
DT = 1.0 / RATE_HZ

FR_HIP, FR_THIGH, FR_CALF = 0, 1, 2

# Postura tripode: FR levantada con la rodilla muy plegada,
# y las OTRAS patas un poco mas flexionadas para bajar el centro de masa
TRIPOD_POSE = STAND_POSE.copy()
TRIPOD_POSE[FR_THIGH] = 0.20    # cadera FR muy hacia delante
TRIPOD_POSE[FR_CALF]  = -1.20   # rodilla muy plegada
# Bajamos un poco las otras 3 patas para mejor base de apoyo
for leg in [1, 2, 3]:  # FL, RR, RL
    TRIPOD_POSE[leg*3 + 1] += 0.15   # mas flexion thigh
    TRIPOD_POSE[leg*3 + 2] -= 0.20   # mas flexion calf


def main():
    robot = Go2Interface(domain_id=1, interface="lo")
    q_now = robot.read_joint_positions()

    # Activar suave
    for i in range(int(1.0 * RATE_HZ)):
        ramp = i / (1.0 * RATE_HZ)
        robot.send_joint_targets(q_now, kp=30.0 * ramp, kd=3.0)
        time.sleep(DT)

    # Levantar
    print("[INFO] Levantando...")
    n = int(3.0 * RATE_HZ)
    for i in range(n):
        q = interpolate(q_now, STAND_POSE, i/n)
        robot.send_joint_targets(q, kp=100.0, kd=6.0)
        time.sleep(DT)

    # Asentar
    for _ in range(int(2.0 * RATE_HZ)):
        robot.send_joint_targets(STAND_POSE, kp=100.0, kd=6.0)
        time.sleep(DT)

    # Pasar a tripode LENTAMENTE (3 s)
    print("[INFO] Levantando pata FR...")
    n = int(3.0 * RATE_HZ)
    for i in range(n):
        q = interpolate(STAND_POSE, TRIPOD_POSE, i/n)
        robot.send_joint_targets(q, kp=120.0, kd=8.0)
        time.sleep(DT)

    # Saludar — solo movemos hip de FR, rango pequeno
    print("[INFO] Saludando...")
    t0 = time.time()
    while time.time() - t0 < 4.0:
        t = time.time() - t0
        q = TRIPOD_POSE.copy()
        q[FR_HIP] = 0.25 * math.sin(2 * math.pi * 1.0 * t)  # 1 Hz, ±0.25 rad
        robot.send_joint_targets(q, kp=120.0, kd=8.0)
        time.sleep(DT)

    # Bajar pata
    print("[INFO] Bajando pata...")
    n = int(2.0 * RATE_HZ)
    for i in range(n):
        q = interpolate(TRIPOD_POSE, STAND_POSE, i/n)
        robot.send_joint_targets(q, kp=100.0, kd=6.0)
        time.sleep(DT)

    # Damping final
    for _ in range(int(1.0 * RATE_HZ)):
        robot.send_damping(kd=2.0)
        time.sleep(DT)


if __name__ == "__main__":
    main()