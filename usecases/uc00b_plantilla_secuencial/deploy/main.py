#!/usr/bin/env python3
# =============================================================================
# ESTE FICHERO NO SE TOCA.
# Tu codigo va en mi_caso.py, en la carpeta de arriba (uc00b_plantilla_secuencial/).
# =============================================================================
"""usecases/uc00b_plantilla_secuencial/deploy/main.py

Arranca el caso de uso: prepara la conexion con el simulador o el robot, crea el
objeto `robot` (ver robot.py) y ejecuta `caso(robot)` de ../mi_caso.py.

    argumentos ──► conexion (DDS) ──► robot ──► mi_caso.caso(robot) ──► parada segura

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
    - para si la telemetria se congela o si el robot se inclina demasiado
    - Ctrl-C, error o fin de --duration envian velocidad cero antes de salir
    - --dry-run ejecuta el caso entero pero NO envia nada al robot

Uso:
    # Comprobacion sin mover nada (funciona incluso sin simulador)
    python3 usecases/uc00b_plantilla_secuencial/deploy/main.py --mode sim --dry-run

    # Simulacion: antes, simulador y `run_policy.py --mode sim --teleop`
    python3 usecases/uc00b_plantilla_secuencial/deploy/main.py --mode sim

    # Robot real: primero --dry-run, mando en la mano (L2+B amortigua)
    python3 usecases/uc00b_plantilla_secuencial/deploy/main.py --mode real --dry-run
"""

from __future__ import annotations

import argparse
import csv
import signal
import sys
import traceback
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from go2core import paths                     # noqa: E402
from go2core.control import contract as ct    # noqa: E402
from go2core.logging.run import create_run    # noqa: E402

from robot import (Parar, Robot, SalidaRobot, SalidaSimulador,  # noqa: E402
                   Telemetria)

UC = Path(__file__).resolve().parents[1]
# mi_caso.py vive en la carpeta del caso de uso, no en deploy/.
sys.path.insert(0, str(UC))
import mi_caso  # noqa: E402

# El nombre de la carpeta es el nombre del caso de uso en experiments/, asi
# que al renombrar la plantilla no hay que tocar nada aqui.
USECASE = UC.name


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
    p.add_argument("--duration", type=float, default=60.0,
                   help="segundos maximos; corta el caso aunque no haya terminado")
    p.add_argument("--dry-run", action="store_true",
                   help="ejecuta el caso pero NO envia velocidades")
    p.add_argument("--log", action="store_true",
                   help="registrar en experiments/ con manifest.json")
    p.add_argument("--tag", default="run", help="etiqueta del experimento")
    args = p.parse_args()

    if not hasattr(mi_caso, "caso"):
        raise SystemExit("mi_caso.py no define `def caso(robot):`")

    cfg = yaml.safe_load(Path(args.config).read_text())
    c = ct.load_contract(paths.CONTRACT)
    dds = c["dds"][args.mode]
    iface = args.iface or paths.iface() or dds["interface"]
    domain = paths.domain() if paths.domain() is not None else dds["domain_id"]
    real = args.mode == "real"
    seg = cfg["seguridad"]

    print(f"{USECASE}")
    print(f"  modo     : {args.mode} (domain {domain}, {iface})")
    print(f"  maximo   : {args.duration:.0f} s")
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

    parada = {"flag": False}
    signal.signal(signal.SIGINT, lambda *_: parada.__setitem__("flag", True))
    signal.signal(signal.SIGTERM, lambda *_: parada.__setitem__("flag", True))

    robot = Robot(cfg=cfg, contrato=c, modo=args.mode, iface=iface, domain=domain,
                  tel=tel, salida=salida, dry_run=args.dry_run,
                  duracion=args.duration, parada=parada)

    run_dir = None
    if args.log:
        run_dir = create_run(USECASE, args.tag, config={
            "args": vars(args), "iface": iface, "domain": domain,
            "telemetria": tel is not None, "params": cfg,
        })

    motivo = "el caso ha terminado"
    print("\nen marcha. Ctrl-C para parar.\n")
    try:
        mi_caso.caso(robot)
    except Parar as e:
        motivo = str(e)
    except Exception as e:
        # Un fallo en el caso: se ensena donde, y se para el robot igualmente.
        traceback.print_exc()
        motivo = f"error en mi_caso.py: {type(e).__name__}: {e}"
    finally:
        # Siempre velocidad cero, pase lo que pase.
        if salida is not None:
            salida.cerrar()
        robot.cerrar()

    # Si el caso termino porque se acabo el tiempo o se pulso Ctrl-C sin que
    # ningun verbo lo notara (p. ej. un `while robot.activo()`), el motivo esta
    # en el robot.
    if motivo == "el caso ha terminado" and robot.motivo:
        motivo = robot.motivo
    print(f"\nfin: {motivo}. {len(robot.filas)} pasos en {robot.tiempo():.1f} s.")

    if run_dir is not None:
        with open(run_dir / "metrics.csv", "w", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["t", "vx", "vy", "wz", "inclinacion_rad",
                        "bateria_pct", "temp_max_c"])
            w.writerows(robot.filas)
        print(f"escrito: {run_dir}")
        print(f"medir:   python3 usecases/{USECASE}/eval/measure.py "
              f"--run {run_dir}")

    return 0 if motivo in ("el caso ha terminado", "fin de --duration",
                           "interrumpido") else 1


if __name__ == "__main__":
    raise SystemExit(main())
