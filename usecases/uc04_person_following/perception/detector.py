#!/usr/bin/env python3
"""usecases/uc04_person_following/perception/detector.py

Detección de personas con YOLO, orientada al seguimiento.

Convierte una imagen en dos magnitudes que el control puede usar:

    desplazamiento lateral   dónde está la persona respecto al centro,
                             normalizado a [-1, +1]
    tamaño aparente          qué fracción del alto de la imagen ocupa,
                             que sirve de estimación inversa de la distancia

POR QUÉ NO SE DETECTAN CARAS
----------------------------
La cámara del Go2 está a unos 30 cm del suelo y apunta al frente: de una
persona a dos metros ve piernas y torso, casi nunca la cara. Por eso se usa la
clase `person` de YOLO, que se dispara igual con cuerpos parciales, en lugar de
un detector facial.

Eso tiene una consecuencia para el control: el alto del recuadro NO es
proporcional a la distancia de forma fiable, porque a distancias cortas la
persona se sale por arriba del encuadre y el recuadro deja de crecer. El
control lo tiene en cuenta con una zona muerta amplia y límites de velocidad.

ESTABILIDAD
-----------
YOLO puede perder la detección en fotogramas sueltos, o saltar entre dos
personas. Para que el robot no dé bandazos:

  - se elige siempre la detección MÁS GRANDE (la persona más cercana)
  - se suaviza con media exponencial
  - una pérdida breve no cuenta como pérdida: hay que fallar varios
    fotogramas seguidos

Uso como programa, para probar la cámara sin mover el robot:

    python3 usecases/uc04_person_following/perception/detector.py --show
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Deteccion:
    """Una persona detectada, en coordenadas normalizadas."""

    visible: bool
    lateral: float = 0.0      # -1 izquierda, 0 centro, +1 derecha
    tamano: float = 0.0       # fracción del alto de la imagen [0, 1]
    confianza: float = 0.0
    caja: tuple[int, int, int, int] | None = None
    perdida_s: float = 0.0    # segundos desde la última detección


class DetectorPersonas:
    """YOLO sobre una cámara, con suavizado y gestión de pérdidas."""

    def __init__(self, modelo: str = "yolo11n.pt", camara: int = 0,
                 ancho: int = 640, alto: int = 480, confianza_min: float = 0.4,
                 suavizado: float = 0.6, fallos_para_perder: int = 5,
                 imgsz: int = 320) -> None:
        from ultralytics import YOLO

        self.yolo = YOLO(modelo)
        self.confianza_min = confianza_min
        self.suavizado = suavizado
        self.fallos_para_perder = fallos_para_perder
        self.imgsz = imgsz

        self.cap = cv2.VideoCapture(camara)
        if not self.cap.isOpened():
            raise RuntimeError(
                f"No se puede abrir /dev/video{camara}.\n"
                "En Linux hay que pasar la camara al contenedor: usa ./go2 en\n"
                "lugar de `docker compose`, que es quien carga el override."
            )
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, ancho)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, alto)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # imagen reciente, no en cola

        self._lat = 0.0
        self._tam = 0.0
        self._fallos = 0
        self._ultima = 0.0
        self.fps = 0.0
        self._t_prev = time.perf_counter()

    # ------------------------------------------------------------------
    def leer(self) -> tuple[np.ndarray | None, Deteccion]:
        ok, imagen = self.cap.read()
        if not ok:
            return None, Deteccion(visible=False, perdida_s=self._perdida())

        h, w = imagen.shape[:2]
        # classes=[0] restringe a la clase `person` de COCO: no interesa el
        # resto y filtrar en la inferencia es mas rapido que despues.
        res = self.yolo.predict(imagen, imgsz=self.imgsz, conf=self.confianza_min,
                                classes=[0], verbose=False)[0]

        mejor, mejor_area = None, 0.0
        for caja in res.boxes:
            x1, y1, x2, y2 = (float(v) for v in caja.xyxy[0])
            area = (x2 - x1) * (y2 - y1)
            if area > mejor_area:
                mejor_area, mejor = area, (x1, y1, x2, y2, float(caja.conf[0]))

        ahora = time.perf_counter()
        dt = ahora - self._t_prev
        self._t_prev = ahora
        if dt > 0:
            self.fps = 0.8 * self.fps + 0.2 * (1.0 / dt)

        if mejor is None:
            self._fallos += 1
            visible = self._fallos < self.fallos_para_perder
            return imagen, Deteccion(visible=visible, lateral=self._lat,
                                     tamano=self._tam,
                                     perdida_s=self._perdida())

        x1, y1, x2, y2, conf = mejor
        self._fallos = 0
        self._ultima = time.monotonic()

        lat = ((x1 + x2) / 2.0 - w / 2.0) / (w / 2.0)
        tam = (y2 - y1) / h

        a = self.suavizado
        self._lat = a * self._lat + (1 - a) * lat
        self._tam = a * self._tam + (1 - a) * tam

        return imagen, Deteccion(visible=True, lateral=self._lat,
                                 tamano=self._tam, confianza=conf,
                                 caja=(int(x1), int(y1), int(x2), int(y2)))

    def _perdida(self) -> float:
        return 0.0 if self._ultima == 0.0 else time.monotonic() - self._ultima

    # ------------------------------------------------------------------
    def dibujar(self, imagen: np.ndarray, d: Deteccion,
                cmd: tuple[float, float, float] | None = None,
                objetivo_tamano: float = 0.6) -> np.ndarray:
        """Superpone la detección y el comando sobre la imagen."""
        h, w = imagen.shape[:2]
        vis = imagen.copy()

        cv2.line(vis, (w // 2, 0), (w // 2, h), (80, 80, 80), 1)

        if d.caja:
            x1, y1, x2, y2 = d.caja
            color = (0, 200, 0) if d.visible else (0, 140, 200)
            cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)
            cv2.circle(vis, ((x1 + x2) // 2, (y1 + y2) // 2), 5, color, -1)
            cv2.putText(vis, f"{d.confianza:.2f}", (x1, max(y1 - 8, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        estado = "SIGUIENDO" if d.visible else "SIN PERSONA"
        color = (0, 200, 0) if d.visible else (0, 0, 220)
        cv2.putText(vis, estado, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    color, 2)
        cv2.putText(vis, f"lateral {d.lateral:+.2f}   tamano {d.tamano:.2f} "
                         f"(objetivo {objetivo_tamano:.2f})",
                    (10, h - 34), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1)

        if cmd is not None:
            vx, vy, wz = cmd
            cv2.putText(vis, f"vx {vx:+.2f}   vy {vy:+.2f}   wz {wz:+.2f}",
                        (10, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (0, 220, 220), 1)

        cv2.putText(vis, f"{self.fps:4.1f} fps", (w - 95, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
        return vis

    def cerrar(self) -> None:
        self.cap.release()


# ===========================================================================
if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Prueba del detector, sin mover el robot")
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--show", action="store_true", help="abrir ventana")
    p.add_argument("--seconds", type=float, default=30.0)
    args = p.parse_args()

    det = DetectorPersonas(camara=args.camera)
    print("detector listo. Ctrl-C para salir.\n")
    t0 = time.monotonic()
    try:
        while time.monotonic() - t0 < args.seconds:
            img, d = det.leer()
            if img is None:
                print("sin imagen de la camara")
                break
            if args.show:
                cv2.imshow("uc04 - deteccion", det.dibujar(img, d))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            else:
                estado = "persona" if d.visible else "   ---  "
                print(f"\r  {estado}  lateral {d.lateral:+.2f}  "
                      f"tamano {d.tamano:.2f}  {det.fps:4.1f} fps", end="")
    except KeyboardInterrupt:
        pass
    finally:
        det.cerrar()
        cv2.destroyAllWindows()
        print("\nfin")
