#!/bin/sh
# templog.sh <event> — append one CSV sample of all temperature sensors +
# power state to /home/root/templog/templog.csv.
#
# Events: timer (5-min cadence / RTC wake), suspend, resume, udev-charger,
#         manual, boot. Callers pass the tag; sampling is identical.
#
# Units: cpu/board/accel in milli-degC, batt in deci-degC (fuel gauge raw),
# current in uA (positive = charging), voltage in uV.

EV="${1:-manual}"
DIR=/home/root/templog
CSV=$DIR/templog.csv
mkdir -p "$DIR"

rd() { cat "$1" 2>/dev/null || echo ""; }

TS=$(date +%s)
ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
UP=$(cut -d' ' -f1 /proc/uptime)

CPU=$(rd /sys/class/thermal/thermal_zone0/temp)
BATT=$(rd /sys/class/power_supply/max77818_battery/temp)
BOARD=$(rd /sys/class/hwmon/hwmon4/temp1_input)
ARAW=$(rd /sys/bus/iio/devices/iio:device2/in_temp_raw)
AOFF=$(rd /sys/bus/iio/devices/iio:device2/in_temp_offset)
ACC=""
[ -n "$ARAW" ] && [ -n "$AOFF" ] && ACC=$(( (ARAW + AOFF) * 625 / 10 ))

CAP=$(rd /sys/class/power_supply/max77818_battery/capacity)
ST=$(rd /sys/class/power_supply/max77818_battery/status)
CUR=$(rd /sys/class/power_supply/max77818_battery/current_now)
VOLT=$(rd /sys/class/power_supply/max77818_battery/voltage_now)
CHG=$(rd /sys/class/power_supply/max77818-charger/online)
WR=$(rd /sys/devices/platform/soc@0/44000000.bus/44340000.i2c/i2c-0/0-0008/slg46824-wakeup.1.auto/wakeup_reason)

[ -f "$CSV" ] || echo "iso,epoch,uptime,event,cpu_mC,batt_dC,board_mC,accel_mC,capacity_pct,status,current_uA,voltage_uV,charger_online,wakeup_reason" > "$CSV"

# flock serializes udev/timer/sleep-hook writers
exec 9>>"$CSV"
flock 9
echo "$ISO,$TS,$UP,$EV,$CPU,$BATT,$BOARD,$ACC,$CAP,$ST,$CUR,$VOLT,$CHG,$WR" >&9
