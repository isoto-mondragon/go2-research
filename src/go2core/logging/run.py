"""Identidad y metadatos de un experimento.

Regla del proyecto: ningun resultado sale de una carpeta sin manifest.json.
El run_id incluye el sha de git para que la pregunta "con que codigo saliste
esta figura" se responda mirando el nombre del directorio.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return "unknown"


def git_sha(short: bool = True) -> str:
    args = ["rev-parse"] + (["--short"] if short else []) + ["HEAD"]
    return _git(*args)


def git_dirty() -> bool:
    return bool(_git("status", "--porcelain"))


def make_run_id(tag: str) -> str:
    """<ISO-timestamp>_<sha>_<tag>, p.ej. 2026-09-14T1032_a3f9c21_kd05"""
    stamp = datetime.now().strftime("%Y-%m-%dT%H%M")
    return f"{stamp}_{git_sha()}_{tag}"


def create_run(usecase: str, tag: str, config: dict, extra: dict | None = None) -> Path:
    """Crea experiments/<usecase>/<run_id>/ con manifest.json y snapshot de config."""
    run_id = make_run_id(tag)
    run_dir = REPO_ROOT / "experiments" / usecase / run_id
    (run_dir / "checkpoints").mkdir(parents=True, exist_ok=True)

    manifest = {
        "run_id": run_id,
        "usecase": usecase,
        "tag": tag,
        "created": datetime.now().isoformat(timespec="seconds"),
        "git": {"sha": git_sha(short=False), "dirty": git_dirty()},
        "platform": {
            "python": sys.version.split()[0],
            "os": platform.platform(),
            "machine": platform.machine(),
        },
        # Rellenar desde env/HARDWARE.md cuando se ejecute sobre el robot real.
        "robot": {"model": None, "firmware": None, "serial": None, "lidar": None},
        "config": config,
    }
    if extra:
        manifest.update(extra)

    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    if git_dirty():
        print("  [!] AVISO: hay cambios sin commitear. Este run NO es reproducible.")

    print(f"  run creado: {run_dir.relative_to(REPO_ROOT)}")
    return run_dir
