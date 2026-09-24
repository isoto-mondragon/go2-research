# Inventario de hardware

Generado por `tools/inventory_robot.py` el 2026-09-24T09:11:47.
Los campos marcados PENDIENTE hay que completarlos a mano.

## Robot

| campo | valor |
|---|---|
| Modelo | Unitree Go2 EDU |
| Variante | EDU base (LiDAR L1) |
| Numero de serie | PENDIENTE (mirar la pegatina) |
| Firmware | PENDIENTE (app: Device > About) |
| **Masa medida** | **PENDIENTE (pesar; entra en el coste de transporte)** |
| Ordenador embarcado | PENDIENTE (mirar la docking station) |

## Sensores detectados por DDS

| sensor | estado |
|---|---|
| LiDAR | 4D LiDAR L1 integrado (EDU base) |
| Camara frontal | detectada |
| Mando fisico | emparejado |
| Sport Mode | activo |
| Motores | 12, temperatura 35-41 C |
| Sensores de fuerza en pies | si |

## Bateria

| campo | valor |
|---|---|
| Carga | 80 % |
| Ciclos | 5 |
| Tension | 30.8 V |
| Desequilibrio entre celdas | 6.0 mV |

## Comunicacion

| campo | valor |
|---|---|
| Interfaz del portatil | enp3s0 |
| IP del portatil | 192.168.123.222/24 |
| IP del robot | 192.168.123.161 |
| Domain DDS | 0 |
| Frecuencia de rt/lowstate | 499.6 Hz |

## Portatil de desarrollo

HP ProBook 450 G10, i5-1335U, 16 GB, Intel Iris Xe.
Ubuntu 26.04.1 LTS, contenedor Docker con ROS 2 Humble.

## Topics publicados

```
  api/arm/request
  api/assistant_recorder/request
  api/assistant_recorder/response
  api/audiohub/request
  api/audiohub/response
  api/bashrunner/request
  api/bashrunner/response
  api/config/request
  api/config/response
  api/fourg_agent/request
  api/fourg_agent/response
  api/gas_sensor/request
  api/gas_sensor/response
  api/gesture/request
  api/gpt/request
  api/gpt/response
  api/motion_switcher/request
  api/motion_switcher/response
  api/obstacles_avoid/request
  api/obstacles_avoid/response
  api/pet/request
  api/pet/response
  api/programming_actuator/request
  api/programming_actuator/response
  api/rm_con/request
  api/robot_state/request
  api/robot_state/response
  api/slam_operate/request
  api/slam_operate/response
  api/sport/request
  api/sport/response
  api/sport_lease/request
  api/sport_lease/response
  api/uwbswitch/request
  api/uwbswitch/response
  api/videohub/request
  api/videohub/response
  api/voice/request
  api/voice/response
  api/vui/request
  api/vui/response
  arm/action/state
  arm_Command
  arm_Feedback
  audio_msg
  audiohub/player/state
  audioreceiver
  audiosender
  config_change_status
  frontvideostream
  gas_sensor
  gesture/result
  gnss
  gpt_cmd
  gpt_state
  gptflowfeedback
  lf/battery_alarm
  lf/lowstate
  lf/sportmodestate
  lio_sam_ros2/mapping/odometry
  lowcmd
  lowstate
  multiplestate
  parameter_events
  pctoimage_local
  pet/flowfeedback
  programming_actuator/command
  programming_actuator/feedback
  public_network_status
  qt_add_edge
  qt_add_node
  qt_command
  qt_notice
  query_result_edge
  query_result_node
  rosout
  rtc/state
  rtc_status
  selftest
  servicestate
  servicestateactivate
  slam_info
  slam_key_info
  sportmodestate
  uslam/client_command
  uslam/cloud_map
  uslam/frontend/cloud_world_ds
  uslam/frontend/odom
  uslam/localization/cloud_world
  uslam/localization/odom
  uslam/map_file_pub
  uslam/map_file_sub
  uslam/navigation/global_path
  uslam/server_log
  utlidar/client_command
  utlidar/cloud
  utlidar/cloud_base
  utlidar/cloud_deskewed
  utlidar/grid_map
  utlidar/height_map
  utlidar/height_map_array
  utlidar/imu
  utlidar/lidar_state
  utlidar/mapping_cmd
  utlidar/range_info
  utlidar/range_map
  utlidar/robot_odom
  utlidar/robot_pose
  utlidar/server_log
  utlidar/switch
  utlidar/voxel_map
  utlidar/voxel_map_compressed
  uwbstate
  uwbswitch
  videohub/inner
  webrtcreq
  webrtcres
  wirelesscontroller
  wirelesscontroller_unprocessed
  xfk_webrtcreq
  xfk_webrtcres
```
