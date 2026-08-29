#!/bin/sh
# Re-arm templog after a reboot (/etc is volatile tmpfs overlay: the timer
# unit and udev rule die on reboot; script + CSV + sleep hook survive).
# Run: /home/root/templog/install.sh
set -e
DIR=/home/root/templog

cp $DIR/templog.service $DIR/templog.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now templog.timer

mkdir -p /etc/udev/rules.d
cp $DIR/99-templog.rules /etc/udev/rules.d/
udevadm control --reload

# sleep hook lives on the RO rootfs and normally survives; reinstall if gone
if [ ! -f /usr/lib/systemd/system-sleep/sleep-templog.sh ]; then
  mount -o remount,rw /
  cp $DIR/sleep-templog.sh /usr/lib/systemd/system-sleep/
  chmod +x /usr/lib/systemd/system-sleep/sleep-templog.sh
  mount -o remount,ro /
fi

$DIR/templog.sh boot
echo "templog armed"
