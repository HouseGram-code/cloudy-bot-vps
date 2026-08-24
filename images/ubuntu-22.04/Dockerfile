# Cloudy VPS - Ubuntu 22.04 LTS guest image
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    TERM=xterm-256color \
    LANG=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        wget \
        git \
        nano \
        vim \
        htop \
        neofetch \
        sudo \
        unzip \
        zip \
        tar \
        xz-utils \
        procps \
        iproute2 \
        iputils-ping \
        net-tools \
        dnsutils \
        python3 \
        python3-pip \
        build-essential \
        openssh-client \
        tmux \
        screen \
        locales \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

# ---- tmate (SSH access without port forwarding) ----
ARG TMATE_VERSION=2.4.0
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
        amd64) tarch="amd64" ;; \
        arm64) tarch="arm64v8" ;; \
        armhf) tarch="arm32v7" ;; \
        *) echo "unsupported arch: $arch" && exit 1 ;; \
    esac; \
    wget -qO /tmp/tmate.tar.xz "https://github.com/tmate-io/tmate/releases/download/${TMATE_VERSION}/tmate-${TMATE_VERSION}-static-linux-${tarch}.tar.xz"; \
    tar -xf /tmp/tmate.tar.xz -C /tmp; \
    mv /tmp/tmate-${TMATE_VERSION}-static-linux-${tarch}/tmate /usr/local/bin/tmate; \
    chmod +x /usr/local/bin/tmate; \
    rm -rf /tmp/tmate*

# ---- Cosmetics: login banner ----
RUN printf '%s\n' \
    '' \
    '   ___ _                _        _   _ ___  ___ ' \
    '  / __| |___ _  _ __| |_  _  | | | | _ \/ __|' \
    ' | (__| / _ \ || / _` | || | | |_| |  _/\__ \' \
    '  \___|_\___/\_,_\__,_|\_, |  \___/|_|  |___/' \
    '                        |__/                  ' \
    '  Ubuntu 22.04 LTS  |  Free Tier VPS  |  powered by Cloudy VPS Bot' \
    '' > /etc/motd

RUN echo 'cat /etc/motd' >> /root/.bashrc \
    && echo 'cd /root' >> /root/.bashrc

WORKDIR /root

# Keep the "VPS" alive as a long-running box.
CMD ["/bin/bash", "-c", "tail -f /dev/null"]
