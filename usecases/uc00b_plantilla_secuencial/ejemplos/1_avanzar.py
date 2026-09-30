# Ejemplo 1: se levanta, avanza dos segundos y se sienta.
# Es lo mas simple posible. Ensena que el caso es una receta que se lee de
# arriba abajo, y que cada verbo espera a terminar antes de pasar al siguiente.
# (En simulacion levantarse() y sentarse() no hacen nada: solo existen en el real.)


def caso(robot):
    robot.levantarse()
    robot.avanzar(2)
    robot.sentarse()
