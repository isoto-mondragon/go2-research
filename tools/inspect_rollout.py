#!/usr/bin/env python3
"""tools/inspect_rollout.py

Analiza el metrics_sim.csv de un run ya evaluado, para distinguir una marcha
real de un comportamiento degenerado.

POR QUE HACE FALTA
------------------
El seguimiento de velocidad por si solo no mide lo que parece. Una politica
que desliza el cuerpo sin levantar las patas puntua MEJOR que una que camina:
sigue el comando frontal, gasta poca energia y no se cae. Si esa es la metrica
central del barrido, la curva seria un artefacto y en el robot real esa
politica se caeria o destrozaria los pies.

EL DISCRIMINADOR
----------------
`height` se calcula desde los angulos articulares. Si el robot da pasos, las
patas se flexionan y la altura OSCILA. Si van rigidas, es una linea plana.

  desviacion tipica de height alta  + potencia alta  -> camina
  desviacion tipica de height ~0    + potencia baja  -> desliza o esta quieto

Se compara ademas contra el desplazamiento realmente medido, para detectar el
caso "no se mueve pero el evaluador dice que si".

Uso:
    python3 tools/inspect_rollout.py experiments/uc01_locomotion/<run_id>/
    python3 tools/inspect_rollout.py <run_a>/ <run_b>/     # comparar dos
"""

from __future__ import annotations

import argparse
import csv
import statistics as st
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def cargar(run_dir: Path) -> list[dict]:
    f = run_dir / "metrics_sim.csv"
    if not f.exists():
        sys.exit(f"No existe {f}. Ejecuta antes eval_sim.py con --out {run_dir}")
    with open(f) as fh:
        return list(csv.DictReader(fh))


def num(rows: list[dict], col: str) -> list[float]:
    out = []
    for r in rows:
        try:
            out.append(float(r[col]))
        except (KeyError, ValueError, TypeError):
            pass
    return out


def analizar(run_dir: Path) -> dict:
    rows = cargar(run_dir)
    nombre = run_dir.name
    print(f"\n{'=' * 78}")
    print(f"{nombre}")
    print(f"{'=' * 78}")
    print(f"muestras: {len(rows)}")

    segs = sorted({int(r["segment"]) for r in rows})
    print(f"\n  {'seg':>3} {'comando':<18} {'vx med':>8} {'h media':>8} {'h sd':>8} "
          f"{'P med':>7} {'tau':>6} {'veredicto':<22}")

    resumen = {}
    for s in segs:
        sub = [r for r in rows if int(r["segment"]) == s]
        vx_cmd = float(sub[0]["vx_cmd"])
        vy_cmd = float(sub[0]["vy_cmd"])
        wz_cmd = float(sub[0]["wz_cmd"])

        vx = num(sub, "vx_med")
        h = num(sub, "height")
        p = num(sub, "power_W")
        tau = num(sub, "tau_max")

        h_sd = st.pstdev(h) if len(h) > 1 else 0.0
        h_mean = st.mean(h) if h else 0.0
        p_mean = st.mean(p) if p else 0.0
        vx_mean = st.mean(vx) if vx else 0.0
        tau_mean = st.mean(tau) if tau else 0.0
        movimiento = abs(vx_mean) > 0.05 or abs(wz_cmd) > 0.1

        # Umbrales: 5 mm de oscilacion de altura es lo minimo que produce un
        # paso real; por debajo las patas van practicamente rigidas.
        if not movimiento:
            v = "quieto (esperado)"
        elif h_sd < 0.005 and p_mean < 8:
            v = "DESLIZA (patas rigidas)"
        elif h_sd < 0.005:
            v = "SOSPECHOSO (h plana)"
        elif h_sd > 0.010 and p_mean > 8:
            v = "camina"
        else:
            v = "marcha debil"

        print(f"  {s:>3} ({vx_cmd:+.1f},{vy_cmd:+.1f},{wz_cmd:+.1f})       "
              f"{vx_mean:8.3f} {h_mean:8.3f} {h_sd:8.4f} {p_mean:7.1f} "
              f"{tau_mean:6.1f} {v:<22}")
        resumen[s] = {"h_sd": h_sd, "p": p_mean, "vx": vx_mean, "veredicto": v}

    # --- desplazamiento acumulado, contraste independiente ---
    print("\n  desplazamiento estimado por integracion de la velocidad medida:")
    for s in segs:
        sub = [r for r in rows if int(r["segment"]) == s]
        vx_cmd = float(sub[0]["vx_cmd"])
        if abs(vx_cmd) < 0.05:
            continue
        ts = num(sub, "t")
        vx = num(sub, "vx_med")
        if len(ts) < 2 or not vx:
            continue
        dur = ts[-1] - ts[0]
        dist = st.mean(vx) * dur
        esperada = vx_cmd * dur
        print(f"    seg {s}: {dist:6.2f} m en {dur:.1f} s "
              f"(comandado {esperada:5.2f} m, {100 * dist / esperada:3.0f} %)")

    movs = [v for v in resumen.values() if "quieto" not in v["veredicto"]]
    desliza = sum(1 for v in movs if "DESLIZA" in v["veredicto"] or "SOSPECHOSO" in v["veredicto"])
    print(f"\n  segmentos con movimiento: {len(movs)} | "
          f"marcados como deslizamiento o sospechosos: {desliza}")
    if movs and desliza >= len(movs) / 2:
        print("  >>> Esta politica NO camina de forma fiable. Sus numeros de")
        print("      seguimiento de velocidad no son comparables con los de una")
        print("      politica que si camina.")
    return resumen


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("runs", nargs="+", help="carpetas de experimento a analizar")
    args = p.parse_args()

    todos = {}
    for r in args.runs:
        d = Path(r)
        if not d.is_absolute():
            d = REPO_ROOT / r
        todos[d.name] = analizar(d)

    if len(todos) > 1:
        print(f"\n{'=' * 78}")
        print("COMPARATIVA: desviacion tipica de la altura (oscilacion de las patas)")
        print(f"{'=' * 78}")
        nombres = list(todos)
        segs = sorted(set().union(*(set(v) for v in todos.values())))
        print(f"  {'seg':>3} " + " ".join(f"{n[-18:]:>20}" for n in nombres))
        for s in segs:
            fila = f"  {s:>3} "
            for n in nombres:
                v = todos[n].get(s)
                fila += f"{v['h_sd']:>20.4f}" if v else f"{'-':>20}"
            print(fila)
        print("\n  Una politica que camina oscila por encima de 0.010.")
        print("  Por debajo de 0.005 las patas van practicamente rigidas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
