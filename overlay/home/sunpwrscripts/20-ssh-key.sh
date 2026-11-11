#!/bin/bash
# Run by /etc/rc.local at every boot.
#
# Installs our key for root logins. sshd only allows root and reads keys from
# /etc/ssh/authorized_keys on the internal flash (port 45871, no passwords).
# rc.local restores that file from authorized_keys.new (and .x) 30 minutes
# after boot, so the key goes into those copies as well.

exec >/dev/null 2>&1
KEY='@KEY@'  # filled in by tools/apply-overlay.py --ssh-key
DIR=/etc/config/ssh
[ -d "$DIR" ] || DIR=/etc/ssh

for f in "$DIR/authorized_keys" "$DIR/authorized_keys.new" "$DIR/authorized_keys.x"; do
	[ -f "$f" ] || [ "$f" = "$DIR/authorized_keys" ] || continue
	grep -qF "$KEY" "$f" 2>/dev/null || echo "$KEY" >> "$f"
done
chmod 600 "$DIR"/authorized_keys*

