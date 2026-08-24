# Cloudy VPS - Ubuntu 22.04 LTS guest image
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    TERM=xterm-256color \
    LANG=C.UTF-8 \
    CLOUDY_LANG=en

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
# 1) try the distro package (Ubuntu 22.04 universe ships tmate)
RUN apt-get update \
    && (apt-get install -y --no-install-recommends tmate \
        || echo "tmate not available via apt, falling back to static build") \
    && rm -rf /var/lib/apt/lists/*

# 2) fall back to the official static build if apt did not provide it
ARG TMATE_VERSION=2.4.0
RUN set -eux; \
    if command -v tmate >/dev/null 2>&1; then echo "tmate already installed"; exit 0; fi; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
        amd64) tarch="amd64" ;; \
        arm64) tarch="arm64v8" ;; \
        armhf) tarch="arm32v7" ;; \
        *) echo "unsupported arch: $arch" && exit 1 ;; \
    esac; \
    base="https://github.com/tmate-io/tmate/releases/download"; \
    wget -qO /tmp/tmate.tar.xz "${base}/${TMATE_VERSION}/tmate-${TMATE_VERSION}-static-linux-${tarch}.tar.xz"; \
    tar -xf /tmp/tmate.tar.xz -C /tmp; \
    mv /tmp/tmate-${TMATE_VERSION}-static-linux-${tarch}/tmate /usr/local/bin/tmate; \
    chmod +x /usr/local/bin/tmate; \
    rm -rf /tmp/tmate*

# ---- Cosmetics: pretty login banner (ASCII art + live system info) ----
# The banner is a real script (no fragile printf escaping) and is bilingual:
# CLOUDY_LANG=ru switches every label to Russian.
COPY cloudy-banner.sh /usr/local/bin/cloudy-banner
RUN chmod +x /usr/local/bin/cloudy-banner \
    && ln -sf /usr/local/bin/cloudy-banner /usr/local/bin/motd \
    && : > /etc/motd \
    && printf '%s\n' \
        '' \
        '# Cloudy VPS' \
        'cd /root' \
        'alias banner=/usr/local/bin/cloudy-banner' \
        'case $- in *i*) /usr/local/bin/cloudy-banner ;; esac' \
        >> /root/.bashrc \
    && /usr/local/bin/cloudy-banner > /dev/null

# Verify tmate really made it into the image (fail the build early if not)
RUN tmate -V

WORKDIR /root

# Keep the "VPS" alive as a long-running box.
CMD ["/bin/bash", "-c", "tail -f /dev/null"]
