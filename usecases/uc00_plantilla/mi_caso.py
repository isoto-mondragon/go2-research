# ESTE ES EL UNICO FICHERO QUE TIENES QUE EDITAR.
# Vale igual para el simulador (--mode sim) y para el robot (--mode real).
#
# Lo que puedes leer de tel, y donde existe:
#
#   lo que lees                                  simulador        robot real
#   tel.q()             12 angulos (rad)            si               si
#   tel.dq()            12 velocidades (rad/s)      si               si
#   tel.tau()           12 pares estimados (Nm)     si               si
#   tel.gyro()          giro, 3 ejes (rad/s)        si               si
#   tel.inclinacion()   radianes, 0 es recto        si               si
#   tel.bateria_pct()   0 a 100                  !! SIEMPRE 0 !!     si
#   tel.temp_max()      grados                   !! SIEMPRE 0 !!     si
#   tel.foot_force()    4 pies                   !! SIEMPRE 0 !!     si
#   camara del robot                             !! NO EXISTE !!     si
#
# Si tu logica usa una fila marcada con !!, no la podras probar en el
# simulador: escribela igual y pruebala con el robot.
# t son los segundos desde que empezo.
# En el robot real, por debajo de 0.2 m/s el robot ignora la orden.
import math  # noqa: F401  (te hara falta para pasar grados a radianes)

# main.py lo rellena con la seccion mi_caso de configs/params.yaml.
PARAMS = {}


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
