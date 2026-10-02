# Habla con el robot en lenguaje natural. Escribes una orden, Gemini la traduce
# a un plan de acciones, tu la revisas y el robot la ejecuta.
# Vale igual para el simulador (--mode sim) y para el robot (--mode real).
#
# Lo que entiende (menu cerrado, en deploy/traductor.py):
#   levantarse, sentarse, avanzar (metros), retroceder (metros),
#   girar_izquierda (grados), girar_derecha (grados), esperar (segundos), parar
#
# Para anadir una accion: ponla en ACCIONES (deploy/traductor.py) y en
# ejecutar() (deploy/ejecutor.py). El LLM la usara sin mas cambios.
# Los limites (metros maximos, velocidad...) estan en configs/params.yaml.

import select
import sys

from ejecutor import PlanInvalido, describir, ejecutar, validar
from traductor import ErrorLLM, Traductor


def leer(robot, pregunta):
    """input() que sigue atento a Ctrl-C y a --duration. None si hay que salir."""
    print(pregunta, end="", flush=True)
    while robot.activo():
        if select.select([sys.stdin], [], [], 0.2)[0]:
            linea = sys.stdin.readline()
            return linea.strip() if linea else None      # None: fin de entrada
    return None


def caso(robot):
    try:
        traductor = Traductor(robot.modo, modelo=robot.param("modelo", "gemini-2.5-flash"))
    except ErrorLLM as e:
        print(f"\n{e}")
        return

    print(f"\nModo {robot.modo}. Dime que quieres que haga. 'salir' para terminar.\n")
    while robot.activo():
        frase = leer(robot, "> ")
        if frase is None or frase.lower() in ("salir", "exit", "q"):
            break
        if not frase:
            continue

        try:
            respuesta = traductor.traducir(frase)
            plan, avisos = validar(respuesta, robot)
        except (ErrorLLM, PlanInvalido) as e:
            print(f"  {e}\n")
            continue

        print(f"  {respuesta['mensaje']}")
        print(describir(plan, robot))
        for aviso in avisos:
            print(f"  AVISO: {aviso}")

        # En el robot real siempre se confirma; en simulacion, si lo pide params.yaml.
        if robot.es_real or robot.param("confirmar_en_sim", False):
            if (leer(robot, "  Ejecutar? [s/N] ") or "").lower() not in ("s", "si", "y"):
                print("  Cancelado.\n")
                continue

        ejecutar(plan, robot)
        print()
