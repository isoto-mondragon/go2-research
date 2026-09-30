# Ejemplo 4: se levanta, busca a una persona con la camara y la sigue.
# Ensena percepcion: YOLO dentro de un bucle. Cada vuelta mira, decide y da un
# paso. En el robot real usa su camara; en simulacion, la webcam del portatil.
# Si no hay camara, avisa y se queda quieto en vez de fallar.


def caso(robot):
    robot.levantarse()
    robot.cargar_detector()                         # tarda unos segundos
    # Tamano aparente que queremos: con la camara del robot, 0.75 mantiene unos
    # 2 metros. Con webcam, 0.6. Se puede cambiar en configs/params.yaml.
    objetivo = robot.param("tamano_objetivo", 0.75 if robot.es_real else 0.6)

    while robot.activo():
        p = robot.buscar_persona()
        if not p.visible:
            robot.mover()                           # no la veo: quieto
            continue
        giro = 0.0 if abs(p.lateral) < 0.15 else -1.2 * p.lateral   # a la derecha = wz negativo
        avance = 0.3 if p.tamano < objetivo - 0.05 else 0.0         # lejos: acercarse
        robot.mover(vx=avance, wz=giro)

    robot.parar()
    robot.sentarse()
