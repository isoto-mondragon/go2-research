# Ejemplo 1: avanzar dos segundos y parar.
# Es lo mas simple posible: solo mira el reloj (t) y devuelve una velocidad.
# Ensena que decidir() devuelve tres numeros: (vx, vy, wz).


def decidir(tel, t):
    if t < 2.0:
        return 0.3, 0.0, 0.0   # adelante a 0.3 m/s
    return 0.0, 0.0, 0.0       # parado
