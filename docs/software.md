# Software and boot process

## Operating system

- **Ubuntu 9.04 "Jaunty Jackalope" armel** (`/etc/lsb-release`), Debian
  base 5.0 (`/etc/debian_version`). It was the last Ubuntu release for
  ARMv5; there are no newer versions for this CPU.
- Some packages come from **Debian 6 "Squeeze"**: Apache 2.2.16, PHP 5.3.3.
- `apt` sources point only at `ports.ubuntu.com ... jaunty` (no updates or
  security archives), so the box runs its original 2009-2013 package
  versions. Treat it as unpatchable: keep it on your LAN only.
- Python 2.6.2, Perl 5.10, PHP 5.3, OpenSSH 5.1p1, Apache 2.2.
- About 250 packages; 93% of the files on the root filesystem are
  unmodified Ubuntu/Debian files.
- Kernel **2.6.31.84-SBT** (built 2013-03-21), custom SolarBridge build
  with drivers for the powerline modem (`plcspi`), LCD (`hd44780`) and
  sensors.

## Where things live

| Location | Storage | Contents |
|---|---|---|
| `/` | internal NAND, JFFS2 (248 MB) | OS, vendor packages `powermanager`, `libsbidirect`, `plctools`; `/etc` configuration |
| `/var` | **SD card**, ext3, one partition | Application, configuration, data, logs, swap file, package database |
| `/home` | symlink into `/var/home` | `data_logger`, `httpd`, `sbtech`, `sunpwrscripts` |
| `/tmp`, `/var/run`, `/var/lock`, `/var/tmp`, `/dev/shm` | RAM (tmpfs) | |

Without an SD card the box still boots: SSH works, but Apache and the
application do not.

## Boot sequence

1. Bootloader (`mtd0`) loads the kernel (`mtd1`), root on JFFS2 (`mtd2`).
2. `rcS.d`: `checkfs.sh` checks the SD card (the filesystem check interval
   is 1 day and 38 mounts), `S31repairvarfs` runs a forced
   `fsck` if `/begin_repair_var_fs` exists, `mountall` mounts the card on
   `/var` (from `/etc/fstab`) and enables `/var/swaps/swapfile`.
3. `rc2.d`: `sysklogd`, `klogd`, `dbus`, `ssh` (port 45871), `firstboot`,
   `bootlogs`, `anacron`, `cron`, `apache2`, `ondemand`, then `rc.local`.
   The vendor's `pmsysctl`, `sbtmenu` and `anytermd` are linked as `K`
   (off) in runlevel 2 on our unit.
4. `/etc/rc.local` (vendor, dated 2013-12-31):
   - counts boots in `/home/data_logger/bootcount`
   - archives logs with `file_rotate` into `/home/data_logger/logarchive`
   - manages `/etc/ssh/authorized_keys` (see [ssh.md](ssh.md))
   - runs `/home/data_logger/util/getlayout.sh` (converts the panel layout)
   - runs `/home/data_logger/util/sysmon.sh`, which starts the `sysmon`
     watchdog, which starts `data_logger`
   - runs **every file in `/home/sunpwrscripts/`** with `bash`, in the
     background, appending output to `/home/sunpwrscripts.log`. This is on
     the card, so it is the place to start your own software without
     touching the internal flash. Our overlay uses it.

## Scheduled jobs (`/etc/crontab`)

| Schedule | Job | Purpose |
|---|---|---|
| :11, :41 | `file_rotate ... logarchive` | archive logs |
| daily | `bin/connect -s -t 60 -x 300` | reverse SSH tunnel to the vendor |
| weekly | `util/sync_docs.sh` | download docs from the vendor over SSH |
| every 15 min | `util/check_networking.sh` | restart networking when its self-test (HTTP to `www.google.com`, pings, gateway) fails |
| every 2 min | `touch /dev/shm/sysmon_cron_check` | proves cron is alive to `sysmon` |
| every 2 min | `util/getlayout.sh` | regenerate the layout if `pm.conf` changed |
| every 30 min | `sbti -g` | ping the inverter array |
| every 3 min | `util/sbmenu.sh` | keep the LCD menu `sbtmenu` running |
| weekly | `/etc/cron.weekly/fortnightly.sh` | reboot every second week |

All jobs except `sbmenu.sh` append to `/home/data_logger/cron.log` on the
card. Together with the log archiving at every boot, this is why cards
fill up and wear out.

## Two vendor application stacks

The box runs two generations of vendor software side by side:

1. **SunPower Data Logger** (`/home/data_logger`, build b239 of
   2013-12-31). `data_logger` polls the inverters through `sbti` and
   `libsbidirect`, stores archives in `arc_data/`, and uploads to
   `collector.sunpowermonitor.com`. It has Lua device drivers for many
   inverters and meters (SolarBridge, Fronius, KACO, SMA, Satcon,
   Power-One, Santerno, Shark, Veris, WattNode, ION 8600). Web UI on
   port 80 (Perl CGI in `/home/httpd`).
2. **SolarBridge Power Manager V3** (`powermanager` 3.0.10321, installed
   2013-08-08). PHP web UI on port **14573** (`/var/www`), command and
   data agent `pmSysCtl` (cloud `theenergybridge.com`), LCD menu
   `sbtmenu`, many helper tools in `/usr/local/bin`. Its own poller
   (`task.php?task=poll` from root's crontab) was removed by the 2014
   data logger update.

Both cloud services are gone; see [vendor-cloud.md](vendor-cloud.md).

## Network services

| Port | Service |
|---|---|
| 45871/tcp | OpenSSH 5.1p1, root only, keys only ([ssh.md](ssh.md)) |
| 80/tcp | Data logger web UI (no login) |
| 14573/tcp | Power Manager web UI (PHP); forum posts report the login `admin` / `admin` |

## Important files on the card

| Path (under `/var`) | Contents |
|---|---|
| `sb/pm.conf` | Power Manager configuration (JSON): site, time zone, servers, every microinverter with serial, firmware, grid profile and roof position |
| `sb/pmversions/` | History of `pm.conf` versions |
| `sb/active-grid-settings.json`, `sb/grid-settings-*.conf` | Grid trip limits (voltage, frequency and times) |
| `sb/data/YYYY/*.csv` | Per-inverter readings from the PHP poller |
| `home/data_logger/config.lua` | Data logger settings (upload URLs, intervals, quotas) |
| `home/data_logger/devices.lua` | Device list for the data logger (inverter serials and firmware) |
| `home/data_logger/mi_trip_settings.lua` | Microinverter trip settings |
| `home/data_logger/bin/sbti` | Command-line tool for the Power Manager and inverters ([inverters.md](inverters.md)) |
| `lib/dpkg/` | Package database for the OS on the internal flash. Keep it. |
| `swaps/swapfile` | Swap file (the box uses about 40 MB of RAM) |

The readings in `sb/data` CSV files have these columns: `ts,
mi_generation, dc_amps, panel_status, ac_volts, vbus_avg, frequency,
created_timestamp, sb_serial_number, sim_serial_number, dc_volts,
temperature, ac_amps_measured, vbus_min, vbus_max, dc_watts, power, ac_amps,
lte, lte_modified, seqno, vbsd, vpsd, hwpsd, mode, firmware_revision,
plc_attempts, ac_vl1, ac_vl2, shutdown, ic_temp, a0..a31 alert counts and
values, gen1_alert_code, gen1_alert_value, gen1_alert_count, data_write_ts,
a_seq`. `lte` is lifetime energy.

## Card format

The box's kernel (2.6.31) needs a classic ext3 filesystem:

- MBR, one bootable type 0x83 partition starting at sector 2048
- ext3, 4 KiB blocks, 256-byte inodes, 32 MB journal, features
  `has_journal ext_attr resize_inode dir_index filetype sparse_super
  large_file` and **no** ext4 features (`extent`, `flex_bg`, `huge_file`,
  `metadata_csum`, `64bit` ...)
- Our original card: 2 GB, partition of 3903488 sectors

`tools/make-card.py` builds exactly this.
