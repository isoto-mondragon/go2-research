# =============================================================================
# ESTE FICHERO NO SE TOCA.
# Tu codigo va en mi_caso.py, en la carpeta de arriba (uc00_plantilla/).
# =============================================================================
"""usecases/uc00_plantilla/deploy/robot.py

El objeto `robot` que recibe mi_caso.py. Cada metodo publico es un verbo que se
lee de arriba abajo, sin que quien escribe el caso sepa nada de DDS, de rampas
ni de Sport Mode.

    mi_caso.caso(robot) ──► verbos ──► limitador (tope + rampa) ──► salida ──► robot
                                                                    sim o real

POR QUE LOS VERBOS BLOQUEAN
---------------------------
`robot.avanzar(2)` no vuelve hasta que han pasado los dos segundos. Por dentro
corre un bucle a 20 Hz que envia la velocidad, mira la telemetria y comprueba la
seguridad. Asi el caso se escribe como una secuencia ("levantate, avanza, para")
y no como una maquina de estados que se llama 20 veces por segundo.

SEGURIDAD
---------
Cualquier verbo lanza `Parar` si se acaba --duration, si se pulsa Ctrl-C, si la
telemetria se congela o si el robot se inclina demasiado. `Parar` hereda de
BaseException a proposito: un `except Exception` en el caso no puede tragarsela
y dejar al robot andando. main.py la recoge y manda velocidad cero.
"""

from __future__ import annotations

import math
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
# Para que el caso pueda usar tools/robot_camera.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))

from go2core import paths  # noqa: E402


class Parar(BaseException):
    """El caso debe terminar ya. El texto es el motivo."""


@dataclass
class Persona:
    """Lo que devuelve robot.buscar_persona()."""

    visible: bool = False
    lateral: float = 0.0     # -1 a la izquierda de la imagen, +1 a la derecha
    tamano: float = 0.0      # 0 a 1, fraccion del alto de la imagen; sube al acercarse
    confianza: float = 0.0


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

    # Solo robot real: en simulacion no hay temperatura, foot_force ni bms y
    # salen a cero. Por eso no sirven para decidir nada en sim.
    def temp_max(self) -> float:
        return float(max(getattr(self.msg.motor_state[i], "temperature", 0)
                         for i in range(12)))

    def foot_force(self) -> np.ndarray:
        return np.asarray(getattr(self.msg, "foot_force", [0, 0, 0, 0]), np.float32)

    def bateria_pct(self) -> float:
        bms = getattr(self.msg, "bms_state", None)
        return float(getattr(bms, "soc", 0) or 0) if bms else 0.0


class TelemetriaNula:
    """Lo que ve el caso cuando no llega telemetria (solo con --dry-run).

    Devuelve ceros en vez de None para que quien escribe el caso no tenga que
    comprobar nada: un caso que funciona con telemetria real tambien arranca en
    una comprobacion sin simulador.
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
        self.de_pie = False

    def levantar(self, dormir) -> None:
        self.sport.StandUp()
        dormir(3.0)
        self.sport.BalanceStand()
        dormir(2.0)
        self.de_pie = True

    def sentar(self, dormir) -> None:
        self.sport.StopMove()
        dormir(0.5)
        self.sport.Sit()
        dormir(2.0)
        self.de_pie = False

    def enviar(self, vx: float, vy: float, wz: float) -> None:
        self.sport.Move(float(vx), float(vy), float(wz))

    def cerrar(self) -> None:
        try:
            self.sport.StopMove()
            time.sleep(0.5)
            # Si el caso lo dejo sentado no hay que volver a levantarlo.
            if self.de_pie:
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

    def parado(self) -> bool:
        return all(abs(a) <= self.EPS for a in self.actual)

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
class Robot:
    """Lo que recibe mi_caso.caso(). Ver docstring del modulo."""

    def __init__(self, *, cfg: dict, contrato: dict, modo: str, iface: str,
                 domain: int, tel: Telemetria | None, salida, dry_run: bool,
                 duracion: float, parada: dict) -> None:
        self.modo = modo
        self.es_real = modo == "real"
        self.dry_run = dry_run
        self._cfg = cfg
        self._iface, self._domain = iface, domain
        self._tel = tel
        self._nula = TelemetriaNula()
        self._salida = salida
        self._limitador = Limitador(cfg["control"], contrato["commands"], self.es_real)
        self._max_incl = float(contrato["safety"]["max_tilt_rad"])
        self._seg = cfg["seguridad"]
        self._duracion = duracion
        self._parada = parada            # {"flag": bool}, lo pone el manejador de Ctrl-C
        self._dt = 1.0 / float(cfg["control"]["hz"])
        self._motivo: str | None = None

        self._t0 = self._t_prev = self._siguiente = time.monotonic()
        self._n = 0
        self._de_pie = False
        self._imprimir_en = 0.0
        self.filas: list = []            # para metrics.csv

        self._detector = None
        self._detector_fallido = False
        self._camara = None
        self._avisos: set[str] = set()

    # -- internos ----------------------------------------------------------
    @property
    def _t(self):
        return self._tel or self._nula

    def _avisa(self, clave: str, texto: str) -> None:
        """Un aviso solo una vez: en un bucle a 20 Hz inundaria la pantalla."""
        if clave not in self._avisos:
            self._avisos.add(clave)
            print(f"  AVISO: {texto}")

    def _motivo_parada(self) -> str | None:
        if self._motivo:
            return self._motivo
        if self._parada["flag"]:
            self._motivo = "interrumpido"
        elif self.tiempo() >= self._duracion:
            self._motivo = "fin de --duration"
        elif self._tel is not None:
            if self._tel.edad_s() > self._seg["telemetria_max_edad_s"]:
                self._motivo = f"telemetria congelada ({self._tel.edad_s():.1f} s)"
            elif self._tel.inclinacion() > self._max_incl:
                self._motivo = f"inclinacion {math.degrees(self._tel.inclinacion()):.0f} deg"
        return self._motivo

    def _comprobar(self) -> None:
        m = self._motivo_parada()
        if m:
            raise Parar(m)

    def _dormir(self, s: float) -> None:
        """Como time.sleep, pero atento a Ctrl-C y a la seguridad."""
        fin = time.monotonic() + s
        while time.monotonic() < fin:
            self._comprobar()
            time.sleep(min(0.05, max(0.0, fin - time.monotonic())))

    def _paso(self, deseada: tuple[float, float, float]) -> None:
        """Un paso del bucle de control: seguridad, limites, envio y ritmo."""
        self._comprobar()
        ahora = time.monotonic()
        # Tope al dt: tras una pausa larga (cargar YOLO, por ejemplo), una rampa
        # con dt grande daria un salto de velocidad.
        dt = min(ahora - self._t_prev, 0.2)
        self._t_prev = ahora

        vx, vy, wz = self._limitador.paso(deseada, dt)
        if self._salida is not None:
            self._salida.enviar(vx, vy, wz)

        self._n += 1
        t = self.tiempo()
        incl, bat, tmax = self._t.inclinacion(), self._t.bateria_pct(), self._t.temp_max()
        self.filas.append([f"{t:.3f}", f"{vx:.4f}", f"{vy:.4f}", f"{wz:.4f}",
                           f"{incl:.4f}", f"{bat:.0f}", f"{tmax:.0f}"])
        if t >= self._imprimir_en:
            self._imprimir_en = t + 1.0
            tele = (f"incl {math.degrees(incl):5.1f} deg  bat {bat:3.0f} %  "
                    f"temp {tmax:3.0f} C" if self._tel else "sin telemetria")
            print(f"  t {t:5.1f} s  {tele}  ->  vx {vx:+.2f}  vy {vy:+.2f}  wz {wz:+.2f}")

        # Si el paso llego tarde, no se intenta recuperar el retraso a base de
        # pasos seguidos: se reancla el ritmo.
        self._siguiente += self._dt
        if self._siguiente < time.monotonic() - self._dt:
            self._siguiente = time.monotonic()
        time.sleep(max(0.0, self._siguiente - time.monotonic()))

    def _mover_durante(self, v: tuple[float, float, float], segundos: float) -> None:
        fin = time.monotonic() + segundos
        while time.monotonic() < fin:
            self._paso(v)
        self.parar()

    def _asegurar_de_pie(self) -> None:
        # En el robot real Move no hace nada si el robot esta tumbado. Es lo mas
        # habitual al empezar (se olvida levantarse), asi que se avisa y se hace.
        if self.es_real and not self._de_pie:
            self._avisa("de_pie", "el robot no estaba de pie; llamo a levantarse().")
            self.levantarse()

    # -- estado del caso ---------------------------------------------------
    def activo(self) -> bool:
        """True mientras el caso deba seguir. Uso: `while robot.activo():`."""
        return self._motivo_parada() is None

    @property
    def motivo(self) -> str | None:
        """Por que hay que parar, o None si el caso puede seguir."""
        return self._motivo

    def tiempo(self) -> float:
        """Segundos desde que empezo el caso."""
        return time.monotonic() - self._t0

    def param(self, nombre: str, defecto=None):
        """Un parametro de la seccion mi_caso de configs/params.yaml."""
        return (self._cfg.get("mi_caso") or {}).get(nombre, defecto)

    # -- postura -----------------------------------------------------------
    def levantarse(self) -> None:
        """Pone al robot de pie y equilibrado. En simulacion no hace nada."""
        if self.dry_run:
            print("  [dry-run] levantarse()")
        elif self.es_real:
            print("  levantando el robot (StandUp + BalanceStand)...")
            self._salida.levantar(self._dormir)
        else:
            # unitree_mujoco no emula Sport Mode: el robot simulado ya lo pone
            # de pie la politica RL de run_policy.py.
            self._avisa("levantarse_sim", "en simulacion no hay StandUp: el robot "
                        "ya lo levanta la politica RL de run_policy.py.")
        self._de_pie = True

    def sentarse(self) -> None:
        """Sienta al robot. Solo en el robot real. Despues, levantarse()."""
        self.parar()
        if self.dry_run:
            print("  [dry-run] sentarse()")
        elif self.es_real:
            self._salida.sentar(self._dormir)
        else:
            self._avisa("sentarse_sim", "sentarse() no existe en simulacion "
                        "(no hay Sport Mode); no hago nada.")
        self._de_pie = False

    # -- movimiento --------------------------------------------------------
    def mover(self, vx: float = 0.0, vy: float = 0.0, wz: float = 0.0) -> None:
        """UN paso de control (unos 50 ms) con esta velocidad.

        vx adelante (+) o atras (-), m/s. vy izquierda (+) o derecha (-), m/s.
        wz giro a la izquierda (+) o a la derecha (-), rad/s. Se llama dentro de
        un bucle. Los topes y la rampa se aplican solos.
        """
        self._asegurar_de_pie()
        self._paso((vx, vy, wz))

    def avanzar(self, segundos: float, vel: float = 0.3) -> None:
        """Avanza `segundos` y para."""
        self._asegurar_de_pie()
        self._mover_durante((abs(vel), 0.0, 0.0), segundos)

    def retroceder(self, segundos: float, vel: float = 0.3) -> None:
        """Retrocede `segundos` y para."""
        self._asegurar_de_pie()
        self._mover_durante((-abs(vel), 0.0, 0.0), segundos)

    def girar_izquierda(self, segundos: float, vel: float = 0.5) -> None:
        """Gira a la izquierda `segundos` (vel en rad/s) y para."""
        self._asegurar_de_pie()
        self._mover_durante((0.0, 0.0, abs(vel)), segundos)

    def girar_derecha(self, segundos: float, vel: float = 0.5) -> None:
        """Gira a la derecha `segundos` (vel en rad/s) y para."""
        self._asegurar_de_pie()
        self._mover_durante((0.0, 0.0, -abs(vel)), segundos)

    def parar(self) -> None:
        """Frena con rampa hasta quedarse quieto."""
        for _ in range(int(2.0 / self._dt)):
            if self._limitador.parado():
                return
            self._paso((0.0, 0.0, 0.0))

    def esperar(self, segundos: float) -> None:
        """Se queda quieto `segundos`, vigilando la seguridad."""
        fin = time.monotonic() + segundos
        while time.monotonic() < fin:
            self._paso((0.0, 0.0, 0.0))

    # -- sensores ----------------------------------------------------------
    def inclinacion_grados(self) -> float:
        """Inclinacion del cuerpo en grados; 0 es recto."""
        return math.degrees(self._t.inclinacion())

    def giro(self) -> np.ndarray:
        """Velocidad de giro del cuerpo, 3 ejes, rad/s. [2] es el giro sobre si mismo."""
        return self._t.gyro()

    def angulos(self) -> np.ndarray:
        """12 angulos de las articulaciones, rad. Orden FR, FL, RR, RL; hip, thigh, calf."""
        return self._t.q()

    def velocidades(self) -> np.ndarray:
        """12 velocidades de las articulaciones, rad/s. Mismo orden."""
        return self._t.dq()

    def pares(self) -> np.ndarray:
        """12 pares estimados, Nm. Mismo orden."""
        return self._t.tau()

    def bateria(self) -> float:
        """Carga, 0 a 100. SIEMPRE 0 en simulacion."""
        return self._t.bateria_pct()

    def temperatura(self) -> float:
        """Grados del motor mas caliente. SIEMPRE 0 en simulacion."""
        return self._t.temp_max()

    def fuerza_pies(self) -> np.ndarray:
        """4 valores, uno por pie. SIEMPRE 0 en simulacion."""
        return self._t.foot_force()

    # -- percepcion --------------------------------------------------------
    def imagen(self):
        """Fotograma de la camara del robot (BGR, 1920x1080), o None si falla.

        Solo en el robot real: en simulacion no hay camara del robot.
        """
        if not self.es_real:
            self._avisa("imagen_sim", "en simulacion no hay camara del robot; "
                        "imagen() devuelve None.")
            return None
        if self._camara is None:
            try:
                from robot_camera import CamaraRobot
                self._camara = CamaraRobot(self._iface, self._domain, init_dds=False)
            except Exception as e:
                self._avisa("camara", f"no puedo abrir la camara ({type(e).__name__}: {e}).")
                return None
        return self._camara.leer()

    def cargar_detector(self) -> None:
        """Carga YOLO (tarda unos segundos). Llamalo una vez, antes del bucle.

        Con el robot real usa su camara; en simulacion, la webcam del portatil.
        Si no se puede, avisa y buscar_persona() devolvera siempre "no visible":
        el robot no se movera en vez de fallar.
        """
        if self._detector is not None or self._detector_fallido:
            return
        print("  cargando YOLO...")
        try:
            sys.path.insert(0, str(paths.USECASES / "uc04_person_following"))
            from perception.detector import DetectorPersonas
            self._detector = DetectorPersonas(
                fuente="robot" if self.es_real else "webcam",
                iface=self._iface, domain=self._domain, init_dds=False)
            print("  detector listo")
        except Exception as e:
            self._detector_fallido = True
            self._avisa("detector", f"sin detector ({type(e).__name__}: {e}). "
                        "buscar_persona() no vera a nadie.")

    def buscar_persona(self) -> Persona:
        """Mira la camara y devuelve la persona mas cercana (clase Persona)."""
        self.cargar_detector()
        if self._detector is None:
            return Persona()
        imagen, d = self._detector.leer()
        if imagen is None:
            self._avisa("sin_imagen", "la camara no da imagen.")
            return Persona()
        return Persona(bool(d.visible), float(d.lateral), float(d.tamano),
                       float(d.confianza))

    # -- cierre ------------------------------------------------------------
    def cerrar(self) -> None:
        if self._detector is not None:
            try:
                self._detector.cerrar()
            except Exception:
                pass
