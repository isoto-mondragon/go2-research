#!/usr/bin/env python3
"""usecases/uc04_person_following/deploy/follow_person.py

uc04 — El robot sigue a una persona.

    cámara ──► YOLO ──► control ──► (vx, vy, wz) ──► robot
                                                      │
                             simulador MuJoCo  o  Go2 físico

DOS DESTINOS, UN SOLO CÓDIGO
----------------------------
    --mode sim    publica en rt/wirelesscontroller, igual que tools/teleop.py.
                  Lo consume `run_policy.py --teleop`, que mueve al robot en
                  el simulador con la política de locomoción.
    --mode real   llama a Go2Controller, es decir a Sport Mode. El controlador
                  del fabricante se encarga de caminar.

En los dos casos este script solo decide velocidades. No sabe caminar, y no
tiene por qué: de eso se encarga la capa de locomoción.

LEY DE CONTROL
--------------
Proporcional sobre dos errores, con zona muerta:

    giro      centrar la persona en la imagen
    avance    mantener un tamaño aparente constante, que equivale a mantener
              la distancia

La zona muerta es importante: sin ella el robot oscila constantemente por el
ruido de la detección. Y la rampa de aceleración evita tirones cuando la
detección salta.

SEGURIDAD
---------
    - velocidades limitadas a los rangos del contrato
    - si se pierde a la persona, el robot para (no sigue con el último comando)
    - si la detección se congela, el watchdog para el robot
    - Ctrl-C envía velocidad cero antes de salir

Uso:
    # Terminal 1: simulador
    ./go2 sim up

    # Terminal 2: la política de locomoción escuchando comandos
    python3 usecases/uc01_locomotion/deploy/run_policy.py --mode sim --teleop --duration 600

    # Terminal 3: este script
    python3 usecases/uc04_person_following/deploy/follow_person.py --mode sim --show
"""

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse   # noqa: E402
import csv        # noqa: E402
import json       # noqa: E402
import signal     # noqa: E402
import subprocess  # noqa: E402
import sys        # noqa: E402
import time       # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path       # noqa: E402

import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from go2core import paths                   # noqa: E402
from go2core.control import contract as ct   # noqa: E402
from perception.detector import DetectorPersonas  # noqa: E402

UC = Path(__file__).resolve().parents[1]


# ===========================================================================
class SalidaSimulador:
    """Publica velocidades en rt/wirelesscontroller.

    Es el mismo canal que usa tools/teleop.py, asi que `run_policy.py --teleop`
    las recibe sin cambio alguno. El robot del simulador camina con la politica
    de locomocion y este script solo le dice a donde ir.
    """

    nombre = "simulador (rt/wirelesscontroller)"

    def __init__(self, domain: int, iface: str) -> None:
        from unitree_sdk2py.core.channel import (ChannelFactoryInitialize,
                                                 ChannelPublisher)
        from unitree_sdk2py.idl.unitree_go.msg.dds_ import WirelessController_
        ChannelFactoryInitialize(domain, iface)
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

    Llama a SportClient DIRECTAMENTE, no a Go2Controller. Ese wrapper se
    escribio para el simulador del workspace WSL2 y publica en
    rt/wirelesscontroller, un topic que el robot fisico NO escucha desde fuera:
    lo publica el mando. Resultado: los comandos salian y el robot no se movia.

    Esta es la misma secuencia validada a mano: BalanceStand y luego Move.
    """

    nombre = "robot real (SportClient)"

    def __init__(self, domain: int, iface: str) -> None:
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize
        from unitree_sdk2py.go2.sport.sport_client import SportClient
        ChannelFactoryInitialize(domain, iface)
        self.sport = SportClient()
        self.sport.SetTimeout(10.0)
        self.sport.Init()
        print("  levantando el robot (StandUp + BalanceStand)...")
        self.sport.StandUp()
        time.sleep(3.0)
        self.sport.BalanceStand()
        time.sleep(2.0)
        self.n = 0

    def enviar(self, vx: float, vy: float, wz: float) -> None:
        self.sport.Move(float(vx), float(vy), float(wz))
        self.n += 1

    def cerrar(self) -> None:
        try:
            self.sport.StopMove()
            time.sleep(0.5)
            self.sport.BalanceStand()
        except Exception as e:
            print(f"fallo al parar: {e}. USA EL MANDO: L2+B")


# ===========================================================================
class ControlSeguimiento:
    """Convierte la detección en velocidades, con zona muerta y rampa."""

    def __init__(self, cfg: dict, limites: dict) -> None:
        self.objetivo = float(cfg["objetivo_tamano"])
        self.kp_giro = float(cfg["kp_giro"])
        self.kp_avance = float(cfg["kp_avance"])
        self.zm_lateral = float(cfg["zona_muerta_lateral"])
        self.zm_tamano = float(cfg["zona_muerta_tamano"])
        self.acel_max = float(cfg["aceleracion_max"])

        # Limites absolutos del contrato. NO confundir con los umbrales
        # minimos utiles de mas abajo: usar el mismo nombre para ambos hacia
        # que el clip final recortase vx al rango [0.20, 1.0], y el robot no
        # podia parar ni retroceder nunca.
        self.vx_lim_min, self.vx_lim_max = limites["vx_range"]
        self.wz_lim_min, self.wz_lim_max = limites["wz_range"]
        # Tope propio, mas conservador que el del contrato: seguir a una
        # persona no necesita la velocidad maxima del robot y limitarla hace
        # la demo mucho mas segura.
        self.vx_tope = float(cfg["vx_max"])
        self.wz_tope = float(cfg["wz_max"])
        # Sport Mode ignora los comandos por debajo de un umbral interno: el
        # robot se queda quieto y parece que el seguimiento no funciona. Si el
        # comando no es cero pero se queda corto, se sube al minimo util.
        self.vx_util = float(cfg.get("vx_min_util", 0.0))
        self.wz_util = float(cfg.get("wz_min_util", 0.0))

        self.vx = self.wz = 0.0

    def paso(self, d, dt: float) -> tuple[float, float, float]:
        if not d.visible:
            objetivo_vx = objetivo_wz = 0.0
        else:
            # Giro: centrar la persona. Signo negativo porque una persona a la
            # derecha (lateral > 0) exige girar a la derecha (wz < 0).
            e_lat = d.lateral
            objetivo_wz = (0.0 if abs(e_lat) < self.zm_lateral
                           else -self.kp_giro * e_lat)

            # Avance: mantener el tamano aparente, o sea la distancia.
            # Persona pequena (lejos) -> avanzar. Grande (cerca) -> retroceder.
            e_tam = self.objetivo - d.tamano
            objetivo_vx = (0.0 if abs(e_tam) < self.zm_tamano
                           else self.kp_avance * e_tam)

        objetivo_vx = float(np.clip(objetivo_vx, -self.vx_tope, self.vx_tope))
        objetivo_wz = float(np.clip(objetivo_wz, -self.wz_tope, self.wz_tope))

        # Umbral minimo util: Sport Mode ignora los comandos pequenos, asi que
        # un comando por debajo del minimo deja al robot quieto y parece que el
        # seguimiento no funciona.
        #
        # CUIDADO con el cero: la rampa deja valores como 1e-6 en vez de cero
        # exacto, y sin este epsilon el umbral los elevaba al minimo. Resultado:
        # el robot recibia orden de moverse estando la persona centrada y a la
        # distancia correcta.
        EPS = 1e-3
        if EPS < abs(objetivo_vx) < self.vx_util:
            objetivo_vx = float(np.sign(objetivo_vx) * self.vx_util)
        elif abs(objetivo_vx) <= EPS:
            objetivo_vx = 0.0

        if EPS < abs(objetivo_wz) < self.wz_util:
            objetivo_wz = float(np.sign(objetivo_wz) * self.wz_util)
        elif abs(objetivo_wz) <= EPS:
            objetivo_wz = 0.0

        # Rampa de aceleracion: sin esto, un salto de la deteccion produce un
        # tiron brusco en el robot.
        paso_max = self.acel_max * dt
        self.vx += float(np.clip(objetivo_vx - self.vx, -paso_max, paso_max))
        self.wz += float(np.clip(objetivo_wz - self.wz, -paso_max, paso_max))

        # La rampa deja residuos como 1e-6 al converger a cero. Sin limpiarlos,
        # el robot nunca queda completamente parado.
        if abs(self.vx) < 1e-3:
            self.vx = 0.0
        if abs(self.wz) < 1e-3:
            self.wz = 0.0

        self.vx = float(np.clip(self.vx, self.vx_lim_min, self.vx_lim_max))
        self.wz = float(np.clip(self.wz, self.wz_lim_min, self.wz_lim_max))
        return self.vx, 0.0, self.wz


# ===========================================================================
def main() -> int:
    import yaml

    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=["sim", "real"], default="sim")
    p.add_argument("--iface", default=None)
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--config", default=str(UC / "configs" / "following.yaml"))
    p.add_argument("--show", action="store_true", help="ventana con la deteccion")
    p.add_argument("--duration", type=float, default=300.0)
    p.add_argument("--dry-run", action="store_true",
                   help="detecta y calcula, pero NO envia velocidades")
    p.add_argument("--log", action="store_true", help="registrar el episodio")
    args = p.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    c = ct.load_contract(paths.CONTRACT)
    dds = c["dds"][args.mode]
    iface = args.iface or paths.iface() or dds["interface"]
    domain = paths.domain() if paths.domain() is not None else dds["domain_id"]

    print("uc04 — seguimiento de personas")
    print(f"  modo    : {args.mode} (domain {domain}, {iface})")
    print(f"  camara  : /dev/video{args.camera}")
    print(f"  ventana : {'si' if args.show else 'no'}")
    if args.dry_run:
        print("  DRY RUN: no se envia ninguna velocidad")
    print()

    if args.mode == "real" and not args.dry_run:
        print("  ROBOT FISICO. Confirma:")
        print("   - docs/SAFETY.md leido")
        print("   - espacio libre de 3 m alrededor")
        print("   - mando en la mano")
        if input("\n  Escribe 'si' para continuar: ").strip().lower() != "si":
            return 1

    print("cargando YOLO...")
    det = DetectorPersonas(modelo=cfg["modelo"], camara=args.camera,
                           ancho=cfg["ancho"], alto=cfg["alto"],
                           confianza_min=cfg["confianza_min"],
                           suavizado=cfg["suavizado"],
                           fallos_para_perder=cfg["fallos_para_perder"],
                           imgsz=cfg["imgsz"])
    print("detector listo")

    salida = None
    if not args.dry_run:
        Salida = SalidaSimulador if args.mode == "sim" else SalidaRobot
        salida = Salida(domain, iface)
        print(f"salida: {salida.nombre}")

    control = ControlSeguimiento(cfg["control"], c["commands"])

    if args.show:
        import cv2

    parar = {"flag": False}
    signal.signal(signal.SIGINT, lambda *_: parar.__setitem__("flag", True))

    filas: list = []
    t0 = time.monotonic()
    t_prev = t0
    n = 0
    n_visible = 0
    print("\nen marcha. Ctrl-C para parar.\n")

    try:
        while not parar["flag"] and time.monotonic() - t0 < args.duration:
            imagen, d = det.leer()
            if imagen is None:
                print("la camara ha dejado de dar imagen")
                break

            ahora = time.monotonic()
            dt = min(ahora - t_prev, 0.2)
            t_prev = ahora

            vx, vy, wz = control.paso(d, dt)
            if salida is not None:
                salida.enviar(vx, vy, wz)

            n += 1
            n_visible += int(d.visible)
            if args.log:
                filas.append([f"{ahora - t0:.3f}", int(d.visible),
                              f"{d.lateral:.4f}", f"{d.tamano:.4f}",
                              f"{d.confianza:.3f}", f"{vx:.4f}", f"{wz:.4f}"])

            if args.show:
                cv2.imshow("uc04 - seguimiento",
                           det.dibujar(imagen, d, (vx, vy, wz),
                                       control.objetivo))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            elif n % 15 == 0:
                estado = "persona" if d.visible else "  ---  "
                zg = "ZM" if abs(d.lateral) < control.zm_lateral else "  "
                za = "ZM" if abs(control.objetivo - d.tamano) < control.zm_tamano else "  "
                print(f"\r  {estado}  lat {d.lateral:+.2f}{zg}  "
                      f"tam {d.tamano:.2f}{za}(obj {control.objetivo:.2f})"
                      f"  ->  vx {vx:+.2f}  wz {wz:+.2f}   {det.fps:4.1f} fps  ",
                      end="", flush=True)

    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        return 1
    finally:
        print("\n\nparando...")
        if salida is not None:
            salida.cerrar()
        det.cerrar()
        if args.show:
            import cv2
            cv2.destroyAllWindows()

    dur = time.monotonic() - t0
    print(f"duracion {dur:.1f} s | {n} fotogramas | {det.fps:.1f} fps")
    if n:
        print(f"persona visible el {100 * n_visible / n:.0f} % del tiempo")

    if args.log and filas:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             cwd=paths.ROOT, capture_output=True,
                             text=True).stdout.strip() or "unknown"
        destino = (paths.EXPERIMENTS / "uc04_person_following"
                   / f"{datetime.now():%Y-%m-%dT%H%M%S}_{sha}_follow")
        destino.mkdir(parents=True, exist_ok=True)
        with open(destino / "metrics.csv", "w", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["t", "visible", "lateral", "tamano", "confianza",
                        "vx", "wz"])
            w.writerows(filas)
        (destino / "manifest.json").write_text(json.dumps({
            "usecase": "uc04_person_following",
            "fecha": datetime.now().isoformat(timespec="seconds"),
            "git_sha": sha,
            "modo": args.mode,
            "camara": args.camera,
            "config": cfg,
            "duracion_s": round(dur, 1),
            "fotogramas": n,
            "fps_medio": round(det.fps, 1),
            "visible_pct": round(100 * n_visible / max(n, 1), 1),
        }, indent=2, ensure_ascii=False))
        print(f"\nescrito: {destino}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
