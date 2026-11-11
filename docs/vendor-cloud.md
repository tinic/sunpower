# The vendor cloud software, and why to disable it

Both cloud services the box talks to are gone. The software keeps trying,
fills the card with logs and archives, and still accepts commands from
whoever answers on those domain names. If someone registers or takes over
one of them, they get root on your box.

## What phones home

| Piece | Where | Started by | Talks to | What it can do |
|---|---|---|---|---|
| `data_logger` | card `/home/data_logger/bin` | `sysmon` (from `rc.local`) | `collector.sunpowermonitor.com` (data and command channels) | upload data; run remote commands, including software upgrades (`util/upgrade.sh`) and reboots |
| `sysmon` | card | `util/sysmon.sh` from `rc.local` | | watchdog for `data_logger`; opens a reverse SSH tunnel after errors |
| `connect` | card | `/etc/crontab`, daily | `remoteproxy.sunpowermonitor.com` | **reverse SSH tunnel**: a shell on your box for the other end |
| `sync_docs.sh` | card | `/etc/crontab`, weekly | `remoteproxy.sunpowermonitor.com` over SSH | download documentation |
| `pmSysCtl` (Power Manager V3) | flash `/usr/local/bin` | `/etc/init.d/pmsysctl` (runlevel link `S48` or `K48`) | `syscon1/2.theenergybridge.com` (heartbeat), `data1/2.theenergybridge.com` | runs commands from the server: reverse SSH (`pmRSSH`), firmware install (`pmFwInstall`), send data, reboot |
| `checkmem.sh` | flash | vendor maintenance | `www.theenergybridge.com/rms` | reports to the vendor |

The vendor also used an FTP server on Amazon EC2 for upgrades.

## What our overlay changes

All on the card; the internal flash stays untouched:

- `bin/data_logger` and `bin/connect` are replaced by stubs that exit
- `util/sysmon.sh` no longer starts `sysmon`/`data_logger`
- `util/sync_docs.sh` is a stub
- `/home/sunpwrscripts/10-disable-vendor-cloud.sh` runs
  `/etc/init.d/pmsysctl stop` at every boot and kills `pmRSSH`,
  `pmSendData`, `pm2Cloud`, `rsuptun.sh`
- In `sb/pm.conf`, every `*.theenergybridge.com` server becomes `127.0.0.1`

The originals are kept in `/home/data_logger/vendor-disabled/`. To undo a
change, copy the file back (and delete the hook for `pmSysCtl`).

## What keeps working

- LCD menu (`sbtmenu`)
- Both local web UIs (ports 80 and 14573)
- `sbti` and the powerline link to the inverters
- Log rotation, the network self-check, the fortnightly reboot

## Without our tools

If you only want to stop the phoning home on a running box, as root:

```sh
DL=/home/data_logger
mkdir -p $DL/vendor-disabled
for f in bin/data_logger bin/connect util/sysmon.sh util/sync_docs.sh; do
    cp -p $DL/$f $DL/vendor-disabled/
    printf '#!/bin/sh\nexit 0\n' > $DL/$f
done
/etc/init.d/pmsysctl stop
```

Then add the `pmsysctl stop` line to a file in `/home/sunpwrscripts/` so
it survives reboots.
