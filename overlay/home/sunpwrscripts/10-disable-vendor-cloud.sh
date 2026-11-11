#!/bin/bash
# Run by /etc/rc.local at every boot (it runs each file in /home/sunpwrscripts).
#
# Stops the Power Manager V3 cloud agent. pmSysCtl lives on the internal flash
# and starts from /etc/rc2.d/S48pmsysctl; it sends heartbeats to
# theenergybridge.com and runs whatever commands come back (reverse SSH,
# firmware install, reboot). Its servers in /var/sb/pm.conf point to
# 127.0.0.1 as a second line of defence.

exec >/dev/null 2>&1
/etc/init.d/pmsysctl stop
killall -q pmRSSH pmSendData pm2Cloud rsuptun.sh

