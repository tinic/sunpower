#!/bin/bash
# Run by /etc/rc.local at every boot.
#
# Keeps system logs off the SD card: mounts a small tmpfs over /var/log and
# restarts the daemons that write there, so they reopen their files in RAM.
# Logs from early boot (before rc.local) still go to the card underneath.
exec >/dev/null 2>&1

mountpoint -q /var/log && exit 0
mount -t tmpfs -o size=16m,mode=0755 varlog /var/log || exit 1

mkdir -p /var/log/apache2 /var/log/apt /var/log/fsck /var/log/news
touch /var/log/wtmp /var/log/btmp /var/log/lastlog /var/log/faillog
chown root:utmp /var/log/wtmp /var/log/btmp /var/log/lastlog
chmod 664 /var/log/wtmp /var/log/lastlog
chmod 660 /var/log/btmp

/etc/init.d/sysklogd restart
/etc/init.d/klogd restart
/etc/init.d/apache2 restart
