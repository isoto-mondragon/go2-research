# ============================================================================
# SOLO FUNCIONA CON EL ROBOT REAL.
# En simulacion la bateria vale 0, asi que aqui el robot no se moveria nunca.
# ============================================================================
# Ejemplo 5: gira mientras la bateria este por encima del 60 %, y para cuando baje.
# Ensena a leer un dato que solo existe en el robot de verdad.


def caso(robot):
    robot.levantarse()
    while robot.activo() and robot.bateria() > 60:
        robot.mover(wz=0.5)                 # gira a la izquierda
    robot.parar()
    print(f"bateria: {robot.bateria():.0f} %")
    robot.sentarse()
