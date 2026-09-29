# Ejemplo 4: gira hacia la persona que ve la camara. No avanza.
# Ensena percepcion: camara + YOLO. En el robot real usa su camara frontal;
# en simulacion no hay camara del robot y usa la webcam del portatil.
# Si no hay camara, avisa y se queda parado en vez de fallar.
import sys

from go2core import paths   # main.py ya lo tiene disponible

# No se calcula la ruta desde este fichero: al copiarlo encima de mi_caso.py
# cambia de carpeta y la cuenta dejaria de salir.
sys.path.insert(0, str(paths.USECASES / "uc04_person_following"))

detector = None


def preparar(modo, iface, domain):
    """Se llama una vez antes de empezar: cargar YOLO tarda unos segundos."""
    global detector
    try:
        from perception.detector import DetectorPersonas
        fuente = "robot" if modo == "real" else "webcam"
        detector = DetectorPersonas(fuente=fuente, iface=iface, domain=domain,
                                    init_dds=False)
    except Exception as e:
        print(f"  AVISO: sin camara ({type(e).__name__}: {e}). Me quedo parado.")


def decidir(tel, t):
    if detector is None:
        return 0.0, 0.0, 0.0
    imagen, persona = detector.leer()
    if imagen is None or not persona.visible:
        return 0.0, 0.0, 0.0
    # persona.lateral va de -1 (izquierda) a +1 (derecha). Si esta a la
    # derecha hay que girar a la derecha, que es wz negativo.
    if abs(persona.lateral) < 0.15:     # ya esta centrada: no tiembles
        return 0.0, 0.0, 0.0
    return 0.0, 0.0, -1.2 * persona.lateral
