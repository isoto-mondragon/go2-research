#!/usr/bin/env python3
"""usecases/uc03_energy/eval/plot_cot.py

Genera las figuras del caso de uso uc03 a partir de un experimento ya medido.

Regla del repositorio: las figuras se generan con un comando y NUNCA se editan
a mano. Si una figura no se puede regenerar, no entra en el paper.

Uso:
    python3 usecases/uc03_energy/eval/plot_cot.py experiments/uc03_energy/<run_id>
    python3 usecases/uc03_energy/eval/plot_cot.py <run_a> <run_b>   # comparar
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")          # sin ventana: esto corre dentro del contenedor
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from go2core import paths      # noqa: E402

FIGURAS = paths.RESULTS / "figures"


def cargar(run: Path) -> dict:
    f = run / "manifest.json"
    if not f.exists():
        sys.exit(f"No existe {f}. ¿Es una carpeta de experimento?")
    return json.loads(f.read_text())


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("runs", nargs="+")
    p.add_argument("--out", default=None, help="carpeta de salida de las figuras")
    args = p.parse_args()

    salida = Path(args.out) if args.out else FIGURAS
    salida.mkdir(parents=True, exist_ok=True)

    datos = []
    for r in args.runs:
        d = Path(r)
        if not d.is_absolute():
            d = paths.ROOT / r
        m = cargar(d)
        etiqueta = f"{m['locomocion']} ({m['modo']})"
        datos.append((etiqueta, m))
        print(f"cargado: {d.name} -> {etiqueta}")

    # ---------------- figura 1: CoT frente a velocidad ----------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))

    for etiqueta, m in datos:
        res = [r for r in m["resultados"] if r.get("CoT_mecanico")]
        if not res:
            continue
        v = [r["v_med"] for r in res]
        cot = [r["CoT_mecanico"] for r in res]
        ax1.plot(v, cot, "o-", label=f"{etiqueta}, mecánico")

        ele = [(r["v_med"], r["CoT_electrico"]) for r in res if r.get("CoT_electrico")]
        if ele:
            ax1.plot([x for x, _ in ele], [y for _, y in ele], "s--",
                     label=f"{etiqueta}, eléctrico")

        mejor = min(res, key=lambda r: r["CoT_mecanico"])
        ax1.annotate(f"mín {mejor['CoT_mecanico']:.2f}\n@ {mejor['v_med']:.2f} m/s",
                     (mejor["v_med"], mejor["CoT_mecanico"]),
                     textcoords="offset points", xytext=(8, 12), fontsize=8)

    ax1.set_xlabel("velocidad medida (m/s)")
    ax1.set_ylabel("coste de transporte (adimensional)")
    ax1.set_title("Coste de transporte frente a velocidad")
    ax1.grid(alpha=0.3)
    ax1.legend(fontsize=8)

    # ---------------- figura 2: potencia frente a velocidad ----------------
    for etiqueta, m in datos:
        res = [r for r in m["resultados"] if r.get("v_med")]
        if not res:
            continue
        v = [r["v_med"] for r in res]
        ax2.plot(v, [r["P_mecanica_W"] for r in res], "o-",
                 label=f"{etiqueta}, mecánica")
        ele = [(r["v_med"], r["P_electrica_W"]) for r in res if r.get("P_electrica_W")]
        if ele:
            ax2.plot([x for x, _ in ele], [y for _, y in ele], "s--",
                     label=f"{etiqueta}, eléctrica")

    ax2.set_xlabel("velocidad medida (m/s)")
    ax2.set_ylabel("potencia (W)")
    ax2.set_title("Potencia frente a velocidad")
    ax2.grid(alpha=0.3)
    ax2.legend(fontsize=8)

    m0 = datos[0][1]
    fig.suptitle(f"Unitree Go2, {m0['masa_kg']} kg — uc03", fontsize=11)
    fig.tight_layout()

    f1 = salida / "uc03_cot_vs_velocidad.png"
    fig.savefig(f1, dpi=150)
    print(f"escrito: {f1}")

    # ---------------- tabla en markdown ----------------
    lineas = ["# uc03 — coste de transporte", "",
              f"Masa: {m0['masa_kg']} kg. Locomoción: {m0['locomocion']}. "
              f"Modo: {m0['modo']}. Commit: {m0['git_sha']}.", "",
              "| v comandada | v medida | seguimiento | P mec (W) | "
              "P elec (W) | CoT mec | CoT elec | h sd |",
              "|---|---|---|---|---|---|---|---|"]
    for r in m0["resultados"]:
        def f(x, n=2):
            return "-" if x is None else f"{x:.{n}f}"
        seg = "-" if r.get("seguimiento") is None else f"{100 * r['seguimiento']:.0f} %"
        lineas.append(
            f"| {r['v_cmd']:.2f} | {f(r.get('v_med'), 3)} | {seg} | "
            f"{f(r.get('P_mecanica_W'), 1)} | {f(r.get('P_electrica_W'), 1)} | "
            f"{f(r.get('CoT_mecanico'), 3)} | {f(r.get('CoT_electrico'), 3)} | "
            f"{f(r.get('h_sd'), 4)} |")
    lineas += ["", "## Limitaciones", "", m0.get("limitaciones", "")]

    tabla = paths.RESULTS / "tables" / "uc03_cot.md"
    tabla.parent.mkdir(parents=True, exist_ok=True)
    tabla.write_text("\n".join(lineas) + "\n")
    print(f"escrito: {tabla}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
