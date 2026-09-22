# docker/Dockerfile
#
# Imagen de trabajo del Unitree Go2 para el grupo DANZ.
#
# DECISIONES DE DISENO
# --------------------
# CPU, sin CUDA. Es la unica forma de que funcione en cualquier ordenador sea
# cual sea su tarjeta grafica. MuJoCo simula por CPU y la inferencia ONNX de la
# politica tarda 0.05 ms. La GPU solo hace falta para ENTRENAR, y para eso esta
# Colab. Meter CUDA aqui convertiria la imagen en inutilizable para el resto.
#
# GUI por noVNC. El simulador se ve en el navegador (6080) o con un cliente VNC
# nativo (5900). Funciona igual en Windows, macOS y Linux. Compartir el socket
# X11 solo va bien en Linux.
#
# Ubuntu 22.04. Lo exige ROS 2 Humble, la unica combinacion que Unitree prueba
# oficialmente con el SDK2.
#
# COMMITS FIJADOS
# ---------------
# Los seis repositorios de Unitree estan anclados a un commit concreto. Sin
# esto, dos personas que construyan en dias distintos obtienen imagenes
# distintas, y una imagen publicada deja de poder reconstruirse.
#
# No es teorico: montando este proyecto nos han mordido tres cambios silenciosos
# del upstream en cuestion de semanas.
#   - `unitree_sdk2/install.sh` desaparecio; ahora se instala con cmake
#   - `mujoco-warp` dejo de necesitar clonarse de git al publicarse en PyPI
#   - el pin `warp-lang==1.12.1` dejo de ser compatible con mujoco_warp
#
# Combinacion validada el 2026-09-19 en dos maquinas (Ubuntu 26.04 y Windows).
# Para actualizar: cambiar los ARG, reconstruir y volver a validar.
# Justificacion ampliada en usecases/uc01_locomotion/train/ENTORNO_FIJADO.md

FROM ubuntu:22.04

LABEL org.opencontainers.image.title="go2-workspace"
LABEL org.opencontainers.image.description="Entorno Unitree Go2: ROS2 Humble, CycloneDDS 0.10.2, SDK2, MuJoCo"
LABEL org.opencontainers.image.source="https://github.com/isoto-mondragon/go2-research"
LABEL org.opencontainers.image.licenses="MIT"

# --- commits fijados ---
ARG UNITREE_ROS2_SHA=668d1ec5a05d1c38d3306bdca7d59f2ba3581a88
ARG UNITREE_SDK2_SHA=c753829882fba461ed07ba25aaabee0a25d83663
ARG UNITREE_SDK2_PY_SHA=65691c8a8bc53b98d3976dba4dbf9d5d20b2e7f5
ARG UNITREE_MUJOCO_SHA=1eb6642e3f3fdfb7fb13a9794fd6a2dd93ea0e7d
ARG RMW_CYCLONEDDS_SHA=e370e09ca76fc811e42ff07bd3a5e3b92f18c51e
ARG CYCLONEDDS_SHA=5041f3560c088c99e5088b2b8520b69169621196

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    ROS_DISTRO=humble \
    GO2_DEPS=/opt/go2 \
    GO2_ROOT=/workspace \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1

# ---------------------------------------------------------------------------
# 1. Base del sistema
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg lsb-release locales software-properties-common \
        git build-essential cmake pkg-config \
        python3 python3-pip python3-dev \
        iproute2 iputils-ping net-tools tcpdump \
        nano less unzip \
    && locale-gen en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# 2. Servidor grafico virtual y noVNC
# ---------------------------------------------------------------------------
# MuJoCo abre una ventana con GLFW, que necesita un display. Xvfb lo provee y
# mesa da OpenGL por software (llvmpipe). Mas lento que una GPU pero funciona
# en cualquier maquina, que es justo el requisito.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tigervnc-standalone-server tigervnc-common \
        xvfb x11vnc novnc websockify x11-utils mesa-utils \
        libgl1-mesa-dri libgl1-mesa-glx libglu1-mesa libegl1-mesa \
        libglfw3 libxinerama1 libxcursor1 libxi6 libxrandr2 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# 3. ROS 2 Humble
# ---------------------------------------------------------------------------
# ros-base, no desktop: desktop anade unos 2 GB de herramientas graficas que
# aqui no se usan. rviz2 se anade suelto porque si es util.
RUN add-apt-repository universe \
    && ROS_APT_SOURCE_VERSION=$(curl -fsSL https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest \
         | grep -F '"tag_name"' | awk -F\" '{print $4}') \
    && curl -fsSL -o /tmp/ros2-apt-source.deb \
         "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.jammy_all.deb" \
    && apt-get install -y /tmp/ros2-apt-source.deb \
    && apt-get update && apt-get install -y --no-install-recommends \
        ros-humble-ros-base \
        ros-humble-rviz2 \
        ros-humble-rmw-cyclonedds-cpp \
        ros-humble-rosidl-generator-dds-idl \
        ros-dev-tools \
        python3-colcon-common-extensions \
    && rm -rf /var/lib/apt/lists/* /tmp/ros2-apt-source.deb

# ---------------------------------------------------------------------------
# 4. unitree_ros2 con CycloneDDS 0.10.2
# ---------------------------------------------------------------------------
# El robot usa CycloneDDS 0.10.2. Hay que compilar rmw_cyclonedds contra esa
# version concreta, no contra la de apt.
#
# Los clones son completos (sin --depth 1) porque hay que hacer checkout de un
# commit que puede no ser la punta de la rama.
WORKDIR ${GO2_DEPS}
RUN git clone https://github.com/unitreerobotics/unitree_ros2.git \
    && git -C unitree_ros2 checkout -q ${UNITREE_ROS2_SHA} \
    && cd unitree_ros2/cyclonedds_ws/src \
    && git clone -b humble https://github.com/ros2/rmw_cyclonedds.git \
    && git -C rmw_cyclonedds checkout -q ${RMW_CYCLONEDDS_SHA} \
    && git clone -b releases/0.10.x https://github.com/eclipse-cyclonedds/cyclonedds.git \
    && git -C cyclonedds checkout -q ${CYCLONEDDS_SHA} \
    && echo "unitree_ros2    $(git -C ${GO2_DEPS}/unitree_ros2 rev-parse HEAD)" \
    && echo "rmw_cyclonedds  $(git -C rmw_cyclonedds rev-parse HEAD)" \
    && echo "cyclonedds      $(git -C cyclonedds rev-parse HEAD)"

# GOTCHA: cyclonedds debe compilarse SIN el entorno de ROS2 sourceado. Si se
# sourcea antes, la compilacion falla de forma confusa. Por eso van en dos
# invocaciones separadas y la primera no toca setup.bash.
RUN cd ${GO2_DEPS}/unitree_ros2/cyclonedds_ws \
    && colcon build --packages-select cyclonedds --cmake-args -DCMAKE_BUILD_TYPE=Release

RUN cd ${GO2_DEPS}/unitree_ros2/cyclonedds_ws \
    && . /opt/ros/humble/setup.sh \
    && colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release

# ---------------------------------------------------------------------------
# 5. Unitree SDK2 (C++ y Python)
# ---------------------------------------------------------------------------
# Dependencias segun el README del SDK.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libyaml-cpp-dev libeigen3-dev libboost-all-dev libfmt-dev \
    && rm -rf /var/lib/apt/lists/*

# El repo YA NO trae install.sh: la guia antigua de Unitree lo mencionaba y
# desaparecio. La instalacion actual es cmake con CMAKE_INSTALL_PREFIX.
RUN cd ${GO2_DEPS} \
    && git clone https://github.com/unitreerobotics/unitree_sdk2.git \
    && git -C unitree_sdk2 checkout -q ${UNITREE_SDK2_SHA} \
    && cd unitree_sdk2 \
    && mkdir -p build && cd build \
    && cmake .. -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt/unitree_robotics \
    && make -j"$(nproc)" \
    && make install \
    && ls -la /opt/unitree_robotics/lib

RUN cd ${GO2_DEPS} \
    && git clone https://github.com/unitreerobotics/unitree_sdk2_python.git \
    && git -C unitree_sdk2_python checkout -q ${UNITREE_SDK2_PY_SHA} \
    && cd unitree_sdk2_python && pip3 install --no-cache-dir -e .

# ---------------------------------------------------------------------------
# 6. Entorno Python
# ---------------------------------------------------------------------------
# Todo por pip, nada por apt: mezclar scipy y matplotlib de apt (compilados
# contra numpy 1.x) con numpy 2.x de pip rompe al importar. Ese fallo ya costo
# una sesion.
RUN pip3 install --no-cache-dir --upgrade pip wheel \
    && pip3 install --no-cache-dir \
        torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip3 install --no-cache-dir \
        "numpy>=1.26,<3" "scipy>=1.11" "matplotlib>=3.8" "pandas>=2.1" \
        "pyyaml>=6.0" mujoco onnxruntime ultralytics \
        opencv-python-headless dvc \
        pygame

# pygame lo importa unitree_sdk2py_bridge.py en la cabecera del fichero, aunque
# solo lo use cuando USE_JOYSTICK=1. Sin el, el simulador no arranca ni con el
# joystick desactivado.

# ---------------------------------------------------------------------------
# 7. unitree_mujoco, ya configurado
# ---------------------------------------------------------------------------
# La configuracion se aplica AQUI, no a mano en cada maquina. Los cinco valores
# tienen motivo y cada uno costo una sesion de depuracion:
#   USE_JOYSTICK = 0  sin esto el hilo de fisica no arranca, el DDS sigue
#                     publicando estado congelado y parece un fallo de control
#   DOMAIN_ID = 1     separa el simulador del robot real (domain 0)
#   INTERFACE = "lo"  el simulador habla por loopback
#   VIEWER_DT = 0.02  50 fps. MEDIDO: MuJoCo renderiza esta escena a 188 FPS
#                     (5.3 ms por fotograma) dentro del contenedor, asi que
#                     50 fps cuestan el 26 % de UN nucleo. El bucle de control
#                     usa 0.84 ms de sus 20 ms, o sea que hay CPU de sobra.
#                     Bajarlo a 0.1 (10 fps) hacia que el visor pareciera lento
#                     cuando el cuello no era el renderizado sino este limite.
#   scene_flat.xml    la escena original trae 8 escalones y el robot choca
RUN cd ${GO2_DEPS} \
    && git clone https://github.com/unitreerobotics/unitree_mujoco.git \
    && git -C unitree_mujoco checkout -q ${UNITREE_MUJOCO_SHA} \
    && cd unitree_mujoco/simulate_python \
    && sed -i 's|^ROBOT_SCENE *=.*|ROBOT_SCENE = "../unitree_robots/" + ROBOT + "/scene_flat.xml"|' config.py \
    && sed -i 's|^USE_JOYSTICK *=.*|USE_JOYSTICK = 0|' config.py \
    && sed -i 's|^DOMAIN_ID *=.*|DOMAIN_ID = 1|' config.py \
    && sed -i 's|^INTERFACE *=.*|INTERFACE = "lo"|' config.py \
    && sed -i 's|^VIEWER_DT *=.*|VIEWER_DT = 0.02|' config.py \
    && grep -E '^(ROBOT|ROBOT_SCENE|DOMAIN_ID|INTERFACE|USE_JOYSTICK|VIEWER_DT)' config.py

# La escena plana se copia desde el repositorio en tiempo de construccion.
COPY scene_flat.xml ${GO2_DEPS}/unitree_mujoco/unitree_robots/go2/scene_flat.xml

# ---------------------------------------------------------------------------
# 8. Registro de versiones dentro de la imagen
# ---------------------------------------------------------------------------
# Queda dentro de la imagen para poder auditar cualquier contenedor:
#   docker run --rm go2-workspace:1.0 cat /opt/go2/VERSIONS.txt
RUN { \
      echo "Imagen go2-workspace, construida el $(date -Iseconds)"; \
      echo; \
      echo "Repositorios de Unitree (commits fijados):"; \
      for r in unitree_ros2 unitree_sdk2 unitree_sdk2_python unitree_mujoco; do \
        printf "  %-22s %s\n" "$r" "$(git -C ${GO2_DEPS}/$r rev-parse HEAD)"; \
      done; \
      for r in rmw_cyclonedds cyclonedds; do \
        printf "  %-22s %s\n" "$r" "$(git -C ${GO2_DEPS}/unitree_ros2/cyclonedds_ws/src/$r rev-parse HEAD)"; \
      done; \
      echo; \
      echo "Python:"; \
      pip3 list 2>/dev/null | grep -iE '^(torch|numpy|scipy|mujoco|onnxruntime|ultralytics|opencv|pygame|dvc) '; \
    } > ${GO2_DEPS}/VERSIONS.txt \
    && cat ${GO2_DEPS}/VERSIONS.txt

# ---------------------------------------------------------------------------
# 9. Entrypoint
# ---------------------------------------------------------------------------
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# USUARIOS ARBITRARIOS
# El compose arranca el contenedor con el uid del anfitrion (`user: 1000:1000`)
# para que los ficheros del volumen no queden como root. Ese uid no existe en
# el /etc/passwd de la imagen, asi que la shell muestra "I have no name!" y
# `groups` avisa de un GID sin nombre. Es cosmetico, pero ensucia cada sesion.
#
# Se resuelve dando permiso de escritura a /etc/passwd al grupo root, que es el
# gid con el que arranca cualquier uid no declarado, y anadiendo la entrada al
# vuelo desde el entrypoint.
# Escritura para todos, no solo para el grupo root: el contenedor arranca con
# el uid Y el gid del anfitrion (1000:1000), asi que el grupo root no aplica y
# `g+w` no daba permiso. Es un contenedor de desarrollo, no un servicio
# expuesto, y el fichero solo recibe una linea de usuario al arrancar.
RUN chmod 666 /etc/passwd /etc/group

# GIT Y EL REPOSITORIO MONTADO
# El repositorio se monta desde el anfitrion y pertenece a otro usuario; el
# contenedor corre como root, asi que git lo rechaza:
#     fatal: detected dubious ownership in repository at '/workspace'
# Consecuencia: `git rev-parse` devuelve vacio y los experimentos se registran
# SIN sha de commit, o sea sin trazabilidad. El run se crea igual, con
# "unknown" en el nombre, asi que el fallo pasa desapercibido.
#
# Se resuelve por variables de entorno en lugar de por /etc/gitconfig: aplica
# a cualquier usuario del contenedor y no depende de que una capa concreta se
# haya reconstruido.
ENV GIT_CONFIG_COUNT=1 \
    GIT_CONFIG_KEY_0=safe.directory \
    GIT_CONFIG_VALUE_0=*

# Cinturon y tirantes: tambien en la configuracion de sistema.
RUN git config --system --add safe.directory '*' \
    && git config --system --add safe.directory /workspace \
    && cat /etc/gitconfig

WORKDIR /workspace
ENV PYTHONPATH=/workspace/src
EXPOSE 6080 5900

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["bash"]
