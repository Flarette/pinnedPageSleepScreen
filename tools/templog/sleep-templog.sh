#!/bin/sh
# systemd-sleep hook: sample temps at suspend entry and resume (with SPLD
# wakeup_reason on the resume side). Lives in /usr/lib/systemd/system-sleep
# (this build ignores /etc/systemd/system-sleep).
case "$1" in
  pre)  /home/root/templog/templog.sh suspend ;;
  post) /home/root/templog/templog.sh resume ;;
esac
exit 0
