# Ejemplo 2: cada 5 segundos alterna entre avanzar y girar. Funciona en simulacion.
# Ensena a leer la telemetria: una vez por segundo escribe en pantalla el giro
# que mide el robot (tel.gyro()), y lo veras cambiar cuando empieza a girar.
# Usa --duration 20 para ver varios cambios.

ultimo_segundo = -1


def decidir(tel, t):
    global ultimo_segundo
    if int(t) != ultimo_segundo:            # una vez por segundo
        ultimo_segundo = int(t)
        print(f"    giro medido: {tel.gyro()[2]:+.2f} rad/s")

    if int(t / 5) % 2 == 0:                 # 0-5 s, 10-15 s...
        return 0.3, 0.0, 0.0                # avanza
    return 0.0, 0.0, 0.5                    # gira
