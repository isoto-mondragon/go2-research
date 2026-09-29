# ESTE ES EL UNICO FICHERO QUE TIENES QUE EDITAR.
#
# Lo que puedes consultar de tel:
#   tel.bateria_pct()     carga, 0 a 100        (0 en simulacion)
#   tel.inclinacion()     radianes, 0 es recto
#   tel.temp_max()        grados                (0 en simulacion)
#   tel.q()               12 angulos de las articulaciones
#   tel.dq()              12 velocidades de las articulaciones
#   tel.tau()             12 pares de las articulaciones
#   tel.gyro()            3 velocidades de giro del cuerpo
#   tel.foot_force()      4 fuerzas de los pies (0 en simulacion)
# t son los segundos desde que empezo.
import math  # noqa: F401  (te hara falta para pasar grados a radianes)


def decidir(tel, t):
    """Devuelve (vx, vy, wz): la velocidad que quieres ahora mismo.

    vx  adelante (+) o atras (-), en m/s
    vy  izquierda (+) o derecha (-), en m/s
    wz  giro a la izquierda (+) o a la derecha (-), en rad/s

    No te preocupes por los limites ni por acelerar poco a poco:
    main.py lo hace por ti.
    """
    if t < 2.0:
        return 0.3, 0.0, 0.0   # avanza dos segundos...
    return 0.0, 0.0, 0.0       # ...y para


# Si necesitas la camara (ver ejemplos/4_seguir_con_camara.py):
#
#   def preparar(modo, iface, domain):     # se llama una vez, antes de empezar
#       global camara
#       from robot_camera import CamaraRobot
#       camara = CamaraRobot(iface, domain, init_dds=False)
#
#   Y dentro de decidir():  imagen = camara.leer()   # None si falla
