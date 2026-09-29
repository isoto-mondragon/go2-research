# Ejemplo 2: gira mientras la bateria este por encima del 60 %, y para cuando baje.
# Ensena a leer la telemetria con tel.
# En simulacion la bateria vale 0, asi que ahi no gira nunca: es normal.


def decidir(tel, t):
    if tel.bateria_pct() > 60:
        return 0.0, 0.0, 0.5   # gira a la izquierda
    return 0.0, 0.0, 0.0       # bateria baja (o simulacion): parado
