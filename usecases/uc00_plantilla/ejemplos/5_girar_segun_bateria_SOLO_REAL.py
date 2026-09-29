# ============================================================================
# SOLO FUNCIONA CON EL ROBOT REAL.
# En simulacion la bateria vale 0, asi que aqui el robot no se moveria nunca.
# ============================================================================
# Ejemplo 5: gira mientras la bateria este por encima del 60 %, y para cuando baje.
# Ensena a leer un dato que solo existe en el robot de verdad.


def decidir(tel, t):
    if tel.bateria_pct() > 60:
        return 0.0, 0.0, 0.5   # gira a la izquierda
    return 0.0, 0.0, 0.0       # bateria baja: parado
