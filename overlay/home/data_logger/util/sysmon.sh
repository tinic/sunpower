#!/bin/sh
# Called from /etc/rc.local at boot. The vendor version started the system
# monitor, which ran and watched the data logger, and opened a reverse SSH
# tunnel to the vendor after errors. Both are disabled; the original is in
# /home/data_logger/vendor-disabled/sysmon.sh.
echo "$(date): sysmon/data_logger disabled (vendor cloud is gone)"
