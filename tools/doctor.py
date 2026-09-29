#!/usr/bin/env python3
"""tools/doctor.py

Comprueba que este ordenador puede ejecutar el proyecto, y dice exactamente
que falta y con que comando se arregla.

Funciona TANTO en el anfitrion como dentro del contenedor: detecta donde esta
y comprueba lo que corresponde.

Uso:
    python3 tools/doctor.py             # comprobar todo
    python3 tools/doctor.py --fix       # ademas, arreglar lo automatizable
"""

from __future__ import annotations

import argparse
import grp
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
V, R, G, Y, Z, B = ("\033[34m", "\033[31m", "\033[32m", "\033[33m",
                    "\033[0m", "\033[1m")

problemas: list[tuple[str, str]] = []   # (que falla, como se arregla)
avisos: list[str] = []


def ok(txt: str, detalle: str = "") -> None:
    print(f"  {G}[ok]{Z} {txt}" + (f"   {detalle}" if detalle else ""))


def mal(txt: str, arreglo: str, detalle: str = "") -> None:
    print(f"  {R}[XX]{Z} {txt}" + (f"   {detalle}" if detalle else ""))
    problemas.append((txt, arreglo))


def avisa(txt: str, detalle: str = "") -> None:
    print(f"  {Y}[--]{Z} {txt}" + (f"   {detalle}" if detalle else ""))
    avisos.append(txt)


def sec(txt: str) -> None:
    print(f"\n{V}{B}{txt}{Z}")


def corre(cmd: list[str], t: float = 10) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=t)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return 1, str(e)


def en_contenedor() -> bool:
    return Path("/.dockerenv").exists()


# ===========================================================================
def comprobar_anfitrion(args) -> None:
    sec("1. Sistema")
    so = platform.system()
    print(f"  sistema: {so} {platform.machine()}")
    if so != "Linux":
        avisa("No es Linux: el simulador funciona, el ROBOT FISICO no",
              "es una limitacion de Docker Desktop, no del proyecto")

    sec("2. Docker")
    if not shutil.which("docker"):
        mal("Docker no esta instalado",
            "sudo apt install -y docker.io docker-compose-v2 docker-buildx")
        return
    ok("docker instalado")

    c, out = corre(["docker", "version", "--format", "{{.Server.Version}}"])
    if c != 0:
        if "permission denied" in out.lower():
            mal("Sin permisos para usar Docker",
                "sudo usermod -aG docker $USER  y REINICIAR el ordenador")
        else:
            mal("El servicio de Docker no responde",
                "sudo systemctl enable --now docker")
        return
    ok("docker funciona", f"servidor {out}")

    c, _ = corre(["docker", "compose", "version"])
    if c != 0:
        mal("docker compose no disponible",
            "sudo apt install -y docker-compose-v2")
    else:
        ok("docker compose disponible")

    sec("3. Fichero .env")
    env = RAIZ / ".env"
    valores: dict[str, str] = {}
    if not env.exists():
        mal("No existe .env",
            'echo "UID_GID=$(id -u):$(id -g)" > .env')
    else:
        for l in env.read_text().splitlines():
            if "=" in l and not l.startswith("#"):
                k, v = l.split("=", 1)
                valores[k.strip()] = v.strip()
        ok(".env existe", f"{len(valores)} variables")

    if platform.system() == "Linux":
        esperado = f"{os.getuid()}:{os.getgid()}"
        if valores.get("UID_GID") != esperado:
            mal(f"UID_GID incorrecto (deberia ser {esperado})",
                'sed -i "/^UID_GID=/d" .env && '
                'echo "UID_GID=$(id -u):$(id -g)" >> .env',
                f"ahora: {valores.get('UID_GID', 'sin definir')}")
        else:
            ok("UID_GID correcto", esperado)

    sec("4. Red del robot")
    if platform.system() != "Linux":
        avisa("Sin robot fisico en este sistema")
    else:
        c, out = corre(["ip", "-br", "link"])
        ifaces = []
        for l in out.splitlines():
            n = l.split()[0].split("@")[0] if l.split() else ""
            if n.startswith("e") and not n.startswith(("eth-docker",)):
                ifaces.append((n, "UP" if " UP " in l else "DOWN"))
        if ifaces:
            ok("interfaces Ethernet", ", ".join(f"{n} ({e})" for n, e in ifaces))
        else:
            avisa("Sin interfaz Ethernet: ¿adaptador USB?")

        iface = valores.get("GO2_IFACE")
        nombres = [n for n, _ in ifaces]
        if not iface:
            if nombres:
                mal("GO2_IFACE sin definir",
                    f'echo "GO2_IFACE={nombres[0]}" >> .env')
            else:
                avisa("GO2_IFACE sin definir y sin interfaces Ethernet")
        elif iface not in nombres:
            arreglo = (f'sed -i "s/^GO2_IFACE=.*/GO2_IFACE={nombres[0]}/" .env'
                       if nombres else "conecta un cable de red")
            mal(f"GO2_IFACE='{iface}' NO existe en esta maquina", arreglo,
                f"disponibles: {', '.join(nombres) or 'ninguna'}")
        else:
            ok(f"GO2_IFACE={iface} existe")
            c, out = corre(["ip", "-br", "addr", "show", iface])
            if "192.168.123." in out:
                ok("IP del robot configurada", out.split()[-1])
                c, _ = corre(["ping", "-c", "2", "-W", "2", "192.168.123.161"], 8)
                if c == 0:
                    ok("el ROBOT RESPONDE", "192.168.123.161")
                else:
                    avisa("El robot no responde",
                          "¿encendido? ¿cable? ¿ha terminado de arrancar?")
            else:
                mal("La interfaz no tiene la IP 192.168.123.222",
                    f"./env/go2_net.sh create {iface} && ./env/go2_net.sh up")

    sec("5. GPU y webcam")
    dri = Path("/dev/dri")
    gpu = dri.exists() and any(dri.glob("renderD*"))
    videos = sorted(Path("/dev").glob("video*"))
    print(f"  GPU accesible : {'si' if gpu else 'no'}")
    print(f"  webcam        : {', '.join(v.name for v in videos) or 'ninguna'}")
    print(f"  {Y}la camara del ROBOT llega por red: no necesita /dev/video{Z}")

    sec("6. Override de Linux")
    ov = RAIZ / "docker-compose.linux.yml"
    if platform.system() != "Linux":
        avisa("No aplica en este sistema")
    elif not ov.exists():
        if gpu or videos:
            mal("Falta docker-compose.linux.yml",
                "python3 tools/gen_linux_override.py --write")
        else:
            ok("no hace falta (sin GPU ni webcam)")
    else:
        txt = ov.read_text()
        import re
        gids = [int(g) for g in re.findall(r'^\s+- "(\d+)"', txt, re.M)]
        malos = [g for g in gids if not _existe_gid(g)]
        disp = re.findall(r"- (/dev/[a-z0-9/]+):", txt)
        faltan = [d for d in disp if not Path(d).exists()]

        if malos:
            mal(f"El override trae GID de otra maquina: {malos}",
                "python3 tools/gen_linux_override.py --write")
        elif faltan:
            mal(f"El override pide dispositivos que no existen: {faltan}",
                "python3 tools/gen_linux_override.py --write")
        else:
            ok("override correcto para esta maquina",
               f"GID {gids}, {len(disp)} dispositivos")

    sec("7. Imagen del contenedor")
    c, out = corre(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"], 20)
    if "go2-workspace" in out:
        for l in out.splitlines():
            if "go2-workspace" in l:
                ok("imagen descargada", l)
    else:
        mal("Falta la imagen",
            "docker compose --profile sim pull")

    sec("8. Configuracion de compose")
    for perfil in ("sim", "real"):
        cmd = ["docker", "compose", "-f", "docker-compose.yml"]
        if ov.exists() and platform.system() == "Linux":
            cmd += ["-f", "docker-compose.linux.yml"]
        cmd += ["--profile", perfil, "config", "--quiet"]
        c, out = corre(cmd, 20)
        if c == 0:
            ok(f"perfil '{perfil}' valido")
        else:
            mal(f"perfil '{perfil}' invalido",
                "python3 tools/gen_linux_override.py --write",
                out.splitlines()[0] if out else "")


def _existe_gid(g: int) -> bool:
    try:
        grp.getgrgid(g)
        return True
    except KeyError:
        return Path(f"/dev/dri").exists() and any(
            d.stat().st_gid == g for d in Path("/dev").glob("video*")
        ) if Path("/dev").exists() else False


# ===========================================================================
def comprobar_contenedor(args) -> None:
    sec("1. Dentro del contenedor")
    c, out = corre(["id"])
    ok("usuario", out)
    print(f"  HOME={os.environ.get('HOME')}  DISPLAY={os.environ.get('DISPLAY')}")

    sec("2. Entorno del proyecto")
    for v in ("GO2_MODE", "GO2_IFACE", "ROS_DOMAIN_ID", "GO2_ROOT", "GO2_DEPS"):
        val = os.environ.get(v)
        (ok if val else mal)(f"{v}", "sal y vuelve a entrar al contenedor",
                             val or "sin definir") if val else mal(
            f"{v} sin definir", "sal y vuelve a entrar al contenedor")

    sec("3. Interfaz de red")
    iface = os.environ.get("GO2_IFACE", "")
    c, out = corre(["ip", "-br", "addr"])
    if iface and iface in out:
        for l in out.splitlines():
            if l.startswith(iface):
                ok(f"{iface} visible", l)
        if "192.168.123." in out:
            ok("IP del robot presente")
            c, _ = corre(["ping", "-c", "2", "-W", "2", "192.168.123.161"], 8)
            (ok if c == 0 else avisa)("el robot responde" if c == 0
                                      else "el robot no responde",
                                      "192.168.123.161")
    elif iface == "lo":
        ok("modo simulacion (lo)")
    elif iface:
        mal(f"'{iface}' no existe dentro del contenedor",
            "corrige GO2_IFACE en .env con el nombre real y vuelve a entrar",
            "interfaces: " + ", ".join(l.split()[0] for l in out.splitlines()))

    sec("4. Bibliotecas")
    for mod, etiqueta in (("numpy", "numpy"), ("cv2", "opencv"),
                          ("torch", "torch"), ("ultralytics", "YOLO"),
                          ("mujoco", "mujoco"), ("unitree_sdk2py", "SDK Unitree"),
                          ("onnxruntime", "onnxruntime")):
        c, out = corre([sys.executable, "-c",
                        f"import {mod}; print(getattr({mod},'__version__',''))"], 60)
        (ok if c == 0 else mal)(etiqueta, "la imagen esta incompleta: "
                                "docker compose --profile sim pull",
                                out.splitlines()[-1] if c == 0 and out else "")

    sec("5. Ventanas graficas")
    if not os.environ.get("DISPLAY"):
        avisa("Sin DISPLAY: no se pueden abrir ventanas",
              "usa el perfil dev o real con xhost +local:docker")
    else:
        c, out = corre([sys.executable, "-c",
                        "import cv2; cv2.namedWindow('t'); cv2.destroyAllWindows()"], 30)
        (ok if c == 0 else mal)("cv2.imshow funciona",
                                "en el anfitrion: xhost +local:docker")

    sec("6. Camara del robot")
    if os.environ.get("GO2_MODE") == "real" and iface not in ("", "lo"):
        c, out = corre([sys.executable, "-c", f"""
from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.go2.video.video_client import VideoClient
ChannelFactoryInitialize(0, '{iface}')
v = VideoClient(); v.SetTimeout(3.0); v.Init()
code, data = v.GetImageSample()
print('codigo', code, 'bytes', len(data) if data else 0)
"""], 30)
        (ok if c == 0 and "codigo 0" in out else mal)(
            "camara del robot", "comprueba que la app movil esta cerrada",
            out.splitlines()[-1] if out else "")
    else:
        avisa("No aplica (modo sim o sin interfaz)")


# ===========================================================================
def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fix", action="store_true",
                   help="arreglar lo que se pueda automaticamente")
    args = p.parse_args()

    dentro = en_contenedor()
    print(f"\n{V}{B}{'=' * 62}{Z}")
    print(f"{V}{B}  Diagnostico del entorno Go2 "
          f"({'CONTENEDOR' if dentro else 'TU ORDENADOR'}){Z}")
    print(f"{V}{B}{'=' * 62}{Z}")

    if dentro:
        comprobar_contenedor(args)
    else:
        comprobar_anfitrion(args)

    print(f"\n{V}{B}{'=' * 62}{Z}")
    if not problemas:
        print(f"  {G}{B}TODO CORRECTO{Z}")
        if avisos:
            print(f"  {Y}{len(avisos)} aviso(s), ninguno bloqueante{Z}")
        print(f"\n  Siguiente paso:")
        if dentro:
            print("    python3 tools/dds_smoketest.py --mode "
                  f"{os.environ.get('GO2_MODE', 'sim')} "
                  f"--iface {os.environ.get('GO2_IFACE', 'lo')}")
        else:
            print("    docker compose --profile sim up")
        return 0

    print(f"  {R}{B}{len(problemas)} PROBLEMA(S){Z}\n")
    for i, (que, arreglo) in enumerate(problemas, 1):
        print(f"  {R}{i}. {que}{Z}")
        print(f"     arreglo:  {B}{arreglo}{Z}\n")

    if args.fix:
        print(f"{Y}Ejecutando los arreglos automatizables...{Z}\n")
        for que, arreglo in problemas:
            if arreglo.startswith(("python3 tools/", "echo ", "sed ")):
                print(f"  $ {arreglo}")
                subprocess.run(arreglo, shell=True, cwd=RAIZ)
        print(f"\n{Y}Vuelve a ejecutar el diagnostico para comprobar.{Z}")
    else:
        print(f"  {Y}Anade --fix para aplicar los arreglos automatizables.{Z}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
