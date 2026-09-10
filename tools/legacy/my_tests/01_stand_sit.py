"""
01_stand_sit.py
Secuencia segura: lee postura actual -> levanta -> mantiene -> tumba -> damping.
"""
import sys
import time
import numpy as np

# Permite importar lib/go2_robot.py
sys.path.insert(0, "/home/isoto/robotics/my_tests/lib")
from go2_robot import Go2Interface, LIE_POSE, STAND_POSE, interpolate


RATE_HZ = 200
DT = 1.0 / RATE_HZ


def go_to_pose(robot, q_start, q_end, duration_s, kp=60.0, kd=5.0):
    """Interpola entre dos posturas a lo largo de duration_s segundos."""
    n = int(duration_s * RATE_HZ)
    for i in range(n):
        alpha = i / n
        q = interpolate(q_start, q_end, alpha)
        robot.send_joint_targets(q, kp=kp, kd=kd)
        time.sleep(DT)


def hold_pose(robot, q, duration_s, kp=60.0, kd=5.0):
    """Mantiene una postura durante duration_s segundos."""
    n = int(duration_s * RATE_HZ)
    for _ in range(n):
        robot.send_joint_targets(q, kp=kp, kd=kd)
        time.sleep(DT)


def main():
    robot = Go2Interface(domain_id=1, interface="lo")

    # 1. Leemos la postura ACTUAL en vez de asumir LIE_POSE
    q_now = robot.read_joint_positions()
    print(f"[INFO] Postura inicial leida: {np.round(q_now, 2)}")

    # 2. Activamos los motores SUAVEMENTE en la postura actual
    #    (kp/kd bajos al principio para que no haya tirones)
    print("[INFO] Activando motores con ganancias suaves...")
    for i in range(int(1.0 * RATE_HZ)):
        ramp = i / (1.0 * RATE_HZ)
        robot.send_joint_targets(q_now, kp=20.0 * ramp, kd=2.0)
        time.sleep(DT)

    # 3. Levantar
    print("[INFO] Levantando...")
    go_to_pose(robot, q_now, STAND_POSE, duration_s=3.0, kp=60.0, kd=5.0)

    # 4. Mantener
    print("[INFO] Manteniendo de pie 5 s...")
    hold_pose(robot, STAND_POSE, duration_s=5.0)

    # 5. Volver a tumbarse despacio
    print("[INFO] Sentandose...")
    go_to_pose(robot, STAND_POSE, LIE_POSE, duration_s=4.0, kp=40.0, kd=5.0)

    # 6. Apagar suavemente con damping (en vez de cortar de golpe)
    print("[INFO] Aplicando damping y terminando...")
    for _ in range(int(1.0 * RATE_HZ)):
        robot.send_damping(kd=2.0)
        time.sleep(DT)

    print("[INFO] Hecho.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Detenido por el usuario.")
        sys.exit(0)
