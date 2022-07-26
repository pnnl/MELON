# See here for image contents: https://github.com/microsoft/vscode-dev-containers/tree/v0.238.0/containers/python-3-miniconda/.devcontainer/base.Dockerfile

FROM mcr.microsoft.com/vscode/devcontainers/miniconda:0-3

# [Choice] Node.js version: none, lts/*, 16, 14, 12, 10
ARG NODE_VERSION="none"
RUN if [ "${NODE_VERSION}" != "none" ]; then su vscode -c "umask 0002 && . /usr/local/share/nvm/nvm.sh && nvm install ${NODE_VERSION} 2>&1"; fi

# Copy environment.yml (if found) to a temp location so we update the environment. Also
# copy "noop.txt" so the COPY instruction does not fail if no environment.yml exists.
COPY environment.yml* .devcontainer/noop.txt /tmp/conda-tmp/
RUN if [ -f "/tmp/conda-tmp/environment.yml" ]; then umask 0002 && /opt/conda/bin/conda env update -n base -f /tmp/conda-tmp/environment.yml; fi \
    && rm -rf /tmp/conda-tmp

# [Optional] Uncomment to install a different version of Python than the default
# RUN conda install -y python=3.6 \
#     && pip install --no-cache-dir pipx \
#     && pipx reinstall-all

# [Optional] Uncomment this section to install additional OS packages.
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
    libboost-dev \
    libzmq5-dev \
    cmake-curses-gui \
    autoconf \
    libtool \
    libxerces-c-dev \
    automake

##############################
# New code below
##############################

# Python packages
RUN pip install eppy \
    && pip install glm \
    && conda install pandas

# Set LD_LIBRARY_PATH so GridLAB-D can find the HELICS shared library
ENV LD_LIBRARY_PATH=/usr/local/lib

# Install HELICS
RUN cd ~ \
    && git clone https://github.com/GMLC-TDC/HELICS \
    && cd HELICS \
    && mkdir build \
    && cd build \
    && cmake \
    -D HELICS_BUILD_CXX_SHARED_LIB=ON \
    ../ \
    && make \
    && sudo make install \
    && cd ../.. \
    && rm -rf HELICS

# Install HELICS python package
RUN pip install helics

# Install HELICS command line interface
RUN pip install git+https://github.com/GMLC-TDC/helics-cli.git@main

# Install GridLAB-D
RUN cd ~ \
    && git clone https://github.com/gridlab-d/gridlab-d.git \
    && cd gridlab-d \
    && git checkout feature/1279 \
    && autoreconf -if \
    && ./configure --with-helics=/usr/local \
    'CXXFLAGS=-w -O2 -std=c++14' \
    'CFLAGS=-w -O2' \
    'LDFLAGS=-w -O2' \
    && make -j8 \
    && sudo make install \
    && cd .. \
    && rm -rf gridlab-d

# Install EnergyPlus
RUN cd ~ \
    && wget https://github.com/NREL/EnergyPlus/releases/download/v9.5.0/EnergyPlus-9.5.0-de239b2e5f-Linux-Ubuntu20.04-x86_64.sh \
    && chmod +x EnergyPlus-9.5.0-de239b2e5f-Linux-Ubuntu20.04-x86_64.sh \
    && printf 'y\n\n\n' | ./EnergyPlus-9.5.0-de239b2e5f-Linux-Ubuntu20.04-x86_64.sh
