#!/usr/bin/env bash
# Cloudy VPS - compact login banner.
# Localized with CLOUDY_LANG=ru|en. Shows the VPS limits (cgroup / plan env),
# not the metrics of the physical host.

set -u

if [ -t 1 ]; then
	R=$'\e[0m'; B=$'\e[1m'
	CY=$'\e[38;5;81m'; GR=$'\e[38;5;114m'; YE=$'\e[38;5;221m'
	GY=$'\e[38;5;245m'; RD=$'\e[38;5;203m'
else
	R=""; B=""; CY=""; GR=""; YE=""; GY=""; RD=""
fi

LANG_SEL="${CLOUDY_LANG:-en}"
case "$LANG_SEL" in ru*) LANG_SEL="ru" ;; *) LANG_SEL="en" ;; esac

if [ "$LANG_SEL" = "ru" ]; then
	L_TIER="Бесплатный VPS"; L_RAM="ОЗУ"; L_DISK="Диск"; L_CPU="CPU"
	L_UP="онлайн"; L_HINT="banner — показать снова"
else
	L_TIER="Free VPS"; L_RAM="RAM"; L_DISK="Disk"; L_CPU="CPU"
	L_UP="uptime"; L_HINT="type 'banner' to show this again"
fi

# ---- facts -----------------------------------------------------------------
os_name="$( . /etc/os-release 2>/dev/null; printf '%s' "${PRETTY_NAME:-Linux}" )"
host_name="$(hostname 2>/dev/null || cat /etc/hostname 2>/dev/null || printf '%s' "${HOSTNAME:-vps}")"
ip_addr="$(hostname -I 2>/dev/null | awk '{print $1}')"
[ -n "$ip_addr" ] || ip_addr="-"

# CPU: cgroup quota first, then the plan env, then nproc.
cpu=""
if [ -r /sys/fs/cgroup/cpu.max ]; then
	cpu="$(awk '{if ($1 != "max" && $2 > 0) printf "%.3g", $1/$2}' /sys/fs/cgroup/cpu.max)"
elif [ -r /sys/fs/cgroup/cpu/cpu.cfs_quota_us ]; then
	q="$(cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us 2>/dev/null || echo -1)"
	p="$(cat /sys/fs/cgroup/cpu/cpu.cfs_period_us 2>/dev/null || echo 0)"
	[ "$q" -gt 0 ] 2>/dev/null && [ "$p" -gt 0 ] 2>/dev/null && \
		cpu="$(awk -v q="$q" -v p="$p" 'BEGIN{printf "%.3g", q/p}')"
fi
[ -n "$cpu" ] || cpu="${CLOUDY_CPU:-$(nproc 2>/dev/null || echo 1)}"

# RAM: cgroup limit / usage, so it reflects the VPS and not the host.
mem_total=0; mem_used=0
if [ -r /sys/fs/cgroup/memory.max ]; then
	lim="$(cat /sys/fs/cgroup/memory.max)"
	[ "$lim" != "max" ] && mem_total=$(( lim / 1048576 ))
	[ -r /sys/fs/cgroup/memory.current ] && \
		mem_used=$(( $(cat /sys/fs/cgroup/memory.current) / 1048576 ))
elif [ -r /sys/fs/cgroup/memory/memory.limit_in_bytes ]; then
	lim="$(cat /sys/fs/cgroup/memory/memory.limit_in_bytes)"
	[ "$lim" -lt 9223372036854771712 ] 2>/dev/null && mem_total=$(( lim / 1048576 ))
	[ -r /sys/fs/cgroup/memory/memory.usage_in_bytes ] && \
		mem_used=$(( $(cat /sys/fs/cgroup/memory/memory.usage_in_bytes) / 1048576 ))
fi
if [ "$mem_total" -le 0 ] 2>/dev/null; then
	mem_total="${CLOUDY_RAM_MB:-$(awk '/^MemTotal:/{printf "%d", $2/1024}' /proc/meminfo)}"
	mem_used=$(awk '/^MemTotal:/{t=$2} /^MemAvailable:/{a=$2} END{printf "%d", (t-a)/1024}' /proc/meminfo)
fi
[ "$mem_total" -gt 0 ] 2>/dev/null || mem_total=1
mem_pct=$(( mem_used * 100 / mem_total ))

# Disk: `df /` reports the whole host filesystem when no storage quota is
# applied to the container, which used to render a bogus "10/10 G". Trust df
# only when its size really matches the plan, otherwise measure the data the
# user actually owns.
disk_total_g="${CLOUDY_DISK_GB:-0}"
df_total_g="$(df -BG / 2>/dev/null | awk 'NR==2{gsub("G","",$2); print $2+0}')"
df_used_m="$(df -BM / 2>/dev/null | awk 'NR==2{gsub("M","",$3); print $3+0}')"
[ -n "$df_total_g" ] || df_total_g=0
[ -n "$df_used_m" ] || df_used_m=0

if [ "$disk_total_g" -le 0 ] 2>/dev/null; then
	disk_total_g="$df_total_g"
	disk_used_m="$df_used_m"
elif [ "$df_total_g" -le "$disk_total_g" ] 2>/dev/null; then
	# a real quota is in place, df is trustworthy
	disk_used_m="$df_used_m"
else
	# no quota: count the writable data instead of the whole host disk
	disk_used_m="$(timeout 4 du -sxm /root /home /var/log /tmp /opt /srv 2>/dev/null \
		| awk '{s+=$1} END{printf "%d", s}')"
	[ -n "$disk_used_m" ] || disk_used_m=0
fi
[ "$disk_total_g" -gt 0 ] 2>/dev/null || disk_total_g=1
disk_total_m=$(( disk_total_g * 1024 ))
[ "$disk_used_m" -gt "$disk_total_m" ] 2>/dev/null && disk_used_m="$disk_total_m"
disk_pct=$(( disk_used_m * 100 / disk_total_m ))
if [ "$disk_used_m" -ge 1024 ] 2>/dev/null; then
	disk_used_txt="$(awk -v m="$disk_used_m" 'BEGIN{printf "%.1fG", m/1024}')"
else
	disk_used_txt="${disk_used_m}M"
fi

uptime_h="$(awk '{s=int($1); d=int(s/86400); h=int((s%86400)/3600); m=int((s%3600)/60);
	if (d>0) printf "%dd %dh", d, h; else if (h>0) printf "%dh %dm", h, m; else printf "%dm", m}' /proc/uptime)"

# ---- helpers ---------------------------------------------------------------
bar() { # bar <percent> -> short colored gauge
	local pct="$1" width=10 filled color i
	[ "$pct" -lt 0 ] 2>/dev/null && pct=0
	[ "$pct" -gt 100 ] 2>/dev/null && pct=100
	filled=$(( pct * width / 100 ))
	if   [ "$pct" -ge 85 ]; then color="$RD"
	elif [ "$pct" -ge 60 ]; then color="$YE"
	else color="$GR"; fi
	printf '%s' "$color"
	for ((i=0; i<filled; i++)); do printf '▰'; done
	printf '%s' "$GY"
	for ((i=filled; i<width; i++)); do printf '▱'; done
	printf '%s' "$R"
}

# ---- render ----------------------------------------------------------------
printf '\n'
printf "  ${CY}${B}☁ CLOUDY VPS${R}  ${GY}·${R}  ${B}%s${R}  ${GY}·${R}  ${YE}%s${R}\n" \
	"$os_name" "$L_TIER"
printf "  ${GY}%s (%s)${R}  ${GY}·${R}  ${GY}%s${R} ${B}%s${R}\n" \
	"$host_name" "$ip_addr" "$L_UP" "$uptime_h"
printf "  ${B}%s${R} %s ${B}%s${R}/%s MB   ${B}%s${R} %s ${B}%s${R}/%sG   ${B}%s${R} ${B}%s${R}\n" \
	"$L_RAM"  "$(bar "$mem_pct")"  "$mem_used"       "$mem_total" \
	"$L_DISK" "$(bar "$disk_pct")" "$disk_used_txt" "$disk_total_g" \
	"$L_CPU"  "$cpu"
printf "  ${GY}%s${R}\n\n" "$L_HINT"
