# Protocolo de seguridad - Unitree Go2

Obligatorio para cualquier persona del grupo que opere el robot, incluidos
estudiantes de TFG/TFM. No es burocracia: en un grupo de investigacion este
documento vale tanto como el codigo.

## Antes de encender
- [ ] Radio de 2 m libre. Nada fragil, nadie detras del robot.
- [ ] Bateria > 50 %. Por debajo del 30 % el comportamiento de los motores
      cambia y contamina cualquier medida.
- [ ] Mando fisico encendido y EN LA MANO. Es la unica parada de emergencia real.
- [ ] App movil Unitree cerrada y desconectada.

## Antes de enviar cualquier LowCmd
- [ ] Robot tumbado y en modo damping (L2+B).
- [ ] Estado del servicio sport_mode comprobado con MotionSwitcher.CheckMode().
- [ ] Si esta activo: ReleaseMode() y volver a comprobar que queda vacio.
      Publicar LowCmd con sport_mode activo hace que dos controladores peleen
      por los mismos motores. El robot puede dar una patada.

## Secuencia de primer contacto (una sola vez por robot)
1. `env/go2_net.sh probe`
2. `tools/dds_smoketest.py --mode real --iface <IFACE>`   (solo lectura)
3. Comprobacion de sport_mode
4. LowCmd nulo (kp=kd=tau=0): debe aceptarse y el robot NO debe moverse
5. `tools/check_write_path.py --real-robot-i-have-read-safety` con el robot
   suspendido o tumbado de lado
6. Solo entonces: politica de locomocion, con el robot en el suelo

## Si algo va mal
- L2+B en el mando: damping inmediato.
- Cortar el proceso emisor NO detiene al robot por si solo.
- Registrar el incidente en este documento con fecha y causa.

## Registro de incidentes
| fecha | que paso | causa | mitigacion |
|---|---|---|---|
