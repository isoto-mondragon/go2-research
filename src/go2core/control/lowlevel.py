"""Capa de bajo nivel DDS del Go2: rt/lowstate y rt/lowcmd.

Esta clase es la unica que toca LowCmd. Encapsula lo que valida
tools/check_write_path.py y le anade lo que el robot real exige:

  - reemision del ultimo objetivo a frecuencia constante (500 Hz por defecto)
    en un hilo aparte, para que la politica pueda correr a 50 Hz sin que el
    firmware se quede sin comandos entre pasos
  - watchdog sobre lowstate
  - clamp de posicion respecto a una referencia
  - deteccion de inclinacion excesiva
  - limite de par POR ARTICULACION con disparo por saturacion SOSTENIDA
  - paso a amortiguacion (passive) garantizado al salir, incluso con Ctrl-C

SOBRE EL LIMITE DE PAR
----------------------
En el Go2 la rodilla lleva una reduccion extra y aguanta casi el doble que la
cadera y el muslo, asi que un umbral escalar es siempre o demasiado laxo para
la cadera o demasiado estricto para la rodilla.

Ademas, saturar el actuador de forma transitoria NO es una averia: levantarse
desde el suelo satura la rodilla unas decenas de milisegundos y eso es
funcionamiento normal. Lo que indica un problema es la saturacion SOSTENIDA:
una articulacion pegada a su tope durante medio segundo esta peleando contra
algo que no cede. Por eso el disparo mide duracion, no valor instantaneo.

Funciona igual contra unitree_mujoco (domain 1, "lo") y contra el robot fisico
(domain 0, interfaz Ethernet).
"""

from __future__ import annotations

import threading
import time

import numpy as np

from unitree_sdk2py.core.channel import (
    ChannelFactoryInitialize,
    ChannelPublisher,
    ChannelSubscriber,
)
from unitree_sdk2py.idl.default import unitree_go_msg_dds__LowCmd_
from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowCmd_, LowState_
from unitree_sdk2py.utils.crc import CRC

N_JOINTS = 12
N_MOTOR_SLOTS = 20
POS_STOP_F = 2.146e9
VEL_STOP_F = 16000.0


class SafetyTrip(RuntimeError):
    """Se ha violado un limite de seguridad. El llamante debe ir a passive."""


class LowLevel:
    """Interfaz DDS de bajo nivel con el Go2 (simulado o real).

    Todos los vectores de 12 que entran y salen de esta clase estan en
    ORDEN MOTOR (FR, FL, RR, RL).
    """

    def __init__(self, contract: dict, mode: str = "sim",
                 iface: str | None = None, domain: int | None = None) -> None:
        if mode not in ("sim", "real"):
            raise ValueError("mode debe ser 'sim' o 'real'")
        dds = contract["dds"][mode]
        self.mode = mode
        self.iface = iface or dds["interface"]
        self.domain = domain if domain is not None else dds["domain_id"]

        self.c = contract
        self.names = contract["joint_order"]
        self.motor_mode = int(contract.get("motor_mode", 1))

        s = contract["safety"]
        limits = s.get("tau_limits") or [float(s.get("tau_max", 33.0))] * N_JOINTS
        self.tau_limits = np.asarray(limits, dtype=np.float32)
        self.tau_sat_frac = float(s.get("tau_saturation_frac", 0.98))
        self.tau_sustained_s = float(s.get("tau_sustained_ms", 500)) / 1000.0
        self.q_delta_max = float(s["q_delta_max"])
        self.watchdog_s = float(s["watchdog_ms"]) / 1000.0
        self.max_tilt_rad = float(s["max_tilt_rad"])
        self.publish_dt = 1.0 / float(contract["policy"]["publish_hz"])

        # Se puede desactivar en simulacion para poder observar que pasa
        # DESPUES del instante en que normalmente se abortaria.
        self.torque_trip = True

        self._state: LowState_ | None = None
        self._state_t = 0.0
        self._state_lock = threading.Lock()

        self._target = np.zeros(N_JOINTS, dtype=np.float32)
        self._kp = np.zeros(N_JOINTS, dtype=np.float32)
        self._kd = np.zeros(N_JOINTS, dtype=np.float32)
        self._cmd_lock = threading.Lock()

        self._crc = CRC()
        self._cmd = unitree_go_msg_dds__LowCmd_()
        self._pub_thread: threading.Thread | None = None
        self._running = False
        self.published = 0

        # Diagnostico acumulado
        self.tau_peak = np.zeros(N_JOINTS, dtype=np.float32)
        self.sat_time = np.zeros(N_JOINTS, dtype=np.float32)   # segundos saturada
        self._sat_since = np.full(N_JOINTS, np.nan, dtype=np.float64)
        self._last_check = None

    # -- ciclo de vida ----------------------------------------------------
    def start(self, wait_state_s: float = 5.0) -> None:
        ChannelFactoryInitialize(self.domain, self.iface)

        self._sub = ChannelSubscriber("rt/lowstate", LowState_)
        self._sub.Init(self._on_state, 10)

        self._pub = ChannelPublisher("rt/lowcmd", LowCmd_)
        self._pub.Init()
        self._init_cmd()

        t0 = time.monotonic()
        while self.state() is None and time.monotonic() - t0 < wait_state_s:
            time.sleep(0.02)
        if self.state() is None:
            raise RuntimeError(
                f"No llega rt/lowstate en domain {self.domain} por '{self.iface}'. "
                "Comprueba que el simulador o el robot estan activos."
            )

        self.go_passive()
        self._running = True
        self._pub_thread = threading.Thread(target=self._publish_loop, daemon=True)
        self._pub_thread.start()

    def stop(self, damping_s: float = 0.5) -> None:
        if self._running:
            try:
                self.go_passive()
                time.sleep(damping_s)
            except Exception:
                pass
        self._running = False
        if self._pub_thread is not None:
            self._pub_thread.join(timeout=1.0)

    def __enter__(self) -> "LowLevel":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    # -- estado -----------------------------------------------------------
    def _on_state(self, msg: LowState_) -> None:
        with self._state_lock:
            self._state = msg
            self._state_t = time.monotonic()

    def state(self) -> LowState_ | None:
        with self._state_lock:
            return self._state

    def state_age_s(self) -> float:
        with self._state_lock:
            return float("inf") if self._state is None else time.monotonic() - self._state_t

    def joint_q(self) -> np.ndarray:
        st = self.state()
        return np.asarray([st.motor_state[i].q for i in range(N_JOINTS)], dtype=np.float32)

    def joint_dq(self) -> np.ndarray:
        st = self.state()
        return np.asarray([st.motor_state[i].dq for i in range(N_JOINTS)], dtype=np.float32)

    def joint_tau(self) -> np.ndarray:
        st = self.state()
        return np.asarray(
            [getattr(st.motor_state[i], "tau_est", 0.0) for i in range(N_JOINTS)],
            dtype=np.float32,
        )

    def gyro(self) -> np.ndarray:
        return np.asarray(self.state().imu_state.gyroscope, dtype=np.float32)

    def quaternion(self) -> np.ndarray:
        return np.asarray(self.state().imu_state.quaternion, dtype=np.float32)

    def projected_gravity(self) -> np.ndarray:
        """Gravedad mundial rotada al sistema del cuerpo. Robot plano: [0,0,-1]."""
        w, x, y, z = self.quaternion()
        return -np.asarray([
            2.0 * (x * z - w * y),
            2.0 * (y * z + w * x),
            1.0 - 2.0 * (x * x + y * y),
        ], dtype=np.float32)

    def tilt_rad(self) -> float:
        gz = float(np.clip(-self.projected_gravity()[2], -1.0, 1.0))
        return float(np.arccos(gz))

    def height_proxy(self) -> float:
        """Altura relativa del tronco estimada desde la geometria de las patas.

        No hay odometria fiable en lowstate, asi que se usa la extension media
        de las patas como indicador de si el robot esta erguido o tumbado.
        Tumbado ronda 0.1, de pie ronda 0.3.
        """
        q = self.joint_q()
        thigh = q[[1, 4, 7, 10]]
        calf = q[[2, 5, 8, 11]]
        # Cinematica plana aproximada del Go2: femur y tibia de 0.213 m.
        return float(np.mean(0.213 * np.cos(thigh) + 0.213 * np.cos(thigh + calf)))

    # -- comandos ---------------------------------------------------------
    def _init_cmd(self) -> None:
        self._cmd.head[0], self._cmd.head[1] = 0xFE, 0xEF
        self._cmd.level_flag = 0xFF
        self._cmd.gpio = 0
        for i in range(N_MOTOR_SLOTS):
            m = self._cmd.motor_cmd[i]
            m.mode = self.motor_mode
            m.q, m.dq = POS_STOP_F, VEL_STOP_F
            m.kp = m.kd = m.tau = 0.0

    def set_command(self, q_target, kp, kd) -> None:
        q = np.asarray(q_target, dtype=np.float32)
        kp = np.asarray(kp, dtype=np.float32)
        kd = np.asarray(kd, dtype=np.float32)
        for name, v in (("q_target", q), ("kp", kp), ("kd", kd)):
            if v.shape != (N_JOINTS,):
                raise ValueError(f"{name} debe tener {N_JOINTS} elementos, tiene {v.shape}")
        with self._cmd_lock:
            self._target, self._kp, self._kd = q, kp, kd

    def set_command_clamped(self, q_target, kp, kd, reference) -> np.ndarray:
        q = np.asarray(q_target, dtype=np.float32)
        ref = np.asarray(reference, dtype=np.float32)
        q_c = np.clip(q, ref - self.q_delta_max, ref + self.q_delta_max)
        self.set_command(q_c, kp, kd)
        return q_c

    def go_passive(self) -> None:
        kd = np.asarray(self.c["fsm"]["gains"]["passive"]["kd"], dtype=np.float32)
        st = self.state()
        q = self.joint_q() if st is not None else np.zeros(N_JOINTS, dtype=np.float32)
        self.set_command(q, np.zeros(N_JOINTS, dtype=np.float32), kd)

    def _publish_loop(self) -> None:
        next_t = time.monotonic()
        while self._running:
            with self._cmd_lock:
                q, kp, kd = self._target, self._kp, self._kd
            for i in range(N_JOINTS):
                m = self._cmd.motor_cmd[i]
                m.mode = self.motor_mode
                m.q = float(q[i])
                m.dq = 0.0
                m.kp = float(kp[i])
                m.kd = float(kd[i])
                m.tau = 0.0
            self._cmd.crc = self._crc.Crc(self._cmd)
            self._pub.Write(self._cmd)
            self.published += 1
            next_t += self.publish_dt
            time.sleep(max(0.0, next_t - time.monotonic()))

    # -- seguridad --------------------------------------------------------
    def check_safety(self, check_tilt: bool = True, transient: bool = False) -> None:
        """Lanza SafetyTrip si algo se ha salido de rango.

        Args:
            check_tilt: desactivar durante las rampas del FSM, donde el tronco
                puede estar legitimamente inclinado.
            transient: se acepta por compatibilidad. El disparo por par ya
                distingue transitorio de sostenido por si mismo.
        """
        now = time.monotonic()

        age = self.state_age_s()
        if age > self.watchdog_s:
            raise SafetyTrip(f"watchdog: lowstate lleva {age * 1000:.0f} ms sin llegar")

        tau = np.abs(self.joint_tau())
        self.tau_peak = np.maximum(self.tau_peak, tau)

        sat = tau >= self.tau_limits * self.tau_sat_frac
        dt = 0.0 if self._last_check is None else now - self._last_check
        self._last_check = now
        self.sat_time += sat * dt

        self._sat_since = np.where(sat & np.isnan(self._sat_since), now, self._sat_since)
        self._sat_since = np.where(sat, self._sat_since, np.nan)

        if self.torque_trip:
            dur = np.where(np.isnan(self._sat_since), 0.0, now - self._sat_since)
            bad = dur > self.tau_sustained_s
            if bad.any():
                j = int(np.argmax(dur))
                raise SafetyTrip(
                    f"saturacion sostenida en {self.names[j]}: {tau[j]:.1f} Nm "
                    f"(limite {self.tau_limits[j]:.1f}) durante {dur[j] * 1000:.0f} ms. "
                    f"Error de posicion: "
                    f"{abs(float(self._target[j] - self.joint_q()[j])):.3f} rad. "
                    "Esa articulacion esta peleando contra algo que no cede."
                )

        if check_tilt:
            tilt = self.tilt_rad()
            if tilt > self.max_tilt_rad:
                raise SafetyTrip(f"inclinacion {np.degrees(tilt):.0f} deg supera el limite")

    def tau_table(self) -> str:
        """Tabla por articulacion: par actual, pico, limite y tiempo saturada."""
        tau = np.abs(self.joint_tau())
        q = self.joint_q()
        lines = [f"  {'articulacion':<10} {'tau':>7} {'pico':>7} {'limite':>7} "
                 f"{'%lim':>6} {'sat(s)':>7} {'q':>8} {'objetivo':>9}"]
        for i, n in enumerate(self.names):
            pct = 100.0 * tau[i] / self.tau_limits[i]
            flag = " <<<" if pct >= 98 else ""
            lines.append(
                f"  {n:<10} {tau[i]:7.2f} {self.tau_peak[i]:7.2f} "
                f"{self.tau_limits[i]:7.2f} {pct:5.0f}% {self.sat_time[i]:7.2f} "
                f"{q[i]:8.3f} {self._target[i]:9.3f}{flag}"
            )
        return "\n".join(lines)

    def summary(self) -> str:
        if self.state() is None:
            return "sin lowstate"
        return (
            f"modo={self.mode} domain={self.domain} iface={self.iface} | "
            f"lowstate hace {self.state_age_s() * 1000:.0f} ms | "
            f"inclinacion {np.degrees(self.tilt_rad()):.1f} deg | "
            f"altura ~{self.height_proxy():.3f} m | "
            f"tau max {np.abs(self.joint_tau()).max():.1f} Nm | "
            f"lowcmd enviados {self.published}"
        )
