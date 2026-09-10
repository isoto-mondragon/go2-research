"""
00_find_stand_pose.py (v2)

Sube al Go2 a la postura nominal de Unitree (kp altos), espera a que se
asiente, y luego MIDE la postura real cuando los pies estan apoyados.

Diferencias clave respecto a la v1:
- Postura objetivo correcta: thigh=0.67, calf=-1.30 (validada por Unitree).
- Subida MAS LENTA (5 s) y con kp progresivo, evitando latigazos.
- Asentamiento de 6 s para que la fisica converja a un equilibrio real.
- Comprueba que las rodillas no esten dobladas hacia el lado equivocado.
"""
import sys, time
import numpy as np

sys.path.insert(0, "/home/isoto/robotics/my_tests/lib")
from go2_robot import Go2Interface, JOINT_NAMES, interpolate

RATE_HZ = 200
DT = 1.0 / RATE_HZ

# Postura nominal del Go2 segun el SDK oficial (validada hw + sim)
STAND_TARGET = np.array([
     0.0,  0.67, -1.30,
     0.0,  0.67, -1.30,
     0.0,  0.67, -1.30,
     0.0,  0.67, -1.30,
])


def main():
    robot = Go2Interface(domain_id=1, interface="lo")
    q0 = robot.read_joint_positions()
    print(f"[INFO] Postura inicial leida:")
    for leg, name in enumerate(["FR", "FL", "RR", "RL"]):
        h, t, c = q0[leg*3:leg*3+3]
        print(f"  {name}:  hip={h:+.3f}  thigh={t:+.3f}  calf={c:+.3f}")

    # 1. Activar motores en postura actual con ganancia rampeada
    print("\n[INFO] Activando motores con kp rampeado (1.5 s)...")
    n = int(1.5 * RATE_HZ)
    for i in range(n):
        ramp = i / n
        robot.send_joint_targets(q0, kp=40.0 * ramp, kd=3.0)
        time.sleep(DT)

    # 2. Subida LENTA a STAND_TARGET (5 s)
    print("[INFO] Subiendo a stand en 5 s...")
    n = int(5.0 * RATE_HZ)
    for i in range(n):
        alpha = i / n
        # smoothstep: aceleracion y deceleracion suaves
        s = alpha * alpha * (3 - 2 * alpha)
        q = interpolate(q0, STAND_TARGET, s)
        robot.send_joint_targets(q, kp=80.0, kd=5.0)
        time.sleep(DT)

    # 3. Asentar 6 s con kp alto
    print("[INFO] Asentando 6 s con kp=100...")
    for _ in range(int(6.0 * RATE_HZ)):
        robot.send_joint_targets(STAND_TARGET, kp=100.0, kd=6.0)
        time.sleep(DT)

    # 4. MEDIR durante 2 s
    print("[INFO] Midiendo postura de equilibrio...")
    samples = []
    for _ in range(int(2.0 * RATE_HZ)):
        robot.send_joint_targets(STAND_TARGET, kp=100.0, kd=6.0)
        q = robot.read_joint_positions()
        samples.append(q)
        time.sleep(DT)
    q_real = np.mean(samples, axis=0)

    # 5. Mostrar y validar
    print("\n=================================================")
    print("POSTURA MEDIDA EN EQUILIBRIO:")
    print("=================================================")
    print("STAND_POSE = np.array([")
    valid = True
    for leg in range(4):
        h, t, c = q_real[leg*3:leg*3+3]
        name = ["FR", "FL", "RR", "RL"][leg]
        warn = ""
        # Calf debe ser claramente NEGATIVO (entre -1.0 y -1.6)
        if c > -1.0:
            warn = "  <-- CALF SOSPECHOSA"
            valid = False
        # Thigh debe estar entre 0.4 y 1.0
        if t < 0.4 or t > 1.0:
            warn += "  <-- THIGH SOSPECHOSA"
            valid = False
        print(f"    {h:+.3f}, {t:+.3f}, {c:+.3f},   # {name}{warn}")
    print("])")
    print("=================================================")

    if valid:
        print("\n[OK] La postura parece correcta. Copia el bloque a lib/go2_robot.py")
    else:
        print("\n[!!] La postura medida tiene anomalias. NO la uses tal cual.")
        print("     Lee mas abajo el diagnostico.")

    # 6. Diferencia entre target y medido
    diff = q_real - STAND_TARGET
    max_diff = np.max(np.abs(diff))
    print(f"\nMax desviacion respecto a target: {max_diff:.3f} rad")
    if max_diff > 0.15:
        print("[!] Desviacion alta: posible deslizamiento o postura inestable.")

    # 7. Bajada
    print("\n[INFO] Bajando suavemente...")
    n = int(4.0 * RATE_HZ)
    for i in range(n):
        alpha = i / n
        s = alpha * alpha * (3 - 2 * alpha)
        q = interpolate(q_real, q0, s)
        robot.send_joint_targets(q, kp=60.0, kd=5.0)
        time.sleep(DT)
    for _ in range(int(1.0 * RATE_HZ)):
        robot.send_damping(kd=2.0)
        time.sleep(DT)


if __name__ == "__main__":
    main()