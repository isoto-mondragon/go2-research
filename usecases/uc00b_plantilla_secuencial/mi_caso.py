# ESTE ES EL UNICO FICHERO QUE TIENES QUE EDITAR.
# Escribe lo que quieres que haga el robot, de arriba abajo, como una receta.
# Vale igual para el simulador (--mode sim) y para el robot (--mode real).
#
# Lo que puede hacer robot (mas detalle en LEEME.md):
#   robot.levantarse()                 de pie          (solo real; en sim ya lo esta)
#   robot.sentarse()                   sentado         (solo real)
#   robot.avanzar(2)                   2 segundos hacia delante, y para
#   robot.retroceder(2)  robot.girar_izquierda(2)  robot.girar_derecha(2)
#   robot.mover(vx=0.3, wz=0.5)        UN paso; para usarlo dentro de un bucle
#   robot.parar()   robot.esperar(1)   quieto
#   robot.activo()                     False cuando hay que terminar (Ctrl-C, tiempo...)
#   robot.inclinacion_grados()  robot.giro()  robot.angulos()  robot.pares()
#   robot.bateria()      !! SIEMPRE 0 EN SIMULACION !!
#   robot.temperatura()  !! SIEMPRE 0 EN SIMULACION !!
#   robot.fuerza_pies()  !! SIEMPRE 0 EN SIMULACION !!
#   robot.cargar_detector()  robot.buscar_persona()   YOLO (webcam en sim, camara en real)
#   robot.imagen()                     camara del robot  !! NO EXISTE EN SIMULACION !!
# En el robot real, por debajo de 0.2 m/s el robot ignora la orden.


def caso(robot):
    robot.levantarse()
    robot.avanzar(2)         # dos segundos hacia delante...
    robot.parar()            # ...y quieto
