"""
go2_robot.py
Wrapper que encapsula la comunicación DDS con unitree_mujoco (o robot real).
Expone una API simple: send_joint_targets(...) y read_state().

Diseño:
- Inicializa DDS una sola vez por proceso.
- Mantiene un thread suscriptor de rt/lowstate que actualiza self.state.
- send_joint_targets() construye el LowCmd_, calcula CRC y lo publica.
"""
import time
import threading
import numpy as np

from unitree_sdk2py.core.channel import (
    ChannelPublisher, ChannelSubscriber, ChannelFactoryInitialize,
)
from unitree_sdk2py.idl.default import unitree_go_msg_dds__LowCmd_
from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowCmd_, LowState_
from unitree_sdk2py.utils.crc import CRC


# ---- Convenciones del Go2 -------------------------------------------------
# 12 motores, ordenados como en el SDK de Unitree:
# Pata: FR=0, FL=1, RR=2, RL=3
# Tipo:  hip=0, thigh=1, calf=2
# Indice global = pata*3 + tipo
JOINT_NAMES = [
    "FR_hip", "FR_thigh", "FR_calf",
    "FL_hip", "FL_thigh", "FL_calf",
    "RR_hip", "RR_thigh", "RR_calf",
    "RL_hip", "RL_thigh", "RL_calf",
]

# Posturas de referencia (radianes)
LIE_POSE = np.array([
    0.0,  1.30, -2.70,
    0.0,  1.30, -2.70,
    0.0,  1.30, -2.70,
    0.0,  1.30, -2.70,
])

STAND_POSE = np.array([
     0.0,  0.67, -1.30,   # FR
     0.0,  0.67, -1.30,   # FL
     0.0,  0.67, -1.30,   # RR
     0.0,  0.67, -1.30,   # RL
])

class Go2Interface:
    """
    Wrapper alrededor del DDS de Unitree para hablar con el Go2 (sim o real).
    """

    def __init__(self, domain_id=1, interface="lo"):
        """
        domain_id=1, interface="lo"  -> simulador unitree_mujoco
        domain_id=0, interface="eth0" (o el nombre real) -> robot fisico
        """
        print(f"[Go2Interface] Inicializando DDS dom={domain_id} iface={interface}")
        ChannelFactoryInitialize(domain_id, interface)

        # Publisher de comandos
        self._pub = ChannelPublisher("rt/lowcmd", LowCmd_)
        self._pub.Init()

        # Subscriber de estado
        self._state_lock = threading.Lock()
        self._latest_state = None
        self._sub = ChannelSubscriber("rt/lowstate", LowState_)
        self._sub.Init(self._on_state, 10)

        # Estructura del comando (rellena entre publicaciones)
        self._cmd = unitree_go_msg_dds__LowCmd_()
        self._cmd.head = [0xFE, 0xEF]
        self._cmd.level_flag = 0xFF
        self._cmd.gpio = 0
        for i in range(20):
            self._cmd.motor_cmd[i].mode = 0x01

        self._crc = CRC()

        # Espera a recibir el primer estado (asi sabemos que la conexion va)
        print("[Go2Interface] Esperando primer mensaje de estado...")
        t0 = time.time()
        while self._latest_state is None:
            if time.time() - t0 > 5.0:
                raise RuntimeError(
                    "No se recibe rt/lowstate en 5 s. "
                    "¿Esta el simulador en marcha y el domain_id coincide?"
                )
            time.sleep(0.05)
        print("[Go2Interface] Conexion establecida.")

    def _on_state(self, msg: LowState_):
        with self._state_lock:
            self._latest_state = msg

    def read_state(self):
        """Devuelve el ultimo LowState_ recibido (None si aun no hay)."""
        with self._state_lock:
            return self._latest_state

    def read_joint_positions(self):
        """Devuelve un array (12,) con las posiciones articulares actuales."""
        st = self.read_state()
        if st is None:
            return None
        return np.array([st.motor_state[j].q for j in range(12)])

    def read_joint_velocities(self):
        """Devuelve un array (12,) con las velocidades articulares."""
        st = self.read_state()
        if st is None:
            return None
        return np.array([st.motor_state[j].dq for j in range(12)])

    def read_imu(self):
        """Devuelve (quat, gyro, accel) del IMU del robot."""
        st = self.read_state()
        if st is None:
            return None
        imu = st.imu_state
        return (
            np.array(imu.quaternion),   # [w, x, y, z]
            np.array(imu.gyroscope),    # rad/s
            np.array(imu.accelerometer) # m/s^2
        )

    def send_joint_targets(self, q_target, kp=60.0, kd=5.0, tau_ff=None):
        """
        Envia un comando a los 12 motores con control PD por articulacion.

        Parametros:
          q_target: array de 12 posiciones objetivo (rad)
          kp, kd:   ganancias PD (escalar para todos, o array de 12)
          tau_ff:   par feedforward opcional (array de 12), util para
                    compensar gravedad o anhadir control torque-based
        """
        q_target = np.asarray(q_target, dtype=float)
        assert q_target.shape == (12,), "q_target debe tener 12 elementos"

        # Permite pasar kp/kd como escalar o array
        kp_arr = np.full(12, kp) if np.isscalar(kp) else np.asarray(kp)
        kd_arr = np.full(12, kd) if np.isscalar(kd) else np.asarray(kd)
        tau_arr = np.zeros(12) if tau_ff is None else np.asarray(tau_ff)

        for j in range(12):
            self._cmd.motor_cmd[j].q = float(q_target[j])
            self._cmd.motor_cmd[j].dq = 0.0
            self._cmd.motor_cmd[j].kp = float(kp_arr[j])
            self._cmd.motor_cmd[j].kd = float(kd_arr[j])
            self._cmd.motor_cmd[j].tau = float(tau_arr[j])

        self._cmd.crc = self._crc.Crc(self._cmd)
        self._pub.Write(self._cmd)

    def send_damping(self, kd=2.0):
        """
        Comando 'seguro' que solo aplica amortiguamiento (sin posicion target).
        Util para terminar el script sin que el robot se desplome bruscamente.
        """
        for j in range(12):
            self._cmd.motor_cmd[j].q = 0.0
            self._cmd.motor_cmd[j].dq = 0.0
            self._cmd.motor_cmd[j].kp = 0.0
            self._cmd.motor_cmd[j].kd = float(kd)
            self._cmd.motor_cmd[j].tau = 0.0
        self._cmd.crc = self._crc.Crc(self._cmd)
        self._pub.Write(self._cmd)


def interpolate(q_start, q_end, alpha):
    """Interpolacion lineal entre dos posturas. alpha en [0, 1]."""
    return (1.0 - alpha) * np.asarray(q_start) + alpha * np.asarray(q_end)
