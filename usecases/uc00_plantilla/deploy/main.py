#!/usr/bin/env python3
# =============================================================================
# ESTE FICHERO NO SE TOCA.
# Tu codigo va en mi_caso.py, en la carpeta de arriba (uc00_plantilla/).
# =============================================================================
"""usecases/uc00_plantilla/deploy/main.py

La maquinaria de la plantilla. Lee `decidir()` de ../mi_caso.py y se ocupa de
todo lo demas.

    telemetria ──► decidir() ──► limitador ──► (vx, vy, wz) ──► robot
                   mi_caso.py    tope + rampa                   sim o real

DOS DESTINOS, UN SOLO CODIGO
----------------------------
    --mode sim    publica en rt/wirelesscontroller. Lo consume
                  `run_policy.py --teleop`, que mueve al robot simulado con la
                  politica RL. unitree_mujoco NO emula Sport Mode.
    --mode real   llama a SportClient directamente, con StandUp ->
                  BalanceStand -> Move. Con Go2Controller uc04 no movia el
                  robot; falta verificar si es por no llamar a BalanceStand.

SEGURIDAD
---------
    - velocidades limitadas al mas estricto de params.yaml y del contrato
    - rampa de aceleracion
    - para si la telemetria se congela, si el robot se inclina demasiado o si
      la bateria esta baja
    - Ctrl-C, error o fin de --duration envian velocidad cero antes de salir
    - --dry-run calcula todo pero NO envia nada al robot

Uso:
    # Comprobacion sin mover nada (funciona incluso sin simulador)
    python3 usecases/uc00_plantilla/deploy/main.py --mode sim --dry-run

    # Simulacion: antes, simulador y `run_policy.py --mode sim --teleop`
    python3 usecases/uc00_plantilla/deploy/main.py --mode sim

    # Robot real: primero --dry-run, mando en la mano (L2+B amortigua)
    python3 usecases/uc00_plantilla/deploy/main.py --mode real --dry-run
"""

from __future__ import annotations

import argparse
import csv
import math
import signal
import sys
import threading
import time
from pathlib import Path

import numpy as np
import yaml

# `paths` deduce la raiz del repositorio desde su propia ubicacion: funciona
# igual dentro del contenedor (/workspace) que en un clon cualquiera.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
# Para que mi_caso.py pueda importar robot_camera (ejemplo 4).
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))

from go2core import paths                     # noqa: E402
from go2core.control import contract as ct    # noqa: E402
from go2core.logging.run import create_run    # noqa: E402

UC = Path(__file__).resolve().parents[1]
# mi_caso.py vive en la carpeta del caso de uso, no en deploy/.
sys.path.insert(0, str(UC))
import mi_caso  # noqa: E402

# El nombre de la carpeta es el nombre del caso de uso en experiments/, asi
# que al renombrar la plantilla no hay que tocar nada aqui.
USECASE = UC.name


# ===========================================================================
# Telemetria
# ===========================================================================
class Telemetria:
    """Suscriptor de rt/lowstate de solo lectura. NO publica nada.

    Es segura junto a Sport Mode. La clase LowLevel de go2core no lo es: su
    hilo publica LowCmd continuamente y pelearia con el controlador del
    fabricante por los mismos motores.
    """

    def __init__(self) -> None:
        self.msg = None
        self.t = 0.0
        self._lock = threading.Lock()

    def start(self) -> None:
        from unitree_sdk2py.core.channel import ChannelSubscriber
        from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_
        ChannelSubscriber("rt/lowstate", LowState_).Init(self._on, 10)

    def _on(self, m) -> None:
        with self._lock:
            self.msg, self.t = m, time.monotonic()

    def esperar(self, s: float) -> bool:
        t0 = time.monotonic()
        while self.msg is None and time.monotonic() - t0 < s:
            time.sleep(0.02)
        return self.msg is not None

    def edad_s(self) -> float:
        return float("inf") if self.msg is None else time.monotonic() - self.t

    # -- lecturas --
    def q(self) -> np.ndarray:
        return np.asarray([self.msg.motor_state[i].q for i in range(12)], np.float32)

    def dq(self) -> np.ndarray:
        return np.asarray([self.msg.motor_state[i].dq for i in range(12)], np.float32)

    def tau(self) -> np.ndarray:
        return np.asarray([getattr(self.msg.motor_state[i], "tau_est", 0.0)
                           for i in range(12)], np.float32)

    def gyro(self) -> np.ndarray:
        return np.asarray(self.msg.imu_state.gyroscope, np.float32)

    def inclinacion(self) -> float:
        """Angulo del tronco respecto a la vertical, en radianes."""
        _, x, y, _ = self.msg.imu_state.quaternion
        return math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * (x * x + y * y))))

    # Solo robot real: en simulacion no hay temperatura, foot_force ni bms
    # y salen a cero. Por eso no sirven para decidir nada en sim.
    def temp_max(self) -> float:
        return float(max(getattr(self.msg.motor_state[i], "temperature", 0)
                         for i in range(12)))

    def foot_force(self) -> np.ndarray:
        return np.asarray(getattr(self.msg, "foot_force", [0, 0, 0, 0]), np.float32)

    def bateria_pct(self) -> float:
        bms = getattr(self.msg, "bms_state", None)
        return float(getattr(bms, "soc", 0) or 0) if bms else 0.0


class TelemetriaNula:
    """Lo que ve decidir() cuando no llega telemetria (solo con --dry-run).

    Devuelve ceros en vez de None para que quien escribe mi_caso.py no tenga
    que comprobar nada: un caso de uso que funciona con telemetria real
    tambien arranca en una comprobacion sin simulador.
    """

    def q(self): return np.zeros(12, np.float32)
    def dq(self): return np.zeros(12, np.float32)
    def tau(self): return np.zeros(12, np.float32)
    def gyro(self): return np.zeros(3, np.float32)
    def inclinacion(self): return 0.0
    def temp_max(self): return 0.0
    def foot_force(self): return np.zeros(4, np.float32)
    def bateria_pct(self): return 0.0


# ===========================================================================
# Salidas (mismo patron que uc04: SalidaSimulador y SalidaRobot)
# ===========================================================================
class SalidaSimulador:
    """Publica velocidades en rt/wirelesscontroller.

    Es el mismo canal que usa tools/teleop.py, asi que `run_policy.py
    --teleop` las recibe sin cambio alguno. El robot simulado camina con la
    politica de locomocion y este script solo le dice a donde ir.
    """

    nombre = "simulador (rt/wirelesscontroller)"

    def __init__(self) -> None:
        from unitree_sdk2py.core.channel import ChannelPublisher
        from unitree_sdk2py.idl.unitree_go.msg.dds_ import WirelessController_
        self.pub = ChannelPublisher("rt/wirelesscontroller", WirelessController_)
        self.pub.Init()
        self.msg = WirelessController_(lx=0.0, ly=0.0, rx=0.0, ry=0.0, keys=0)

    def enviar(self, vx: float, vy: float, wz: float) -> None:
        # Mapeo del mando: ly = vx, lx = vy, rx = wz
        self.msg.ly, self.msg.lx, self.msg.rx = float(vx), float(vy), float(wz)
        self.pub.Write(self.msg)

    def cerrar(self) -> None:
        for _ in range(10):
            self.enviar(0.0, 0.0, 0.0)
            time.sleep(0.01)


class SalidaRobot:
    """Sport Mode del fabricante. Solo robot real.

    Llama a SportClient DIRECTAMENTE, con la secuencia completa: Move no hace
    nada hasta que StandUp y BalanceStand han terminado. Con Go2Controller,
    uc04 no movia el robot (causa probable: falta BalanceStand; pendiente de
    verificar con el robot). Ver tools/teleop_real.py.
    """

    nombre = "robot real (SportClient)"

    def __init__(self) -> None:
        from unitree_sdk2py.go2.sport.sport_client import SportClient
        self.sport = SportClient()
        self.sport.SetTimeout(10.0)
        self.sport.Init()
        print("  levantando el robot (StandUp + BalanceStand)...")
        self.sport.StandUp()
        time.sleep(3.0)
        self.sport.BalanceStand()
        time.sleep(2.0)

    def enviar(self, vx: float, vy: float, wz: float) -> None:
        self.sport.Move(float(vx), float(vy), float(wz))

    def cerrar(self) -> None:
        try:
            self.sport.StopMove()
            time.sleep(0.5)
            self.sport.BalanceStand()
        except Exception as e:
            print(f"fallo al parar: {e}. USA EL MANDO: L2+B")


# ===========================================================================
# Limites y rampa
# ===========================================================================
class Limitador:
    """Aplica topes, umbral minimo util y rampa de aceleracion."""

    # La rampa converge a cero dejando residuos del orden de 1e-6. Sin este
    # epsilon el umbral minimo util los subiria a 0.2 y el robot recibiria
    # orden de moverse cuando la logica pide parar.
    EPS = 1e-3

    def __init__(self, cfg: dict, limites: dict, real: bool) -> None:
        self.acel = float(cfg["aceleracion_max"])
        # El mas estricto entre el tope propio y el del contrato.
        self.lim = [
            (max(-cfg["vx_max"], limites["vx_range"][0]),
             min(cfg["vx_max"], limites["vx_range"][1])),
            (max(-cfg["vy_max"], limites["vy_range"][0]),
             min(cfg["vy_max"], limites["vy_range"][1])),
            (max(-cfg["wz_max"], limites["wz_range"][0]),
             min(cfg["wz_max"], limites["wz_range"][1])),
        ]
        # Solo en real: Sport Mode ignora las ordenes por debajo de ~0.2 m/s,
        # asi que sin subirlas el robot no se mueve. La politica RL de la
        # simulacion SI responde a ordenes pequenas; forzar el minimo ahi
        # cambiaria la logica probada y falsearia la comparacion sim/real.
        # (uc04 lo aplica siempre; deberia revisarse.)
        v, w = float(cfg["vel_min_util"]), float(cfg["wz_min_util"])
        self.minimos = [v, v, w] if real else [0.0, 0.0, 0.0]
        self.actual = [0.0, 0.0, 0.0]

    def paso(self, deseada: tuple[float, float, float], dt: float) -> tuple[float, float, float]:
        salida = []
        for i, d in enumerate(deseada):
            lo, hi = self.lim[i]
            d = float(np.clip(d, lo, hi))
            if abs(d) <= self.EPS:
                d = 0.0
            elif abs(d) < self.minimos[i]:
                d = math.copysign(self.minimos[i], d)

            paso_max = self.acel * dt
            a = self.actual[i] + float(np.clip(d - self.actual[i], -paso_max, paso_max))
            if abs(a) < self.EPS:
                a = 0.0
            self.actual[i] = float(np.clip(a, lo, hi))
            salida.append(self.actual[i])
        return salida[0], salida[1], salida[2]


# ===========================================================================
def iniciar_dds(domain: int, iface: str, dry_run: bool) -> bool:
    """Inicializa DDS una sola vez. Devuelve False si no hay SDK (solo dry-run)."""
    try:
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize
    except ImportError:
        if dry_run:
            print("  AVISO: no hay unitree_sdk2py; --dry-run sigue sin telemetria.")
            print("         Dentro de la caja (./go2 dev shell) si la tendras.")
            return False
        raise SystemExit("No se puede importar unitree_sdk2py. Ejecuta esto "
                         "dentro de la caja: ./go2 dev shell")
    ChannelFactoryInitialize(domain, iface)
    return True


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=["sim", "real"], default="sim")
    p.add_argument("--iface", default=None, help="anula GO2_IFACE y el contrato")
    p.add_argument("--config", default=str(UC / "configs" / "params.yaml"))
    p.add_argument("--duration", type=float, default=10.0, help="segundos")
    p.add_argument("--dry-run", action="store_true",
                   help="calcula y muestra, pero NO envia velocidades")
    p.add_argument("--log", action="store_true",
                   help="registrar en experiments/ con manifest.json")
    p.add_argument("--tag", default="run", help="etiqueta del experimento")
    args = p.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    c = ct.load_contract(paths.CONTRACT)
    dds = c["dds"][args.mode]
    iface = args.iface or paths.iface() or dds["interface"]
    domain = paths.domain() if paths.domain() is not None else dds["domain_id"]
    real = args.mode == "real"
    ctl, seg = cfg["control"], cfg["seguridad"]

    print(f"{USECASE}")
    print(f"  modo     : {args.mode} (domain {domain}, {iface})")
    print(f"  duracion : {args.duration:.0f} s a {ctl['hz']} Hz")
    if args.dry_run:
        print("  DRY RUN: no se envia ninguna velocidad")
    print()

    if real and not args.dry_run:
        print("  ROBOT FISICO. Confirma:")
        print("   - docs/SAFETY.md leido")
        print("   - espacio libre de 3 m alrededor")
        print("   - mando en la mano (L2+B amortigua)")
        if input("\n  Escribe 'si' para continuar: ").strip().lower() != "si":
            return 1

    hay_dds = iniciar_dds(domain, iface, args.dry_run)

    tel = None
    if hay_dds:
        tel = Telemetria()
        tel.start()
        # En dry-run se sigue sin telemetria: comprobar la plantilla no debe
        # exigir que haya un simulador arrancado.
        if not tel.esperar(2.0 if args.dry_run else 5.0):
            if not args.dry_run:
                print("No llega rt/lowstate. Comprueba que el simulador o el "
                      "robot estan activos.")
                return 1
            print("  AVISO: no llega rt/lowstate (simulador apagado?); "
                  "sigo sin telemetria.")
            tel = None

    if real and tel is not None and seg["bateria_min_pct"] > 0:
        bat = tel.bateria_pct()
        if bat < seg["bateria_min_pct"]:
            print(f"Bateria al {bat:.0f} %, minimo {seg['bateria_min_pct']} %.")
            return 1

    salida = None
    if not args.dry_run:
        salida = (SalidaRobot if real else SalidaSimulador)()
        print(f"salida: {salida.nombre}")

    limitador = Limitador(ctl, c["commands"], real)

    # Los parametros propios de configs/params.yaml (seccion mi_caso) llegan a
    # mi_caso.py como el diccionario PARAMS. Asi quien escribe su caso no
    # tiene que abrir ni interpretar el yaml.
    mi_caso.PARAMS = cfg.get("mi_caso") or {}

    # Gancho opcional: si mi_caso.py define preparar(), se llama una vez antes
    # del bucle. Sirve para abrir la camara o cargar un modelo, que es lento y
    # no debe hacerse en cada paso. Solo lo usa el ejemplo 4.
    if hasattr(mi_caso, "preparar"):
        mi_caso.preparar(args.mode, iface, domain)

    run_dir = None
    if args.log:
        run_dir = create_run(USECASE, args.tag, config={
            "args": vars(args), "iface": iface, "domain": domain,
            "telemetria": tel is not None, "params": cfg,
        })

    parar = {"flag": False}
    signal.signal(signal.SIGINT, lambda *_: parar.__setitem__("flag", True))
    signal.signal(signal.SIGTERM, lambda *_: parar.__setitem__("flag", True))

    filas: list = []
    avisado_none = False
    motivo = "fin de --duration"
    dt_obj = 1.0 / float(ctl["hz"])
    t0 = t_prev = time.monotonic()
    siguiente = t0
    n = 0
    print("\nen marcha. Ctrl-C para parar.\n")

    try:
        while not parar["flag"]:
            ahora = time.monotonic()
            t = ahora - t0
            if t >= args.duration:
                break
            # Tope al dt: tras una pausa larga, una rampa con dt grande daria
            # un salto de velocidad.
            dt = min(ahora - t_prev, 0.2)
            t_prev = ahora

            # --- comprobaciones de seguridad ---
            if tel is not None:
                if tel.edad_s() > seg["telemetria_max_edad_s"]:
                    motivo = f"telemetria congelada ({tel.edad_s():.1f} s)"
                    break
                if tel.inclinacion() > c["safety"]["max_tilt_rad"]:
                    motivo = f"inclinacion {math.degrees(tel.inclinacion()):.0f} deg"
                    break

            # --- decidir, limitar, enviar ---
            deseada = mi_caso.decidir(tel or TelemetriaNula(), t)
            if deseada is None:
                # Lo mas habitual: una cadena if/elif sin `return` final. Parar
                # y avisar es mejor que romper con un error de desempaquetado.
                if not avisado_none:
                    print("  AVISO: decidir() no ha devuelto nada; se manda "
                          "velocidad cero. Le falta un return al final.")
                    avisado_none = True
                deseada = (0.0, 0.0, 0.0)
            vx, vy, wz = limitador.paso(deseada, dt)
            if salida is not None:
                salida.enviar(vx, vy, wz)

            n += 1
            incl = tel.inclinacion() if tel else 0.0
            bat = tel.bateria_pct() if tel else 0.0
            tmax = tel.temp_max() if tel else 0.0
            if args.log:
                filas.append([f"{t:.3f}", f"{vx:.4f}", f"{vy:.4f}", f"{wz:.4f}",
                              f"{incl:.4f}", f"{bat:.0f}", f"{tmax:.0f}"])
            if n % int(ctl["hz"]) == 1:
                tele = (f"incl {math.degrees(incl):5.1f} deg  bat {bat:3.0f} %  "
                        f"temp {tmax:3.0f} C" if tel else "sin telemetria")
                print(f"  t {t:5.1f} s  {tele}  ->  "
                      f"vx {vx:+.2f}  vy {vy:+.2f}  wz {wz:+.2f}")

            siguiente += dt_obj
            time.sleep(max(0.0, siguiente - time.monotonic()))

    except Exception as e:
        motivo = f"error: {type(e).__name__}: {e}"
    finally:
        # Siempre velocidad cero, pase lo que pase.
        if salida is not None:
            salida.cerrar()

    if parar["flag"]:
        motivo = "interrumpido"
    print(f"\nfin: {motivo}. {n} pasos en {time.monotonic() - t0:.1f} s.")

    if run_dir is not None:
        with open(run_dir / "metrics.csv", "w", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["t", "vx", "vy", "wz", "inclinacion_rad",
                        "bateria_pct", "temp_max_c"])
            w.writerows(filas)
        print(f"escrito: {run_dir}")
        print(f"medir:   python3 usecases/{USECASE}/eval/measure.py "
              f"--run {run_dir}")

    return 0 if motivo in ("fin de --duration", "interrumpido") else 1


if __name__ == "__main__":
    raise SystemExit(main())
