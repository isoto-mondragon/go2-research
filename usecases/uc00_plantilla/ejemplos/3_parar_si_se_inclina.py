# Ejemplo 3: avanza, pero para si el cuerpo se inclina mas de 15 grados.
# Ensena a reaccionar a un sensor. La inclinacion viene en radianes,
# por eso se pasa el limite de grados a radianes con math.radians.
import math

LIMITE = math.radians(15)


def decidir(tel, t):
    if tel.inclinacion() > LIMITE:
        return 0.0, 0.0, 0.0   # inclinado: parar
    return 0.3, 0.0, 0.0       # recto: avanzar
