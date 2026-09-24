#!/usr/bin/env python3
"""tools/inventory_robot.py

Inventario del Unitree Go2 leyendo por DDS. NO envia ningun comando: el robot
no se mueve.

Recoge todo lo que se puede averiguar sin la app movil:

  - que topics publica el robot, y por tanto que sensores tiene
  - si hay LiDAR, y de que tipo
  - estado y salud de la bateria: carga, ciclos, temperatura, celdas
  - los 12 motores: posicion, par, temperatura
  - IMU y sensores de fuerza en los pies
  - frecuencia real de rt/lowstate

Lo que NO puede leer y hay que anotar a mano: version de firmware (esta en la
app, en Device > About), numero de serie, y la masa (hay que pesarlo).

Genera un borrador de env/HARDWARE.md con lo que ha podido determinar.

Uso:
    python3 tools/inventory_robot.py --iface enp3s0
    python3 tools/inventory_robot.py --iface enp3s0 --write
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from go2core import paths  # noqa: E402

V, R, G, Y, Z = "\033[34m", "\033[31m", "\033[32m", "\033[33m", "\033[0m"

# Topics conocidos del Go2 y que implica cada uno
PISTAS = {
    "rt/lowstate": "estado de bajo nivel (12 motores, IMU, pies, bateria)",
    "rt/lowcmd": "control de bajo nivel disponible",
    "rt/sportmodestate": "Sport Mode activo (odometria del tronco)",
    "rt/wirelesscontroller": "mando fisico emparejado",
    "rt/utlidar/cloud": "LiDAR L1 integrado (nube de puntos)",
    "rt/utlidar/imu": "IMU del LiDAR L1",
    "rt/utlidar/voxel_map": "mapa de voxeles del LiDAR",
    "rt/utlidar/robot_pose": "pose estimada por el LiDAR",
    "rt/livox/lidar": "LiDAR Livox Mid-360 (EDU Plus)",
    "rt/frontvideostream": "camara frontal ojo de pez",
    "rt/api/videohub/request": "servicio de video",
    "rt/multiplestate": "estado multiple",
    "rt/lf/lowstate": "lowstate a baja frecuencia",
}


def listar_topics(domain: int) -> list[str]:
    try:
        r = subprocess.run(["ros2", "topic", "list"], capture_output=True,
                           text=True, timeout=25)
        return sorted(t.strip().lstrip("/") for t in r.stdout.split("\n") if t.strip())
    except Exception as e:
        print(f"{Y}no se han podido listar los topics: {e}{Z}")
        return []


class Lector:
    def __init__(self) -> None:
        self.msg = None
        self.n = 0
        self.t0 = None
        self.t1 = None

    def on(self, m) -> None:
        self.msg = m
        self.n += 1
        ahora = time.monotonic()
        if self.t0 is None:
            self.t0 = ahora
        self.t1 = ahora

    def hz(self) -> float:
        if self.n < 2 or self.t1 <= self.t0:
            return 0.0
        return (self.n - 1) / (self.t1 - self.t0)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--iface", required=True)
    p.add_argument("--domain", type=int, default=0)
    p.add_argument("--seconds", type=float, default=10.0)
    p.add_argument("--write", action="store_true",
                   help="escribir el borrador en env/HARDWARE.md")
    args = p.parse_args()

    print(f"\n{V}=== Inventario del Go2 (solo lectura) ==={Z}")
    print(f"  interfaz {args.iface}, domain {args.domain}\n")

    from unitree_sdk2py.core.channel import (ChannelFactoryInitialize,
                                             ChannelSubscriber)
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_

    ChannelFactoryInitialize(args.domain, args.iface)
    lec = Lector()
    ChannelSubscriber("rt/lowstate", LowState_).Init(lec.on, 10)

    print(f"escuchando {args.seconds:.0f} s...")
    t0 = time.monotonic()
    while time.monotonic() - t0 < args.seconds:
        time.sleep(0.2)

    if lec.msg is None:
        print(f"\n{R}No llega rt/lowstate.{Z}")
        print("Comprueba ./env/go2_net.sh probe y que la app movil este cerrada.")
        return 2

    m = lec.msg
    inv: dict = {"fecha": datetime.now().isoformat(timespec="seconds"),
                 "interfaz": args.iface, "domain": args.domain}

    # ---------------- topics ----------------
    print(f"\n{V}--- Topics publicados ---{Z}")
    topics = listar_topics(args.domain)
    inv["topics"] = topics
    encontrados = []
    for t in topics:
        pista = PISTAS.get(t) or PISTAS.get("rt/" + t)
        marca = f"  {G}*{Z}" if pista else "   "
        print(f"{marca} {t}" + (f"   {pista}" if pista else ""))
        if pista:
            encontrados.append(t)
    if not topics:
        print("   (ninguno; ¿esta sourceado el entorno ROS 2?)")

    # ---------------- sensores deducidos ----------------
    print(f"\n{V}--- Sensores deducidos ---{Z}")
    tiene = lambda frag: any(frag in t for t in topics)  # noqa: E731
    lidar_l1 = tiene("utlidar")
    lidar_livox = tiene("livox")
    camara = tiene("videostream") or tiene("videohub")
    mando = tiene("wirelesscontroller")
    sport = tiene("sportmodestate")

    if lidar_livox:
        lidar = "Livox Mid-360 (probablemente EDU Plus)"
    elif lidar_l1:
        lidar = "4D LiDAR L1 integrado (EDU base)"
    else:
        lidar = "no detectado"

    for etiqueta, valor in (("LiDAR", lidar),
                            ("camara frontal", "si" if camara else "no detectada"),
                            ("mando fisico", "emparejado" if mando else "no detectado"),
                            ("Sport Mode", "activo" if sport else "no publica")):
        color = G if "no" not in str(valor) else Y
        print(f"  {etiqueta:<16} {color}{valor}{Z}")
    inv["sensores"] = {"lidar": lidar, "camara": camara,
                       "mando": mando, "sport_mode": sport}

    # ---------------- transporte ----------------
    print(f"\n{V}--- Transporte ---{Z}")
    hz = lec.hz()
    print(f"  rt/lowstate      {hz:.1f} Hz  ({lec.n} mensajes)")
    print(f"  {'esperado ~500 Hz en el robot real' if hz > 300 else Y + 'por debajo de lo esperado' + Z}")
    inv["lowstate_hz"] = round(hz, 1)

    # ---------------- bateria ----------------
    print(f"\n{V}--- Bateria ---{Z}")
    bms = getattr(m, "bms_state", None)
    bat: dict = {}
    if bms is not None:
        bat = {
            "carga_pct": int(getattr(bms, "soc", 0) or 0),
            "ciclos": int(getattr(bms, "cycle", 0) or 0),
            "corriente_mA": int(getattr(bms, "current", 0) or 0),
            "version": f"{getattr(bms, 'version_high', 0)}.{getattr(bms, 'version_low', 0)}",
            "estado": int(getattr(bms, "status", 0) or 0),
        }
        celdas = list(getattr(bms, "cell_vol", []) or [])
        if celdas:
            v = [c / 1000.0 for c in celdas if c]
            if v:
                bat["celdas_V"] = [round(x, 3) for x in v]
                bat["desequilibrio_mV"] = round(1000 * (max(v) - min(v)), 1)
        ntc = list(getattr(bms, "bq_ntc", []) or [])
        if ntc:
            bat["temperatura_C"] = [int(x) for x in ntc]

        print(f"  carga            {bat['carga_pct']} %")
        print(f"  ciclos de carga  {bat['ciclos']}")
        print(f"  corriente        {bat['corriente_mA']} mA")
        if "celdas_V" in bat:
            print(f"  celdas           {bat['celdas_V']}")
            d = bat["desequilibrio_mV"]
            color = G if d < 50 else Y
            print(f"  desequilibrio    {color}{d} mV{Z}   (por debajo de 50 esta sano)")
        if "temperatura_C" in bat:
            print(f"  temperatura      {bat['temperatura_C']} C")
    print(f"  tension total    {getattr(m, 'power_v', 0):.1f} V")
    print(f"  corriente total  {getattr(m, 'power_a', 0):.2f} A")
    bat["tension_V"] = round(float(getattr(m, "power_v", 0) or 0), 2)
    inv["bateria"] = bat

    # ---------------- motores ----------------
    print(f"\n{V}--- Motores ---{Z}")
    nombres = ["FR_hip", "FR_thigh", "FR_calf", "FL_hip", "FL_thigh", "FL_calf",
               "RR_hip", "RR_thigh", "RR_calf", "RL_hip", "RL_thigh", "RL_calf"]
    q = [m.motor_state[i].q for i in range(12)]
    tau = [getattr(m.motor_state[i], "tau_est", 0.0) for i in range(12)]
    temp = [int(getattr(m.motor_state[i], "temperature", 0)) for i in range(12)]

    print(f"  {'articulacion':<10} {'q (rad)':>9} {'tau (Nm)':>9} {'T (C)':>6}")
    for i, n in enumerate(nombres):
        alerta = f"  {Y}<<< caliente{Z}" if temp[i] > 60 else ""
        print(f"  {n:<10} {q[i]:9.3f} {tau[i]:9.2f} {temp[i]:6d}{alerta}")
    print(f"\n  temperatura: min {min(temp)} C, max {max(temp)} C")
    if max(temp) == 0:
        print(f"  {Y}Todas a cero: eso pasa en simulacion, no en el robot real.{Z}")
    inv["motores"] = {"posiciones": [round(x, 4) for x in q],
                      "temperaturas": temp,
                      "temp_max": max(temp), "temp_min": min(temp)}

    # ---------------- IMU y pies ----------------
    print(f"\n{V}--- IMU y pies ---{Z}")
    quat = list(m.imu_state.quaternion)
    rpy = list(m.imu_state.rpy)
    pies = list(m.foot_force)
    print(f"  cuaternion    {[round(x, 3) for x in quat]}")
    print(f"  roll/pitch/yaw{[round(x, 3) for x in rpy]}")
    print(f"  temp IMU      {getattr(m.imu_state, 'temperature', 0)} C")
    print(f"  fuerza pies   {pies}   (FR, FL, RR, RL)")
    if all(f == 0 for f in pies):
        print(f"  {Y}Todos a cero. En el robot real deberian dar valores.{Z}")
    inv["imu"] = {"quaternion": [round(x, 4) for x in quat],
                  "rpy": [round(x, 4) for x in rpy]}
    inv["foot_force"] = [int(x) for x in pies]

    # ---------------- modo ----------------
    print(f"\n{V}--- Modo de la maquina ---{Z}")
    mm = getattr(m, "mode_machine", None)
    print(f"  mode_machine  {mm}")
    print(f"  mode_pr       {getattr(m, 'mode_pr', None)}")
    print(f"  tick          {getattr(m, 'tick', None)}")
    inv["mode_machine"] = mm

    # ---------------- salida ----------------
    destino = paths.ROOT / "env" / "inventory.json"
    destino.write_text(json.dumps(inv, indent=2, ensure_ascii=False))
    print(f"\n{G}escrito: {destino}{Z}")

    if args.write:
        md = paths.ROOT / "env" / "HARDWARE.md"
        borrador = f"""# Inventario de hardware

Generado por `tools/inventory_robot.py` el {inv['fecha']}.
Los campos marcados PENDIENTE hay que completarlos a mano.

## Robot

| campo | valor |
|---|---|
| Modelo | Unitree Go2 EDU |
| Variante | {'EDU Plus (LiDAR Livox)' if lidar_livox else 'EDU base (LiDAR L1)' if lidar_l1 else 'PENDIENTE'} |
| Numero de serie | PENDIENTE (mirar la pegatina) |
| Firmware | PENDIENTE (app: Device > About) |
| **Masa medida** | **PENDIENTE (pesar; entra en el coste de transporte)** |
| Ordenador embarcado | PENDIENTE (mirar la docking station) |

## Sensores detectados por DDS

| sensor | estado |
|---|---|
| LiDAR | {lidar} |
| Camara frontal | {'detectada' if camara else 'no detectada'} |
| Mando fisico | {'emparejado' if mando else 'no detectado'} |
| Sport Mode | {'activo' if sport else 'no publica'} |
| Motores | 12, temperatura {min(temp)}-{max(temp)} C |
| Sensores de fuerza en pies | {'si' if any(pies) else 'sin lectura'} |

## Bateria

| campo | valor |
|---|---|
| Carga | {bat.get('carga_pct', '?')} % |
| Ciclos | {bat.get('ciclos', '?')} |
| Tension | {bat.get('tension_V', '?')} V |
| Desequilibrio entre celdas | {bat.get('desequilibrio_mV', '?')} mV |

## Comunicacion

| campo | valor |
|---|---|
| Interfaz del portatil | {args.iface} |
| IP del portatil | 192.168.123.222/24 |
| IP del robot | 192.168.123.161 |
| Domain DDS | {args.domain} |
| Frecuencia de rt/lowstate | {inv['lowstate_hz']} Hz |

## Portatil de desarrollo

HP ProBook 450 G10, i5-1335U, 16 GB, Intel Iris Xe.
Ubuntu 26.04.1 LTS, contenedor Docker con ROS 2 Humble.

## Topics publicados

```
{chr(10).join('  ' + t for t in topics) if topics else '  (no listados)'}
```
"""
        md.write_text(borrador)
        print(f"{G}escrito: {md}{Z}")
        print(f"{Y}Completa los PENDIENTE a mano, sobre todo la MASA.{Z}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
