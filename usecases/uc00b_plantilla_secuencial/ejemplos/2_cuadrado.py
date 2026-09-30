# Ejemplo 2: recorre un cuadrado y escribe la inclinacion en cada esquina.
# Ensena a repetir con un bucle y a leer un sensor. Funciona en simulacion.
# Tarda unos 25 segundos.


def caso(robot):
    robot.levantarse()
    for esquina in range(4):
        robot.avanzar(2)
        robot.girar_izquierda(3)          # unos 90 grados a 0.5 rad/s
        print(f"esquina {esquina + 1}: inclinacion {robot.inclinacion_grados():.1f} grados")
    robot.sentarse()
