# =============================================================================
# ESTE FICHERO NO SE TOCA.
# =============================================================================
"""usecases/uc06_lenguaje_natural/deploy/ejecutor.py

Valida el plan que ha propuesto el LLM y lo ejecuta con los verbos de `robot`.

    plan del LLM ──► validar (menu + topes) ──► mostrar ──► confirmar ──► robot.*

El LLM es una fuente NO fiable: aqui se comprueba todo antes de mover nada.
    - la accion tiene que estar en el menu (si no, se descarta el plan entero)
    - las cantidades se recortan a los topes de params.yaml (seccion mi_caso)
    - el plan tiene un maximo de pasos y de duracion
Los verbos de `robot` aplican despues sus propios limites de velocidad, rampa y
seguridad; esto es una capa mas, no la unica.
"""

from __future__ import annotations

import math

from traductor import ACCIONES


class PlanInvalido(Exception):
    """El plan del LLM no se puede ejecutar. El texto es para el usuario."""


def _topes(robot) -> dict:
    p = robot.param
    return {
        "vel": float(p("velocidad", 0.3)),          # m/s
        "vel_giro": float(p("velocidad_giro", 0.5)),  # rad/s
        "max_metros": float(p("max_metros", 3.0)),
        "max_grados": float(p("max_grados", 360.0)),
        "max_espera": float(p("max_espera", 10.0)),
        "max_pasos": int(p("max_pasos", 30)),
        "max_segundos": float(p("max_segundos_plan", 90.0)),
    }


def _segundos(accion: str, cantidad: float, t: dict) -> float:
    """Cuanto dura una accion. El robot va en lazo abierto: distancia = vel * tiempo."""
    if accion in ("avanzar", "retroceder"):
        return cantidad / t["vel"]
    if accion in ("girar_izquierda", "girar_derecha"):
        return math.radians(cantidad) / t["vel_giro"]
    if accion == "esperar":
        return cantidad
    return 0.0


def validar(respuesta: dict, robot) -> tuple[list[tuple[str, float]], list[str]]:
    """Devuelve (plan limpio, avisos). Lanza PlanInvalido si no hay nada que hacer."""
    t = _topes(robot)
    crudo = respuesta.get("plan") or []
    if not respuesta.get("entendido", False) or not crudo:
        raise PlanInvalido(respuesta.get("mensaje") or "No he entendido la orden.")
    if len(crudo) > t["max_pasos"]:
        raise PlanInvalido(f"El plan tiene {len(crudo)} pasos y el maximo es "
                           f"{t['max_pasos']}. Pide algo mas corto.")

    tope = {"avanzar": t["max_metros"], "retroceder": t["max_metros"],
            "girar_izquierda": t["max_grados"], "girar_derecha": t["max_grados"],
            "esperar": t["max_espera"]}
    plan, avisos = [], []
    for i, paso in enumerate(crudo, 1):
        accion = paso.get("accion")
        if accion not in ACCIONES:
            raise PlanInvalido(f"Paso {i}: la accion {accion!r} no existe. "
                               "No ejecuto nada.")
        try:
            cantidad = abs(float(paso.get("cantidad", 0)))
        except (TypeError, ValueError):
            raise PlanInvalido(f"Paso {i}: cantidad no valida. No ejecuto nada.")
        if not math.isfinite(cantidad):
            raise PlanInvalido(f"Paso {i}: cantidad no valida. No ejecuto nada.")
        if accion in tope and cantidad > tope[accion]:
            avisos.append(f"paso {i}: {accion} {cantidad:g} recortado a {tope[accion]:g}")
            cantidad = tope[accion]
        if accion in tope and cantidad == 0:
            avisos.append(f"paso {i}: {accion} sin cantidad, lo salto")
            continue
        plan.append((accion, cantidad if accion in tope else 0.0))

    total = sum(_segundos(a, c, t) for a, c in plan)
    if total > t["max_segundos"]:
        raise PlanInvalido(f"El plan duraria {total:.0f} s y el maximo es "
                           f"{t['max_segundos']:.0f} s. Pide algo mas corto.")
    if not plan:
        raise PlanInvalido("No queda ninguna accion que ejecutar.")
    return plan, avisos


def describir(plan: list[tuple[str, float]], robot) -> str:
    t = _topes(robot)
    lineas = []
    for i, (accion, cantidad) in enumerate(plan, 1):
        unidad = ACCIONES[accion][0]
        texto = accion if unidad == "-" else f"{accion} {cantidad:g} {unidad}"
        lineas.append(f"    {i}. {texto}")
    total = sum(_segundos(a, c, t) for a, c in plan)
    lineas.append(f"    (unos {total:.0f} s)")
    return "\n".join(lineas)


def ejecutar(plan: list[tuple[str, float]], robot) -> None:
    """Un verbo de `robot` por accion. Si salta una seguridad, `Parar` sube sola."""
    t = _topes(robot)
    for i, (accion, cantidad) in enumerate(plan, 1):
        print(f"  [{i}/{len(plan)}] {accion}" + (f" {cantidad:g}" if cantidad else ""))
        if accion == "levantarse":
            robot.levantarse()
        elif accion == "sentarse":
            robot.sentarse()
        elif accion == "avanzar":
            robot.avanzar(cantidad / t["vel"], vel=t["vel"])
        elif accion == "retroceder":
            robot.retroceder(cantidad / t["vel"], vel=t["vel"])
        elif accion == "girar_izquierda":
            robot.girar_izquierda(_segundos(accion, cantidad, t), vel=t["vel_giro"])
        elif accion == "girar_derecha":
            robot.girar_derecha(_segundos(accion, cantidad, t), vel=t["vel_giro"])
        elif accion == "esperar":
            robot.esperar(cantidad)
        elif accion == "parar":
            robot.parar()
    robot.parar()
