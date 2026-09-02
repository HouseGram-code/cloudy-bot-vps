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


# ---- sshx (browser terminal, second access method) ----
# Official statically linked musl build. The bot can also install it at
# runtime, so containers made from older images keep working.
RUN set -eux; \
    arch="$(uname -m)"; \
    case "$arch" in \
        x86_64|amd64) target="x86_64-unknown-linux-musl" ;; \
        aarch64|arm64) target="aarch64-unknown-linux-musl" ;; \
        armv7*) target="armv7-unknown-linux-musleabihf" ;; \
        *) target="" ;; \
    esac; \
    if [ -n "$target" ]; then \
        wget -qO /tmp/sshx.tar.gz "https://sshx.s3.amazonaws.com/sshx-${target}.tar.gz" \
        && tar -xzf /tmp/sshx.tar.gz -C /usr/local/bin sshx \
        && chmod 755 /usr/local/bin/sshx \
        && rm -f /tmp/sshx.tar.gz; \
    fi; \
    /usr/local/bin/sshx --version || true

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
    # cloudy-login is what the web terminal executes, so the banner is shown
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
    printf '%s\n' '' 'cd /root' \
        '[ -f /etc/profile.d/00-cloudy-banner.sh ] && . /etc/profile.d/00-cloudy-banner.sh # cloudy-banner' \
        >> /root/.bashrc; \
    printf '%s\n' '[ -f /root/.bashrc ] && . /root/.bashrc' >> /root/.bash_profile; \
    bash -n /root/.bashrc; \
    bash -n /etc/profile.d/00-cloudy-banner.sh; \
    bash -n /usr/local/bin/cloudy-login; \
    /usr/local/bin/cloudy-banner > /dev/null


WORKDIR /root

# Keep the "VPS" alive as a long-running box.
CMD ["/bin/bash", "-c", "tail -f /dev/null"]
