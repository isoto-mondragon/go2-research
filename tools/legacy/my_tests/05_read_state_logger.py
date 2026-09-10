"""05_read_state_logger.py — Logger fiable que graba duracion exacta."""
import sys, time
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, "/home/isoto/robotics/my_tests/lib")
from go2_robot import Go2Interface, JOINT_NAMES

DURATION_S = 10.0
RATE_HZ = 100


def main():
    robot = Go2Interface(domain_id=1, interface="lo")

    print(f"[INFO] Grabando {DURATION_S} s a {RATE_HZ} Hz...")
    print("[INFO] Lanza otro script en otra pestana para ver movimiento.")

    times, q_log, dq_log, tau_log = [], [], [], []
    t0 = time.monotonic()
    next_t = t0

    while True:
        now = time.monotonic()
        elapsed = now - t0
        if elapsed >= DURATION_S:
            break

        st = robot.read_state()
        if st is not None:
            q  = np.array([st.motor_state[j].q       for j in range(12)])
            dq = np.array([st.motor_state[j].dq      for j in range(12)])
            tau = np.array([st.motor_state[j].tau_est for j in range(12)])
            times.append(elapsed)
            q_log.append(q)
            dq_log.append(dq)
            tau_log.append(tau)

        # Reloj que NO acumula deriva
        next_t += 1.0 / RATE_HZ
        sleep_t = next_t - time.monotonic()
        if sleep_t > 0:
            time.sleep(sleep_t)

    print(f"[INFO] {len(times)} muestras grabadas.")

    times = np.array(times)
    q_log = np.array(q_log)
    dq_log = np.array(dq_log)
    tau_log = np.array(tau_log)

    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
    for j in range(12):
        axes[0].plot(times, q_log[:, j],   label=JOINT_NAMES[j])
        axes[1].plot(times, dq_log[:, j])
        axes[2].plot(times, tau_log[:, j])
    axes[0].set_ylabel("q (rad)")
    axes[1].set_ylabel("dq (rad/s)")
    axes[2].set_ylabel("tau_est (Nm)")
    axes[2].set_xlabel("t (s)")
    axes[0].legend(ncol=4, fontsize=7, loc="upper right")
    axes[0].set_title("Estado articular del Go2")
    # Lineas de referencia para limites del Go2 real
    axes[1].axhline(+30, color="r", ls="--", lw=0.5, label="vel max")
    axes[1].axhline(-30, color="r", ls="--", lw=0.5)
    axes[2].axhline(+24, color="r", ls="--", lw=0.5, label="tau max hip/thigh")
    axes[2].axhline(-24, color="r", ls="--", lw=0.5)
    plt.tight_layout()
    plt.savefig("/home/isoto/robotics/my_tests/state_log.png", dpi=120)
    print("[INFO] Grafica guardada en state_log.png")


if __name__ == "__main__":
    main()