"""
08_wireless_test.py
Test ping-pong para WirelessController_.
Publica en ambos topics y escucha en ambos para ver si recibe lo que envia.
"""
import time
import threading
from unitree_sdk2py.core.channel import (
    ChannelPublisher, ChannelSubscriber, ChannelFactoryInitialize,
)
from unitree_sdk2py.idl.unitree_go.msg.dds_ import WirelessController_
from unitree_sdk2py.idl.default import unitree_go_msg_dds__WirelessController_

ChannelFactoryInitialize(0, "lo")

received = {"a": 0, "b": 0}
def cb_a(m): received["a"] += 1
def cb_b(m): received["b"] += 1

# Suscribirse a ambos
sub_a = ChannelSubscriber("rt/wirelesscontroller", WirelessController_)
sub_a.Init(cb_a, 10)

sub_b = ChannelSubscriber("rt/wireless_controller", WirelessController_)
sub_b.Init(cb_b, 10)

# Publicar en ambos
pub_a = ChannelPublisher("rt/wirelesscontroller", WirelessController_)
pub_a.Init()
pub_b = ChannelPublisher("rt/wireless_controller", WirelessController_)
pub_b.Init()

msg = unitree_go_msg_dds__WirelessController_()
msg.lx = 0.5  # valor distintivo
msg.keys = 1 << 5  # L2

print("Publicando 50 mensajes en cada topic...")
for i in range(50):
    pub_a.Write(msg)
    pub_b.Write(msg)
    time.sleep(0.02)

# Espera para que lleguen
time.sleep(0.5)

print(f"\nResultado del loopback:")
print(f"  rt/wirelesscontroller  : {received['a']}/50 recibidos")
print(f"  rt/wireless_controller : {received['b']}/50 recibidos")

if received["a"] + received["b"] == 0:
    print("\n!! La publicacion local no funciona. Problema serio de DDS.")
elif received["a"] > 0 and received["b"] > 0:
    print("\nOK. Ambos topics funcionan. El problema NO es DDS, es el go2_ctrl.")
elif received["a"] > 0:
    print("\nSolo rt/wirelesscontroller (sin guion) recibe. Ese es el topic correcto.")
else:
    print("\nSolo rt/wireless_controller (con guion) recibe. Ese es el topic correcto.")
