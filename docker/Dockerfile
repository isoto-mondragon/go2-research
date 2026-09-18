# docker/Dockerfile
#
# Imagen de trabajo del Unitree Go2 para el grupo DANZ.
#
# DECISIONES DE DISENO
# --------------------
# CPU, sin CUDA. Es la unica forma de que funcione en cualquier ordenador sea
# cual sea su tarjeta grafica, que es el requisito. MuJoCo simula por CPU y la
# inferencia ONNX de la politica tarda 0.2 ms. La GPU solo hace falta para
# ENTRENAR, y para eso esta Colab. Si alguien con NVIDIA quiere entrenar en
# local, se anade un Dockerfile.cuda aparte; no se mete CUDA aqui porque
# convertiria la imagen en inutilizable para el resto.
#
# GUI por noVNC. El simulador se ve abriendo localhost:6080 en el navegador.
# Funciona igual en Windows, macOS y Linux. Compartir el socket X11 solo va
# bien en Linux y obligaria a documentar tres casos distintos.
#
# Ubuntu 22.04. Lo exige ROS 2 Humble, que es la unica combinacion que Unitree
# prueba oficialmente con el SDK2.
#
# Todo en rutas FIJAS bajo /opt/go2, conocidas por src/go2core/paths.py. El
# repositorio NO se copia: se monta en /workspace, asi se edita sin reconstruir.

FROM ubuntu:22.04

LABEL org.opencontainers.image.title="go2-workspace"
LABEL org.opencontainers.image.description="Entorno Unitree Go2: ROS2 Humble, CycloneDDS 0.10.2, SDK2, MuJoCo"
LABEL org.opencontainers.image.source="https://github.com/isoto-mondragon/go2-research"

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
# mesa da OpenGL por software (llvmpipe). Es mas lento que una GPU pero
# funciona en cualquier maquina, que es justo el requisito.
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb x11vnc novnc websockify \
        libgl1-mesa-dri libgl1-mesa-glx libglu1-mesa libegl1-mesa \
        libglfw3 libxinerama1 libxcursor1 libxi6 libxrandr2 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# 3. ROS 2 Humble
# ---------------------------------------------------------------------------
# Se instala ros-base, no desktop: desktop anade ~2 GB de herramientas
# graficas que aqui no se usan. rviz2 se anade suelto porque si es util.
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
# El robot Unitree usa CycloneDDS 0.10.2. Hay que compilar rmw_cyclonedds
# contra esa version concreta, no contra la de apt.
#
# GOTCHA: cyclonedds debe compilarse SIN el entorno de ROS2 sourceado. Si se
# sourcea antes, la compilacion falla de forma confusa. Por eso van en dos
# invocaciones separadas y la primera no toca setup.bash.
WORKDIR ${GO2_DEPS}
RUN git clone --depth 1 https://github.com/unitreerobotics/unitree_ros2.git \
    && cd unitree_ros2/cyclonedds_ws/src \
    && git clone --depth 1 -b humble https://github.com/ros2/rmw_cyclonedds.git \
    && git clone --depth 1 -b releases/0.10.x https://github.com/eclipse-cyclonedds/cyclonedds.git

RUN cd ${GO2_DEPS}/unitree_ros2/cyclonedds_ws \
    && colcon build --packages-select cyclonedds --cmake-args -DCMAKE_BUILD_TYPE=Release

RUN cd ${GO2_DEPS}/unitree_ros2/cyclonedds_ws \
    && . /opt/ros/humble/setup.sh \
    && colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release

# ---------------------------------------------------------------------------
# 5. Unitree SDK2 (C++ y Python)
# ---------------------------------------------------------------------------
RUN cd ${GO2_DEPS} \
    && git clone --depth 1 https://github.com/unitreerobotics/unitree_sdk2.git \
    && cd unitree_sdk2 && ./install.sh \
    && mkdir -p build && cd build \
    && cmake .. -DCMAKE_BUILD_TYPE=Release && make -j"$(nproc)"

RUN cd ${GO2_DEPS} \
    && git clone --depth 1 https://github.com/unitreerobotics/unitree_sdk2_python.git \
    && cd unitree_sdk2_python && pip3 install --no-cache-dir -e .

# ---------------------------------------------------------------------------
# 6. Entorno Python
# ---------------------------------------------------------------------------
# Todo por pip, nada por apt: mezclar scipy/matplotlib de apt (compilados
# contra numpy 1.x) con numpy 2.x de pip rompe al importar. Ese fallo ya nos
# costo una sesion.
RUN pip3 install --no-cache-dir --upgrade pip wheel \
    && pip3 install --no-cache-dir \
        torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip3 install --no-cache-dir \
        "numpy>=1.26,<3" "scipy>=1.11" "matplotlib>=3.8" "pandas>=2.1" \
        "pyyaml>=6.0" mujoco onnxruntime ultralytics \
        opencv-python-headless dvc

# ---------------------------------------------------------------------------
# 7. unitree_mujoco, ya configurado
# ---------------------------------------------------------------------------
# La configuracion del simulador se aplica AQUI, no a mano en cada maquina.
# Los cuatro valores tienen motivo y cada uno costo una sesion de depuracion:
#   USE_JOYSTICK = 0  sin esto el hilo de fisica no arranca, el DDS sigue
#                     publicando estado congelado y parece un fallo de control
#   DOMAIN_ID = 1     separa el simulador del robot real (domain 0)
#   INTERFACE = "lo"  el simulador habla por loopback
#   VIEWER_DT = 0.05  20 fps; a 50 el visor roba CPU al bucle de control
#   scene_flat.xml    la escena original trae 8 escalones y el robot choca
RUN cd ${GO2_DEPS} \
    && git clone --depth 1 https://github.com/unitreerobotics/unitree_mujoco.git \
    && cd unitree_mujoco/simulate_python \
    && sed -i 's|^ROBOT_SCENE *=.*|ROBOT_SCENE = "../unitree_robots/" + ROBOT + "/scene_flat.xml"|' config.py \
    && sed -i 's|^USE_JOYSTICK *=.*|USE_JOYSTICK = 0|' config.py \
    && sed -i 's|^DOMAIN_ID *=.*|DOMAIN_ID = 1|' config.py \
    && sed -i 's|^INTERFACE *=.*|INTERFACE = "lo"|' config.py \
    && sed -i 's|^VIEWER_DT *=.*|VIEWER_DT = 0.05|' config.py \
    && grep -E '^(ROBOT|ROBOT_SCENE|DOMAIN_ID|INTERFACE|USE_JOYSTICK|VIEWER_DT)' config.py

# La escena plana se copia desde el repositorio en tiempo de construccion.
COPY scene_flat.xml ${GO2_DEPS}/unitree_mujoco/unitree_robots/go2/scene_flat.xml

# ---------------------------------------------------------------------------
# 8. Entrypoint
# ---------------------------------------------------------------------------
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

WORKDIR /workspace
ENV PYTHONPATH=/workspace/src
EXPOSE 6080

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["bash"]
