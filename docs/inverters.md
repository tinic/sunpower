# Microinverters and `sbti`

## The inverters

SunPower ACPV Gen 1 panels carry a **SolarBridge Pantheon** microinverter
(225 W AC, 240 V; see [hardware.md](hardware.md)). They run from the
panel's DC power, so **at night they are off** and do not answer on the
powerline. They produce power on their own; the Supervisor only monitors
and configures them.

Each inverter has a 15-digit serial number. The Power Manager keeps the
list in `/var/sb/pm.conf` (`summary[0].microinverters`), together with
firmware version, model ("6"), generation (1), grid profile (for example
`IEEE-1547`) and position on the roof drawing.

## `sbti`: the command-line tool

`/home/data_logger/bin/sbti` (on the card) talks to the Power Manager and
the inverters through `libsbidirect` and the `plcspi` driver. It needs
`LD_LIBRARY_PATH=/home/data_logger/lib`.

| Command | Does |
|---|---|
| `sbti -v` | Power Manager hardware and software versions (ours: hw 0002, sw 10732-B9398) |
| `sbti -s` | Power Manager serial number |
| `sbti -l` | List the inverters the Power Manager knows |
| `sbti -m <serial>` | Current metrics and alerts of one inverter |
| `sbti -t <serial>` | Show its trip point settings |
| `sbti -t <serial> <setting> <value>` | Set a trip point: max/min (`mx`, `mn`), frequency/voltage (`f`, `v`), limit/time (`l`, `t`), level (`1`, `2`), for example `mxfl1` |
| `sbti -g` | Ping the whole array (cron runs this every 30 minutes) |
| `sbti -r` | Resync the InvDir library cache |
| `sbti -a <serial>` | Add an inverter manually |
| `sbti -e <serial>` | Erase one or all inverters from the Power Manager |
| `sbti -f <serial> <file>` | Update an inverter's firmware |

Notes:

- At night, `sbti -m` waits about 30 seconds and then fails with
  `InvDir Error Code (1) Generic failure of transaction.`
- `sbti` needs `/usr/local/sbin/plctools/plcioctl_old` on the internal
  flash. Do not delete the `*_old` files there.
- Calls are serialised with the lock `/var/lock/sbti.sync`.
- Every call rewrites the inverter directory cache `/var/sb/.sbidirect.mil`
  and keeps a numbered copy (`.sbidirect_<unix time>.mil`, 7 KB; the
  library keeps 51). That is about 14 KB written to the card per call.
- One `sbti -m` takes about 7 seconds when the inverter answers.

Real output on an overcast November morning (2026-11-11, 08:11 local):

```
$ sbti -m 194051230005285
Inverter Generation = 1
Inverter firmware version = 2406
Total Lifetime Energy in Watt hours = 4.24896e+06
Present AC Power Generating in Watts = 7.2
Average DC voltage over report period in Volts = 39.85
DC Current in Amps = 0.345
DC Power in Watts = 13.6
AC Voltage line 1 to line 2 = 242.98
Commanded Line AC Amperage in Amps = 0.081
Measured Line AC Amperage in Amps = 0.099
Line Frequency in Hertz = 60
Temperature in celsius = 19
No alerts found
```

Lifetime energy is printed with 6 significant digits (10 Wh steps at this
size). The `sbti` binary also contains `Line AC Voltage line 1/2 to
neutral`, `IC temperature in celsius` and `Alert ...` lines, which our
inverters did not print. The vendor data logger used the same fields (ids
1 to 8 and 11 in `lua_scripts/solarbridge.lua`).

**Trip settings (`-t`) are the grid protection limits your utility
requires**, and **firmware updates (`-f`) take about 40 minutes per panel
over the powerline and can fail.** In 2013 one of our inverters failed to
associate during the vendor's own update run. Read before you write.

## Firmware

| Version | Date | Notes |
|---|---|---|
| 2357 | image dated 2013-05-15 | original Gen 1 firmware |
| 2406 | 2013-04-20 | installed by SunPower's 2013 remote upgrade ("V3"; tech note T13004) |
| 2407 | 2013-04-20 | treated as equal to 2406 by the vendor's update script; not deployed on our site |

The images (`inverter_release_0.4.<version>.bfe`, 64 KiB each) were on the
card in `/home/data_logger/` and `/home/updatetmp/mi_update/`, with the
update script `mi_update.sh` and logs of each inverter's update.
`apply-overlay.py` removes them from the new card (keep your old card
image if you want them). We know of no later firmware, and the vendors no
longer exist in their original form ([history.md](history.md)).

## Grid settings

`/var/sb/active-grid-settings.json` on our unit:

```json
{"VLow":"211.0", "VLowTime":"2.6", "VHigh":"256.5", "VHighTime":"232.6",
 "FreqLow":"57.0", "FreqLowTime":"0.2", "FreqHigh":"60.5", "FreqHighTime":"147.2"}
```

Grid profiles live in `sb/grid-settings-std.conf` and
`grid-settings-custom.conf`; `/usr/local/sbin/pmSetTripLimits` and
`/usr/local/bin/tripcheck` on the flash apply and check them.
