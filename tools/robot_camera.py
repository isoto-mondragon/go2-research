#!/usr/bin/env python3
"""tools/robot_camera.py

Ver por los ojos del robot: muestra en el PC lo que capta la camara frontal
del Go2, y mide a cuantos fotogramas y con cuanta latencia llega.

POR QUE VideoClient Y NO EL TOPIC DDS
-------------------------------------
El Go2 publica `frontvideostream`, pero es un flujo comprimido que habria que
decodificar a mano. El SDK ofrece `VideoClient`, un servicio peticion-respuesta
que devuelve fotogramas JPEG ya listos. Mas simple y suficiente para
percepcion.

La contrapartida: al ser peticion-respuesta, la tasa es menor que la de un
flujo continuo. Cuanto menor, lo mide este script, y de eso depende que se
pueda hacer seguimiento con ella.

LA CAMARA ESTA BAJA
-------------------
Va a unos 30 cm del suelo y apunta al frente: de una persona a dos metros ve
piernas y torso, casi nunca la cara. Es ojo de pez, asi que deforma los bordes.
Ambas cosas importan para el detector.

Uso:
    # Ver la camara
    python3 tools/robot_camera.py --iface enp3s0

    # Medir rendimiento sin ventana
    python3 tools/robot_camera.py --iface enp3s0 --no-show --seconds 20

    # Guardar un fotograma (util como foto de referencia)
    python3 tools/robot_camera.py --iface enp3s0 --save referencia.jpg
"""

from __future__ import annotations

import argparse
import statistics as st
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

V, R, G, Y, Z = "\033[34m", "\033[31m", "\033[32m", "\033[33m", "\033[0m"


class CamaraRobot:
    """Camara frontal del Go2 a traves de VideoClient."""

    def __init__(self, iface: str, domain: int = 0, timeout: float = 3.0,
                 init_dds: bool = True) -> None:
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize
        from unitree_sdk2py.go2.video.video_client import VideoClient

        if init_dds:
            ChannelFactoryInitialize(domain, iface)
        self.cliente = VideoClient()
        self.cliente.SetTimeout(timeout)
        self.cliente.Init()

        self.fps = 0.0
        self.latencias: list[float] = []
        self.fallos = 0
        self._t_prev = time.perf_counter()

    def leer(self) -> np.ndarray | None:
        """Devuelve un fotograma BGR, o None si la peticion falla."""
        t0 = time.perf_counter()
        try:
            codigo, datos = self.cliente.GetImageSample()
        except Exception:
            self.fallos += 1
            return None

        if codigo != 0 or not datos:
            self.fallos += 1
            return None

        self.latencias.append((time.perf_counter() - t0) * 1000.0)
        imagen = cv2.imdecode(np.frombuffer(bytes(datos), dtype=np.uint8),
                              cv2.IMREAD_COLOR)
        if imagen is None:
            self.fallos += 1
            return None

        ahora = time.perf_counter()
        dt = ahora - self._t_prev
        self._t_prev = ahora
        if dt > 0:
            self.fps = 0.8 * self.fps + 0.2 * (1.0 / dt)
        return imagen

    def resumen(self) -> str:
        if not self.latencias:
            return "sin fotogramas"
        lat = sorted(self.latencias)
        return (f"latencia media {st.mean(lat):.0f} ms, "
                f"mediana {lat[len(lat) // 2]:.0f} ms, "
                f"p95 {lat[int(0.95 * len(lat))]:.0f} ms")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--iface", required=True)
    p.add_argument("--domain", type=int, default=0)
    p.add_argument("--seconds", type=float, default=30.0)
    p.add_argument("--no-show", action="store_true", help="sin ventana, solo medir")
    p.add_argument("--save", default=None, help="guardar el primer fotograma valido")
    p.add_argument("--detect", action="store_true",
                   help="ademas, detectar personas con YOLO")
    # La camara del Go2 entrega 1920x1080, que no cabe en una pantalla de
    # portatil y ademas es un desperdicio: YOLO infiere a 320 px. Se escala
    # para mostrar y para detectar; la imagen original solo se usa si se guarda.
    p.add_argument("--width", type=int, default=960,
                   help="ancho al que escalar (0 = tamano original)")
    args = p.parse_args()

    print(f"\n{V}=== Camara frontal del Go2 ==={Z}")
    print(f"  interfaz {args.iface}, domain {args.domain}\n")

    try:
        cam = CamaraRobot(args.iface, args.domain)
    except Exception as e:
        print(f"{R}No se puede abrir VideoClient: {e}{Z}")
        print("Comprueba que el robot responde:  ./env/go2_net.sh probe")
        return 2

    yolo = None
    if args.detect:
        print("cargando YOLO...")
        from ultralytics import YOLO
        yolo = YOLO("yolo11n.pt")

    print("pidiendo el primer fotograma...")
    imagen = None
    t0 = time.monotonic()
    while imagen is None and time.monotonic() - t0 < 10:
        imagen = cam.leer()
        if imagen is None:
            time.sleep(0.2)

    if imagen is None:
        print(f"\n{R}No llega imagen.{Z}")
        print("Posibles causas:")
        print("  - el servicio de video no esta activo en el robot")
        print("  - la app movil esta conectada y ocupa el canal")
        print("  - el firmware no expone VideoClient")
        return 2

    h, w = imagen.shape[:2]
    print(f"{G}imagen recibida{Z}   {w}x{h}   {imagen.dtype}")

    if args.save:
        destino = Path(args.save)
        cv2.imwrite(str(destino), imagen)
        print(f"{G}guardado: {destino.resolve()}{Z}")

    print(f"\ncapturando {args.seconds:.0f} s...")
    if not args.no_show:
        print("  'q' para salir, 's' para guardar el fotograma actual\n")

    n = 0
    n_personas = 0
    guardados = 0
    t0 = time.monotonic()

    try:
        while time.monotonic() - t0 < args.seconds:
            imagen = cam.leer()
            if imagen is None:
                continue
            n += 1

            if args.width and imagen.shape[1] > args.width:
                escala = args.width / imagen.shape[1]
                imagen = cv2.resize(imagen, None, fx=escala, fy=escala,
                                    interpolation=cv2.INTER_AREA)
            h, w = imagen.shape[:2]

            if yolo is not None:
                res = yolo.predict(imagen, imgsz=320, conf=0.4, classes=[0],
                                   verbose=False)[0]
                cajas = res.boxes
                n_personas += int(len(cajas) > 0)
                for caja in cajas:
                    x1, y1, x2, y2 = (int(v) for v in caja.xyxy[0])
                    conf = float(caja.conf[0])
                    cv2.rectangle(imagen, (x1, y1), (x2, y2), (0, 200, 0), 2)
                    cv2.putText(imagen, f"{conf:.2f}", (x1, max(y1 - 8, 14)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 0), 1)
                    alto = (y2 - y1) / imagen.shape[0]
                    lat = ((x1 + x2) / 2 - w / 2) / (w / 2)
                    cv2.putText(imagen, f"lat {lat:+.2f}  tam {alto:.2f}",
                                (x1, min(y2 + 18, imagen.shape[0] - 6)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 220), 1)

            if not args.no_show:
                cv2.line(imagen, (w // 2, 0), (w // 2, h), (80, 80, 80), 1)
                cv2.putText(imagen, f"{cam.fps:4.1f} fps", (10, 24),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220, 220, 220), 2)
                if n == 1:
                    cv2.namedWindow("camara del Go2", cv2.WINDOW_NORMAL)
                    cv2.resizeWindow("camara del Go2", w, h)
                cv2.imshow("camara del Go2", imagen)
                k = cv2.waitKey(1) & 0xFF
                if k == ord("q"):
                    break
                if k == ord("s"):
                    guardados += 1
                    nombre = f"captura_{guardados:02d}.jpg"
                    cv2.imwrite(nombre, imagen)
                    print(f"\n  guardado {nombre}")
            elif n % 10 == 0:
                print(f"\r  {n} fotogramas   {cam.fps:4.1f} fps   "
                      f"{cam.fallos} fallos", end="", flush=True)

    except KeyboardInterrupt:
        pass
    finally:
        if not args.no_show:
            cv2.destroyAllWindows()

    dur = time.monotonic() - t0
    print(f"\n\n{V}--- Resultado ---{Z}")
    print(f"  resolucion       {w}x{h}")
    print(f"  fotogramas       {n} en {dur:.1f} s  ->  {n / dur:.1f} fps")
    print(f"  fallos           {cam.fallos}")
    print(f"  {cam.resumen()}")
    if yolo is not None and n:
        print(f"  persona detectada en el {100 * n_personas / n:.0f} % de los fotogramas")

    fps = n / dur
    print()
    if fps >= 10:
        print(f"  {G}Suficiente para seguimiento en tiempo real.{Z}")
    elif fps >= 4:
        print(f"  {Y}Justo. El seguimiento ira a tirones; conviene subir las")
        print(f"  zonas muertas y bajar las ganancias.{Z}")
    else:
        print(f"  {R}Demasiado lento para seguimiento desde el PC.{Z}")
        print("  La alternativa es ejecutar la percepcion en la Jetson del")
        print("  robot (192.168.123.18), donde el video no sale por la red.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
