# Troubleshooting

## The LCD shows "Starting application" forever

Usually the SD card: worn out, corrupted, or full. Image it and rebuild a
card ([revive.md](revive.md)). Other owners report that a plain clone to
a new card helps only for a while, because the full logs and archives come
along; `extract.py` and `apply-overlay.py` leave them out and stop the
software that writes them.

## "Please Wait" freeze

Known Supervisor bug before the 2013 "V3" firmware (SunPower tech note
T13004). A power cycle helped. If your box still has pre-V3 software,
please tell us.

## The box boots but there is no web page

Without a working SD card the box still boots from internal flash, and
SSH on port 45871 answers, but Apache and the application need `/var`
from the card. Check `mount | grep /var`.

## I can not log in over SSH

See [ssh.md](ssh.md): only root, only keys, only RSA, and the keys are in
`/etc/ssh/authorized_keys` on the internal flash. Install a key with
`apply-overlay.py --ssh-key` and rebuild the card.

Modern clients refuse the box's old algorithms unless you allow
`ssh-rsa` (see the config in [ssh.md](ssh.md)).

## SSH or everything is slow right after changes

If the internal flash is nearly full, JFFS2 garbage collection
(`jffs2_gcd_mtd2`) can take all CPU for minutes after writes. See
[internal-flash.md](internal-flash.md).

## `sbti -m` fails

- At night: normal; the inverters have no power. Try in daylight.
- `File does not exist: /usr/local/sbin/plctools/plcioctl_old`: restore
  that file (and the other `*_old` files) from your flash backup.
- `InvDir Error Code (1) Generic failure of transaction` in daylight: the
  inverter does not answer on the powerline. Check that it produces power
  and that `sbti -l` lists it.

## Some inverters report but produce nothing

Owners of a related SolarBridge system reported inverters that were
online but had output disabled, as if the grid were down, and that
freeing space on a full manager brought some back. Check `sbti -m` and
the trip settings (`sbti -t <serial>`) before changing anything.

## My card image is unreadable

Try `ddrescue`, then `e2fsck -fy` on a copy of the partition. If the
filesystem is beyond repair, the application files are the same on every
unit of the same software version, but your configuration (`sb/pm.conf`
with your inverter list and grid settings) is unique. We can not
distribute the vendor files. Ask in the issues: another owner may help.

## The box restarts its network every 15 minutes

`/home/data_logger/util/check_networking.sh` (from `/etc/crontab`)
restarts networking when its self-test fails (`netw_check`: HTTP to
`www.google.com`, pings, the gateway). On a LAN without internet access, stub that script too.
