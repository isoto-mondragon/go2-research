#!/usr/bin/env python3
"""Run the Go2 ONNX policy against unitree_mujoco's Python simulator.

This bypasses the C++ deploy binary, which is currently crashing in
ChannelFactory/RealTimePublisher on this WSL setup.
"""

from __future__ import annotations

import argparse
import math
import sys
import threading
import time
from pathlib import Path

import numpy as np
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ROBOTICS_ROOT = PROJECT_ROOT.parents[1]
SDK2_PYTHON = ROBOTICS_ROOT / "unitree_sdk2_python"
if SDK2_PYTHON.exists():
    sys.path.insert(0, str(SDK2_PYTHON))

try:
    import onnxruntime as ort
except ImportError as exc:
    raise SystemExit(
        "Falta onnxruntime en este entorno. Instala con:\n"
        "  pip install onnxruntime\n"
    ) from exc

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.core.channel import ChannelPublisher, ChannelSubscriber
from unitree_sdk2py.idl.default import unitree_go_msg_dds__LowCmd_
from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowCmd_, LowState_
from unitree_sdk2py.utils.crc import CRC


POS_STOP_F = 2.146e9
VEL_STOP_F = 16000.0


def quat_projected_gravity(quat_wxyz: np.ndarray) -> np.ndarray:
    """Rotate world gravity into body frame using q inverse."""
    w, x, y, z = quat_wxyz.astype(np.float32)
    # Rotation matrix transpose times [0, 0, -1].
    return np.array(
        [
            2.0 * (x * z - w * y),
            2.0 * (y * z + w * x),
            1.0 - 2.0 * (x * x + y * y),
        ],
        dtype=np.float32,
    ) * -1.0


class Go2OnnxController:
    def __init__(self, policy_dir: Path, network: str, stand_seconds: float) -> None:
        self.policy_dir = policy_dir
        self.network = network
        self.stand_seconds = stand_seconds
        self.cfg = yaml.safe_load((policy_dir / "params" / "deploy.yaml").read_text())

        self.joint_ids_map = np.asarray(self.cfg["joint_ids_map"], dtype=np.int64)
        self.step_dt = float(self.cfg["step_dt"])
        self.kp = np.asarray(self.cfg["stiffness"], dtype=np.float32)
        self.kd = np.asarray(self.cfg["damping"], dtype=np.float32)
        self.default_q = np.asarray(self.cfg["default_joint_pos"], dtype=np.float32)
        action_cfg = self.cfg["actions"]["JointPositionAction"]
        self.action_scale = np.asarray(action_cfg["scale"], dtype=np.float32)
        self.action_offset = np.asarray(action_cfg["offset"], dtype=np.float32)
        self.period = float(self.cfg["observations"]["gait_phase"]["params"]["period"])

        self.session = ort.InferenceSession(
            str(policy_dir / "exported" / "policy.onnx"),
            providers=["CPUExecutionProvider"],
        )
        self.input_names = [item.name for item in self.session.get_inputs()]
        self.output_name = self.session.get_outputs()[0].name

        self.low_cmd = unitree_go_msg_dds__LowCmd_()
        self.low_state: LowState_ | None = None
        self.state_lock = threading.Lock()
        self.crc = CRC()
        self.last_action = np.zeros(12, dtype=np.float32)
        self.phase = 0.0
        self.start_time = time.monotonic()
        self.last_cmd_time = self.start_time
        self.vx_cmd = 0.0
        self.wz_cmd = 0.0

    def init_dds(self) -> None:
        ChannelFactoryInitialize(0, self.network)
        self.publisher = ChannelPublisher("rt/lowcmd", LowCmd_)
        self.publisher.Init()
        self.subscriber = ChannelSubscriber("rt/lowstate", LowState_)
        self.subscriber.Init(self._low_state_handler, 10)
        self._init_low_cmd()

    def _init_low_cmd(self) -> None:
        self.low_cmd.head[0] = 0xFE
        self.low_cmd.head[1] = 0xEF
        self.low_cmd.level_flag = 0xFF
        self.low_cmd.gpio = 0
        for i in range(20):
            motor = self.low_cmd.motor_cmd[i]
            motor.mode = 0x01
            motor.q = POS_STOP_F
            motor.dq = VEL_STOP_F
            motor.kp = 0.0
            motor.kd = 0.0
            motor.tau = 0.0

    def _low_state_handler(self, msg: LowState_) -> None:
        with self.state_lock:
            self.low_state = msg

    def _state_snapshot(self) -> LowState_ | None:
        with self.state_lock:
            return self.low_state

    def wait_for_state(self) -> None:
        print("[py_ctrl] Esperando LowState del simulador...")
        while self._state_snapshot() is None:
            time.sleep(0.05)
        print("[py_ctrl] LowState recibido.")

    def _policy_order_q_dq(self, state: LowState_) -> tuple[np.ndarray, np.ndarray]:
        q = np.asarray([state.motor_state[i].q for i in self.joint_ids_map], dtype=np.float32)
        dq = np.asarray([state.motor_state[i].dq for i in self.joint_ids_map], dtype=np.float32)
        return q, dq

    def _velocity_command(self) -> np.ndarray:
        t = time.monotonic() - self.start_time
        vx_target = 0.0
        wz_target = 0.0
        if 5.0 <= t < 25.0:
            vx_target = 0.2
        elif 25.0 <= t < 45.0:
            wz_target = 0.3

        now = time.monotonic()
        dt = now - self.last_cmd_time
        self.last_cmd_time = now
        alpha = max(0.0, min(dt / 1.0, 1.0))
        self.vx_cmd += alpha * (vx_target - self.vx_cmd)
        self.wz_cmd += alpha * (wz_target - self.wz_cmd)
        return np.asarray([self.vx_cmd, 0.0, self.wz_cmd], dtype=np.float32)

    def _obs(self, state: LowState_) -> np.ndarray:
        q, dq = self._policy_order_q_dq(state)
        command = self._velocity_command()
        self.phase = (self.phase + self.step_dt / self.period) % 1.0
        gait = np.asarray(
            [math.sin(self.phase * 2.0 * math.pi), math.cos(self.phase * 2.0 * math.pi)],
            dtype=np.float32,
        )
        if np.linalg.norm(command) < 0.1:
            gait[:] = 0.0

        obs_terms = [
            np.asarray(state.imu_state.gyroscope, dtype=np.float32),
            quat_projected_gravity(np.asarray(state.imu_state.quaternion, dtype=np.float32)),
            command,
            gait,
            q - self.default_q,
            dq,
            self.last_action,
        ]
        return np.concatenate(obs_terms).astype(np.float32)[None, :]

    def _run_policy(self, obs: np.ndarray) -> np.ndarray:
        if len(self.input_names) == 1:
            feeds = {self.input_names[0]: obs}
        else:
            # The mjlab export normally has one "obs" input. This fallback keeps
            # the error readable if a future policy is exported differently.
            raise RuntimeError(f"ONNX con entradas no soportadas: {self.input_names}")
        action = self.session.run([self.output_name], feeds)[0]
        return np.asarray(action, dtype=np.float32).reshape(-1)[:12]

    def _publish_targets(self, targets_policy_order: np.ndarray) -> None:
        for policy_i, motor_i in enumerate(self.joint_ids_map):
            motor = self.low_cmd.motor_cmd[int(motor_i)]
            motor.mode = 0x01
            motor.q = float(targets_policy_order[policy_i])
            motor.dq = 0.0
            motor.kp = float(self.kp[policy_i])
            motor.kd = float(self.kd[policy_i])
            motor.tau = 0.0

        self.low_cmd.crc = self.crc.Crc(self.low_cmd)
        self.publisher.Write(self.low_cmd)

    def stand_up(self) -> None:
        state = self._state_snapshot()
        assert state is not None
        q0, _ = self._policy_order_q_dq(state)
        print(f"[py_ctrl] Stand-up suave durante {self.stand_seconds:.1f}s...")
        t0 = time.monotonic()
        while True:
            state = self._state_snapshot()
            if state is None:
                continue
            elapsed = time.monotonic() - t0
            phase = min(elapsed / self.stand_seconds, 1.0)
            # Smoothstep.
            phase = phase * phase * (3.0 - 2.0 * phase)
            target = (1.0 - phase) * q0 + phase * self.default_q
            self._publish_targets(target.astype(np.float32))
            if elapsed >= self.stand_seconds:
                break
            time.sleep(0.002)
        print("[py_ctrl] Stand-up terminado. Arrancando policy ONNX.")

    def run_policy_loop(self) -> None:
        next_tick = time.monotonic()
        tick = 0
        while True:
            state = self._state_snapshot()
            if state is None:
                time.sleep(0.01)
                continue
            obs = self._obs(state)
            raw_action = self._run_policy(obs)
            self.last_action = raw_action
            target = raw_action * self.action_scale + self.action_offset
            self._publish_targets(target.astype(np.float32))
            if tick % 100 == 0:
                cmd = self._velocity_command()
                print(f"[py_ctrl] t={time.monotonic() - self.start_time:5.1f}s cmd={cmd}")
            tick += 1
            next_tick += self.step_dt
            time.sleep(max(0.0, next_tick - time.monotonic()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--network", default="lo")
    parser.add_argument(
        "--policy-dir",
        default=str(Path(__file__).resolve().parent / "config" / "policy" / "velocity" / "v0"),
    )
    parser.add_argument("--stand-seconds", type=float, default=3.0)
    args = parser.parse_args()

    controller = Go2OnnxController(Path(args.policy_dir), args.network, args.stand_seconds)
    controller.init_dds()
    controller.wait_for_state()
    controller.stand_up()
    controller.run_policy_loop()


if __name__ == "__main__":
    main()
