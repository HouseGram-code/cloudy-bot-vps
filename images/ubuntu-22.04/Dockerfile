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
RUN set -eux; \
    chmod 755 /usr/local/bin/cloudy-banner; \
    ln -sf /usr/local/bin/cloudy-banner /usr/local/bin/motd; \
    : > /etc/motd; \
    rm -f /etc/update-motd.d/* 2>/dev/null || true; \
    : > /etc/legal 2>/dev/null || true; \
    touch /root/.hushlogin; \
    mkdir -p /etc/profile.d; \
    # cloudy-login is what the tmate session executes, so the banner is shown
    # even if ~/.bashrc is never sourced by the login shell.
    printf '%s\n' \
        '#!/bin/bash' \
        'export TERM="${TERM:-xterm-256color}"' \
        'export CLOUDY_LANG="${CLOUDY_LANG:-en}"' \
        '[ -x /usr/local/bin/cloudy-banner ] && /usr/local/bin/cloudy-banner' \
        'export CLOUDY_BANNER_SHOWN=1' \
        'exec bash -l' \
        > /usr/local/bin/cloudy-login; \
    chmod 755 /usr/local/bin/cloudy-login; \
    # one shared hook for login shells (/etc/profile.d) and interactive ones
    printf '%s\n' \
        '# cloudy-banner' \
        'export CLOUDY_LANG="${CLOUDY_LANG:-en}"' \
        "alias banner='/usr/local/bin/cloudy-banner'" \
        'case $- in' \
        '  *i*)' \
        '    if [ -z "$CLOUDY_BANNER_SHOWN" ] && [ -x /usr/local/bin/cloudy-banner ]; then' \
        '      export CLOUDY_BANNER_SHOWN=1' \
        '      /usr/local/bin/cloudy-banner' \
        '    fi' \
        '    ;;' \
        'esac' \
        > /etc/profile.d/00-cloudy-banner.sh; \
    chmod 644 /etc/profile.d/00-cloudy-banner.sh; \
    printf '%s\n' '' 'cd /root' '. /etc/profile.d/00-cloudy-banner.sh' >> /root/.bashrc; \
    printf '%s\n' '[ -f /root/.bashrc ] && . /root/.bashrc # cloudy-banner' \
        >> /root/.bash_profile; \
    bash -n /etc/profile.d/00-cloudy-banner.sh; \
    bash -n /usr/local/bin/cloudy-login; \
    /usr/local/bin/cloudy-banner > /dev/null

# Verify tmate really made it into the image (fail the build early if not)
RUN tmate -V

WORKDIR /root

# Keep the "VPS" alive as a long-running box.
CMD ["/bin/bash", "-c", "tail -f /dev/null"]
