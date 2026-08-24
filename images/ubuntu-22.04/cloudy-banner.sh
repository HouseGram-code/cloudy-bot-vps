#!/usr/bin/env bash
# Cloudy VPS - pretty login banner (ASCII art + live system info)
# Localized with CLOUDY_LANG=ru|en (defaults to en).

set -u

# ---- colors (disabled when output is not a terminal) ----
if [ -t 1 ]; then
	R=$'\e[0m'; B=$'\e[1m'
	CY=$'\e[38;5;81m'; BL=$'\e[38;5;105m'; GR=$'\e[38;5;114m'
	YE=$'\e[38;5;221m'; GY=$'\e[38;5;245m'; RD=$'\e[38;5;203m'
else
	R=""; B=""; CY=""; BL=""; GR=""; YE=""; GY=""; RD=""
fi

LANG_SEL="${CLOUDY_LANG:-en}"
case "$LANG_SEL" in
	ru*) LANG_SEL="ru" ;;
	*)   LANG_SEL="en" ;;
esac

if [ "$LANG_SEL" = "ru" ]; then
	L_WELCOME="Добро пожаловать на ваш бесплатный VPS"
	L_OS="Система";      L_KERNEL="Ядро";    L_HOST="Хост"
	L_IP="IP-адрес";     L_CPU="Процессор";  L_RAM="Память"
	L_DISK="Диск";       L_UPTIME="Онлайн";  L_LOAD="Нагрузка"
	L_TIP="Подсказка"
	L_TIPS=(
		"htop — мониторинг, tmux — сессии, neofetch — инфо о системе"
		"Файлы в /root не сохраняются после удаления VPS — делайте бэкапы"
		"apt install <пакет> работает: у вас полный root-доступ"
		"Сессия SSH закрывается при остановке VPS — берите новый ключ кнопкой"
	)
	L_TIER="Бесплатный тариф"
else
	L_WELCOME="Welcome to your free VPS"
	L_OS="OS";           L_KERNEL="Kernel";  L_HOST="Host"
	L_IP="IP address";   L_CPU="CPU";        L_RAM="Memory"
	L_DISK="Disk";       L_UPTIME="Uptime";  L_LOAD="Load"
	L_TIP="Tip"
	L_TIPS=(
		"htop for monitoring, tmux for persistent sessions, neofetch for specs"
		"Files are lost when the VPS is destroyed — keep your own backups"
		"apt install <package> works fine: you have full root access"
		"The SSH session dies when the VPS stops — grab a fresh key in Discord"
	)
	L_TIER="Free Tier"
fi

# ---- facts ----
os_name="$( . /etc/os-release 2>/dev/null; printf '%s' "${PRETTY_NAME:-Linux}" )"
kernel="$(uname -r)"
host_name="$(hostname 2>/dev/null || cat /etc/hostname 2>/dev/null || printf '%s' "${HOSTNAME:-vps}")"
ip_addr="$(hostname -I 2>/dev/null | awk '{print $1}')"
[ -n "$ip_addr" ] || ip_addr="—"
cpu_model="$(awk -F': ' '/model name/{print $2; exit}' /proc/cpuinfo 2>/dev/null)"
[ -n "$cpu_model" ] || cpu_model="virtual CPU"
cpu_count="$(nproc 2>/dev/null || echo 1)"
load="$(awk '{printf "%s  %s  %s", $1, $2, $3}' /proc/loadavg 2>/dev/null)"

mem_total="$(awk '/^MemTotal:/{printf "%d", $2/1024}' /proc/meminfo)"
mem_avail="$(awk '/^MemAvailable:/{printf "%d", $2/1024}' /proc/meminfo)"
mem_used=$(( mem_total - mem_avail ))
[ "$mem_total" -gt 0 ] 2>/dev/null || mem_total=1
mem_pct=$(( mem_used * 100 / mem_total ))

disk_used="$(df -h / 2>/dev/null | awk 'NR==2{print $3}')"
disk_size="$(df -h / 2>/dev/null | awk 'NR==2{print $2}')"
disk_pct="$(df -h / 2>/dev/null | awk 'NR==2{gsub("%","",$5); print $5}')"
[ -n "$disk_pct" ] || disk_pct=0

uptime_h="$(awk -v ru="$LANG_SEL" '{s=int($1); d=int(s/86400); h=int((s%86400)/3600); m=int((s%3600)/60);
	if (d>0) printf "%dd %dh %dm", d, h, m; else if (h>0) printf "%dh %dm", h, m; else printf "%dm", m}' /proc/uptime)"

tip="${L_TIPS[$(( RANDOM % ${#L_TIPS[@]} ))]}"

# ---- helpers ----
bar() { # bar <percent> -> colored gauge
	local pct="$1" width=18 filled color
	[ "$pct" -lt 0 ] 2>/dev/null && pct=0
	[ "$pct" -gt 100 ] 2>/dev/null && pct=100
	filled=$(( pct * width / 100 ))
	if   [ "$pct" -ge 85 ]; then color="$RD"
	elif [ "$pct" -ge 60 ]; then color="$YE"
	else color="$GR"; fi
	printf '%s' "$color"
	for ((i=0; i<filled; i++)); do printf '█'; done
	printf '%s' "$GY"
	for ((i=filled; i<width; i++)); do printf '░'; done
	printf '%s' "$R"
}

# Pad by visible characters, not bytes, so Cyrillic labels stay aligned.
pad() { # pad <text> <width>
	local text="$1" width="$2" len pad_str=""
	len=${#text}
	while [ "$len" -lt "$width" ]; do
		pad_str="$pad_str "
		len=$(( len + 1 ))
	done
	printf '%s%s' "$text" "$pad_str"
}

row() { # row <label> <value>
	printf "   ${BL}%s${R} ${GY}│${R} %s\n" "$(pad "$1" 12)" "$2"
}

# ---- render ----
printf '\n'
printf "${CY}${B}    ██████╗██╗      ██████╗ ██╗   ██╗██████╗ ██╗   ██╗${R}\n"
printf "${CY}${B}   ██╔════╝██║     ██╔═══██╗██║   ██║██╔══██╗╚██╗ ██╔╝${R}\n"
printf "${CY}${B}   ██║     ██║     ██║   ██║██║   ██║██║  ██║ ╚████╔╝ ${R}\n"
printf "${CY}${B}   ██║     ██║     ██║   ██║██║   ██║██║  ██║  ╚██╔╝  ${R}\n"
printf "${CY}${B}   ╚██████╗███████╗╚██████╔╝╚██████╔╝██████╔╝   ██║   ${R}\n"
printf "${CY}${B}    ╚═════╝╚══════╝ ╚═════╝  ╚═════╝ ╚═════╝    ╚═╝   ${R}\n"
printf '\n'
printf "   ${B}%s${R} ${GY}·${R} ${YE}%s${R} ${GY}·${R} ${GY}powered by Cloudy VPS Bot${R}\n" "$L_WELCOME" "$L_TIER"
printf "   ${GY}────────────────────────────────────────────────────────────${R}\n"

row "$L_OS"     "${B}${os_name}${R}"
row "$L_KERNEL" "${kernel}"
row "$L_HOST"   "${B}${host_name}${R}  ${GY}(${ip_addr})${R}"
row "$L_CPU"    "${cpu_model} ${GY}×${R} ${B}${cpu_count}${R}   ${GY}load:${R} ${load}"
row "$L_RAM"    "$(bar "$mem_pct")  ${B}${mem_used}${R}/${mem_total} MB ${GY}(${mem_pct}%)${R}"
row "$L_DISK"   "$(bar "$disk_pct")  ${B}${disk_used:-?}${R}/${disk_size:-?} ${GY}(${disk_pct}%)${R}"
row "$L_UPTIME" "${uptime_h}"
printf "   ${GY}────────────────────────────────────────────────────────────${R}\n"
printf "   ${GR}%s:${R} ${GY}%s${R}\n\n" "$L_TIP" "$tip"
