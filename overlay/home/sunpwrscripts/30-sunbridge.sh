#!/bin/bash
# Run by /etc/rc.local at every boot. Keeps the MQTT bridge to Home Assistant
# running. No output and no files: the bridge keeps all state in memory, and
# -B stops Python from writing .pyc files.
exec >/dev/null 2>&1 </dev/null

while true; do
	/usr/bin/python -B /home/sunbridge/sunbridge.py
	sleep 30
done
