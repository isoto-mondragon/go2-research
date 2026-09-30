# Ejemplo 3: avanza, pero para si el cuerpo se inclina mas de 15 grados.
# Ensena a reaccionar a un sensor dentro de un bucle: mover() da UN paso y el
# bucle decide en cada uno. Funciona en simulacion (avanza hasta los 10 segundos).


def caso(robot):
    robot.levantarse()
    while robot.activo() and robot.tiempo() < 10:
        if robot.inclinacion_grados() > 15:
            print("inclinado: paro")
            break
        robot.mover(vx=0.3)
    robot.parar()
    robot.sentarse()
