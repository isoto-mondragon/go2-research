# =============================================================================
# ESTE FICHERO NO SE TOCA (salvo para cambiar de modelo o de proveedor).
# =============================================================================
"""usecases/uc06_lenguaje_natural/deploy/traductor.py

Convierte una frase ("avanza dos metros y gira a la derecha") en un PLAN: una
lista de acciones de un menu cerrado. Usa la API de Gemini.

    frase ──► Gemini (salida JSON con esquema) ──► plan ──► ejecutor.py ──► robot

EL LLM NO ESCRIBE CODIGO
------------------------
Solo rellena un esquema JSON: {"accion": <una de 8>, "cantidad": <numero>}.
Lo que no esta en el menu no se puede pedir, y los numeros se recortan despues
en ejecutor.py. Es lo que hace seguro un robot que obedece a un modelo.

SIN DEPENDENCIAS
----------------
Llama a la API REST con urllib (biblioteca estandar). No hay que instalar nada
en el contenedor ni reconstruir la imagen.

CLAVE
-----
GEMINI_API_KEY, de la variable de entorno o del fichero .env de la raiz del
repositorio (que git no versiona). Nunca se imprime.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from go2core import paths  # noqa: E402

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"

# Menu cerrado: accion -> (unidad de `cantidad`, explicacion para el modelo).
# ejecutor.py usa la misma tabla para validar; hay UN solo sitio donde se
# define lo que el robot puede hacer.
ACCIONES = {
    "levantarse":       ("-",       "ponerse de pie"),
    "sentarse":         ("-",       "sentarse (tumbarse); despues hay que levantarse"),
    "avanzar":          ("metros",  "andar hacia delante"),
    "retroceder":       ("metros",  "andar hacia atras"),
    "girar_izquierda":  ("grados",  "girar sobre si mismo a la izquierda"),
    "girar_derecha":    ("grados",  "girar sobre si mismo a la derecha"),
    "esperar":          ("segundos", "quedarse quieto"),
    "parar":            ("-",       "detenerse"),
}


class ErrorLLM(Exception):
    """Algo ha fallado al hablar con el modelo. El texto es para el usuario."""


def clave_api() -> str:
    clave = os.environ.get("GEMINI_API_KEY", "").strip()
    if not clave:
        env = paths.ROOT / ".env"
        if env.is_file():
            for linea in env.read_text().splitlines():
                nombre, _, valor = linea.partition("=")
                if nombre.strip() == "GEMINI_API_KEY":
                    clave = valor.strip().strip("'\"")
    if not clave:
        raise ErrorLLM(
            "Falta GEMINI_API_KEY. Consigue una gratis en "
            "https://aistudio.google.com/apikey y anadela a la linea "
            "GEMINI_API_KEY= del fichero .env (en la raiz del repositorio).")
    return clave


def _instrucciones(modo: str) -> str:
    menu = "\n".join(f"  - {n}: {d}. `cantidad` en {u}." if u != "-" else
                     f"  - {n}: {d}. `cantidad` = 0."
                     for n, (u, d) in ACCIONES.items())
    aviso_sim = (" Estas en SIMULACION: levantarse y sentarse no hacen nada, "
                 "no las incluyas salvo que el usuario las pida."
                 if modo == "sim" else
                 " Es el robot REAL. Si esta tumbado, un plan debe empezar por "
                 "levantarse; el sistema ya lo hace solo si se te olvida.")
    return f"""Eres el traductor de ordenes de un perro robot Unitree Go2.
Conviertes lo que dice el usuario en un plan de acciones de este menu cerrado:
{menu}

Reglas:
- Responde SOLO con el JSON del esquema. No escribas codigo.
- El plan se ejecuta en orden. Una orden compuesta ("ve a la esquina y vuelve")
  se descompone en varias acciones. Un cuadrado de 1 m son 4 x (avanzar 1, girar 90).
- Los giros son sobre el sitio: "da la vuelta" = girar 180 grados.
- Distancias en metros, giros en grados, esperas en segundos. Si no dice cuanto,
  usa 1 metro, 90 grados o 2 segundos.
- El robot no salta, no baila, no coge cosas, no ve ni habla. Si la orden no se
  puede hacer con el menu, pon entendido=false, plan=[] y explica en `mensaje`
  que si puede hacer. Si se puede hacer solo en parte, haz esa parte y dilo.
- Si la orden es peligrosa o ambigua de forma que importe (por ejemplo "avanza
  mucho"), elige lo prudente (poca distancia) y dilo en `mensaje`.
- `mensaje`: una frase corta en el idioma del usuario que resuma lo que vas a hacer.
- Las ordenes siguientes pueden referirse a las anteriores ("otra vez", "ahora
  al reves"): usa el historial.{aviso_sim}"""


ESQUEMA = {
    "type": "object",
    "properties": {
        "entendido": {"type": "boolean"},
        "mensaje": {"type": "string"},
        "plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "accion": {"type": "string", "enum": list(ACCIONES)},
                    "cantidad": {"type": "number"},
                },
                "required": ["accion", "cantidad"],
            },
        },
    },
    "required": ["entendido", "mensaje", "plan"],
}


class Traductor:
    """Una conversacion con el modelo. Recuerda las ultimas ordenes."""

    def __init__(self, modo: str, modelo: str = "gemini-flash-lite-latest",
                 timeout: float = 30.0, memoria: int = 6) -> None:
        self.modelo = modelo
        self.timeout = timeout
        self._memoria = memoria
        self._sistema = _instrucciones(modo)
        self._historial: list[dict] = []     # formato `contents` de Gemini
        self._clave = clave_api()

    def traducir(self, frase: str) -> dict:
        """Devuelve {"entendido": bool, "mensaje": str, "plan": [...]} SIN validar."""
        cuerpo = {
            "systemInstruction": {"parts": [{"text": self._sistema}]},
            "contents": self._historial + [
                {"role": "user", "parts": [{"text": frase}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": ESQUEMA,
                "temperature": 0.0,
            },
        }
        peticion = urllib.request.Request(
            URL.format(modelo=self.modelo),
            data=json.dumps(cuerpo).encode(),
            headers={"Content-Type": "application/json",
                     "x-goog-api-key": self._clave})
        # 500/503/504 son picos de demanda de Google: se reintenta con espera.
        for intento in range(4):
            try:
                with urllib.request.urlopen(peticion, timeout=self.timeout) as r:
                    datos = json.load(r)
                break
            except urllib.error.HTTPError as e:
                if e.code in (500, 503, 504) and intento < 3:
                    print(f"  Gemini saturado ({e.code}), reintento...")
                    time.sleep(2 * (intento + 1))
                    continue
                raise ErrorLLM(self._explicar_http(e)) from None
            except (urllib.error.URLError, TimeoutError) as e:
                raise ErrorLLM(f"No hay conexion con Gemini ({e}). Comprueba que el "
                               "ordenador tiene internet.") from None

        try:
            texto = datos["candidates"][0]["content"]["parts"][0]["text"]
            respuesta = json.loads(texto)
        except (KeyError, IndexError, ValueError):
            motivo = (datos.get("promptFeedback") or {}).get("blockReason", "")
            raise ErrorLLM("Gemini no ha devuelto un plan utilizable"
                           + (f" ({motivo})" if motivo else "") + ". Prueba a "
                           "decirlo de otra forma.") from None

        # Solo se recuerda lo que ha salido bien.
        self._historial += [{"role": "user", "parts": [{"text": frase}]},
                            {"role": "model", "parts": [{"text": texto}]}]
        self._historial = self._historial[-2 * self._memoria:]
        return respuesta

    @staticmethod
    def _explicar_http(e: urllib.error.HTTPError) -> str:
        try:
            detalle = json.load(e)["error"]["message"]
        except Exception:
            detalle = ""
        if e.code in (400, 403) and "API key" in detalle:
            return ("Gemini rechaza la clave. Revisa GEMINI_API_KEY en .env "
                    "(sin comillas ni espacios).")
        if e.code == 404:
            return (f"El modelo no existe ({detalle}). Cambia `modelo` en "
                    "configs/params.yaml.")
        if e.code == 429:
            return ("Demasiadas peticiones a Gemini (limite del plan gratuito). "
                    "Espera un minuto.")
        return f"Gemini responde con error {e.code}: {detalle}"
