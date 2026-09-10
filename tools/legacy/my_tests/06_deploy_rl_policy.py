"""
06_deploy_rl_policy.py
======================
Carga la politica ONNX entrenada en unitree_rl_mjlab (Unitree-Go2-Flat)
y la ejecuta sobre unitree_mujoco (o el robot real) via go2_robot.py.

Calibrado a partir de:
  deploy/robots/go2/config/policy/velocity/v0/params/deploy.yaml

Observacion (50 floats, en orden POLITICA):
  [0:3]    base_ang_vel              scale=1.0
  [3:6]    projected_gravity         scale=1.0
  [6:9]    velocity_commands (vx,vy,wz)  scale=1.0
  [9:11]   gait_phase (sin, cos), period=0.6s  scale=1.0
  [11:23]  joint_pos_rel (q - q_default, 12)   scale=1.0
  [23:35]  joint_vel_rel (12)        scale=1.0
  [35:47]  last_action (12)          scale=1.0
  Total: 47 - revisar al cargar; si la red espera 50, gait_phase puede ser (4)

Accion (12 floats, orden POLITICA):
  q_target_policy = offset + action * scale, con scale=0.25 y offset=q_default
"""
import sys
import time
import math
import numpy as np
import onnxruntime as ort

sys.path.insert(0, "/home/isoto/robotics/my_tests/lib")
from go2_robot import Go2Interface, interpolate


# ============================================================================
# CONFIG calibrada desde deploy.yaml
# ============================================================================
POLICY_PATH = "/home/isoto/robotics/rl_workspace/models/go2_velocity_v1/policy.onnx"

# step_dt del YAML = 0.02 -> 50 Hz
CONTROL_HZ = 50
DT = 1.0 / CONTROL_HZ

# Ganancias PD (orden SDK, NO orden politica)
# El YAML las da en orden politica [FL_hip, FL_thigh, FL_calf, FR..., RL..., RR...]
# Las reordenamos al orden SDK [FR..., FL..., RR..., RL...]
# joint_ids_map: [3,4,5, 0,1,2, 9,10,11, 6,7,8]
# Significa: idx_politica[i] = joint_ids_map[i] en el orden SDK.
# Equivalente: para reordenar de politica -> SDK, usar inversa.
JOINT_IDS_MAP = np.array([3, 4, 5, 0, 1, 2, 9, 10, 11, 6, 7, 8])
# JOINT_IDS_MAP[i] = indice SDK que corresponde a la posicion i en politica.
# Por tanto, para construir un vector en orden SDK a partir de uno politica:
#   v_sdk[JOINT_IDS_MAP[i]] = v_policy[i]   <=>   v_sdk = v_policy[inv_map]
INV_MAP = np.argsort(JOINT_IDS_MAP)  # politica -> SDK

# Ganancias en orden politica (del YAML)
KP_POLICY = np.array([20, 20, 40, 20, 20, 40, 20, 20, 40, 20, 20, 40], dtype=np.float32)
KD_POLICY = np.array([1,  1,  2,  1,  1,  2,  1,  1,  2,  1,  1,  2 ], dtype=np.float32)

# Postura nominal (offset de la accion) en orden politica
Q_DEFAULT_POLICY = np.array([
    -0.1, 0.9, -1.8,   # FL
     0.1, 0.9, -1.8,   # FR
    -0.1, 0.9, -1.8,   # RL
     0.1, 0.9, -1.8,   # RR
], dtype=np.float32)

# Escala de accion (del YAML, scale: [0.25 x 12])
ACTION_SCALE = 0.25

# Periodo del gait_phase (del YAML)
GAIT_PERIOD = 0.6

# Lo convertimos a orden SDK para enviar al go2_robot
KP_SDK = np.zeros(12, dtype=np.float32)
KD_SDK = np.zeros(12, dtype=np.float32)
Q_DEFAULT_SDK = np.zeros(12, dtype=np.float32)
for i_pol in range(12):
    i_sdk = JOINT_IDS_MAP[i_pol]
    KP_SDK[i_sdk] = KP_POLICY[i_pol]
    KD_SDK[i_sdk] = KD_POLICY[i_pol]
    Q_DEFAULT_SDK[i_sdk] = Q_DEFAULT_POLICY[i_pol]


def quat_rotate_inverse(q, v):
    """Rota v por el inverso del cuaternion q (formato w, x, y, z).
    Usado para proyectar la gravedad del mundo al body frame."""
    w, x, y, z = q
    q_vec = np.array([x, y, z], dtype=np.float64)
    a = v * (2.0 * w * w - 1.0)
    b = np.cross(q_vec, v) * (2.0 * w)
    c = q_vec * (np.dot(q_vec, v) * 2.0)
    return (a - b + c).astype(np.float32)


def build_observation(robot, last_action_policy, vx_cmd, vy_cmd, wz_cmd, t_phase):
    """Construye el vector de observacion en orden POLITICA."""
    st = robot.read_state()

    # IMU
    quat = np.array(st.imu_state.quaternion, dtype=np.float32)
    ang_vel = np.array(st.imu_state.gyroscope, dtype=np.float32)

    # Gravedad proyectada al body frame
    gravity_world = np.array([0.0, 0.0, -1.0], dtype=np.float32)
    projected_gravity = quat_rotate_inverse(quat, gravity_world)

    # Joint state en orden SDK -> reordenar a orden politica
    q_sdk = np.array([st.motor_state[i].q for i in range(12)], dtype=np.float32)
    dq_sdk = np.array([st.motor_state[i].dq for i in range(12)], dtype=np.float32)
    q_pol = q_sdk[JOINT_IDS_MAP]    # v_pol[i] = v_sdk[JOINT_IDS_MAP[i]]
    dq_pol = dq_sdk[JOINT_IDS_MAP]
    joint_pos_rel = q_pol - Q_DEFAULT_POLICY

    # Comandos
    cmd = np.array([vx_cmd, vy_cmd, wz_cmd], dtype=np.float32)

    # Gait phase (sin, cos)
    phase = 2.0 * math.pi * t_phase / GAIT_PERIOD
    gait_phase = np.array([math.sin(phase), math.cos(phase)], dtype=np.float32)

    # Concatenar (orden segun deploy.yaml)
    obs = np.concatenate([
        ang_vel,            # 3
        projected_gravity,  # 3
        cmd,                # 3
        gait_phase,         # 2
        joint_pos_rel,      # 12
        dq_pol,             # 12  (joint_vel_rel = vel ya que default vel = 0)
        last_action_policy, # 12
    ]).astype(np.float32)

    return obs


def main():
    robot = Go2Interface(domain_id=1, interface="lo")

    # ----- Pre-stand: ir suavemente a Q_DEFAULT_SDK -----
    print("[INFO] Llevando el robot a postura nominal...")
    q_now = robot.read_joint_positions()
    n_ramp = int(2.5 * CONTROL_HZ)
    for i in range(n_ramp):
        alpha = (i + 1) / n_ramp
        q = interpolate(q_now, Q_DEFAULT_SDK, alpha)
        robot.send_joint_targets(q, kp=60.0, kd=5.0)
        time.sleep(DT)

    # ----- Estabilizacion con kp/kd de la politica -----
    print("[INFO] Transicion a ganancias de la politica...")
    for _ in range(int(1.0 * CONTROL_HZ)):
        robot.send_joint_targets(Q_DEFAULT_SDK, kp=KP_SDK, kd=KD_SDK)
        time.sleep(DT)

    # ----- Cargar politica -----
    print(f"[INFO] Cargando: {POLICY_PATH}")
    sess = ort.InferenceSession(POLICY_PATH, providers=["CPUExecutionProvider"])
    in_name = sess.get_inputs()[0].name
    out_name = sess.get_outputs()[0].name
    in_shape = sess.get_inputs()[0].shape
    out_shape = sess.get_outputs()[0].shape
    print(f"[INFO] Input  {in_name}: {in_shape}")
    print(f"[INFO] Output {out_name}: {out_shape}")
    print(f"[INFO] Mi obs sera de {3+3+3+2+12+12+12}=47 dims. La red espera {in_shape}.")
    print("       Si no coinciden, revisar build_observation.")

    # ----- Bucle de inferencia -----
    last_action_policy = np.zeros(12, dtype=np.float32)
    vx_cmd, vy_cmd, wz_cmd = 0.0, 0.0, 0.0  # arrancamos parados

    print("\n[INFO] Politica activa. Comando inicial = (0,0,0).")
    print("       A los 5s el robot empezara a andar hacia delante a 0.3 m/s.")
    print("       Ctrl+C para parar.\n")

    t0 = time.time()
    try:
        while True:
            loop_start = time.time()
            t = time.time() - t0

            # Curriculum simple de comandos
            if t > 5.0:
                vx_cmd = 0.3

            # Observacion
            obs = build_observation(robot, last_action_policy,
                                     vx_cmd, vy_cmd, wz_cmd, t)
            obs_batch = obs[np.newaxis, :]

            # Inferencia
            action_policy = sess.run([out_name], {in_name: obs_batch})[0][0]
            last_action_policy = action_policy.copy()

            # q_target = offset + action * scale, en orden POLITICA
            q_target_pol = Q_DEFAULT_POLICY + action_policy * ACTION_SCALE

            # Reordenar a SDK para enviar
            q_target_sdk = np.zeros(12, dtype=np.float32)
            for i_pol in range(12):
                q_target_sdk[JOINT_IDS_MAP[i_pol]] = q_target_pol[i_pol]

            robot.send_joint_targets(q_target_sdk, kp=KP_SDK, kd=KD_SDK)

            # Mantener frecuencia
            elapsed = time.time() - loop_start
            if elapsed < DT:
                time.sleep(DT - elapsed)

    except KeyboardInterrupt:
        print("\n[INFO] Parando -> damping...")
        for _ in range(int(1.5 * CONTROL_HZ)):
            robot.send_damping(kd=2.0)
            time.sleep(DT)
        print("[INFO] Hecho.")


if __name__ == "__main__":
    main()
