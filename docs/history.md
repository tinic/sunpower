# History

## Companies and services

These are leads from public sources, not legal advice. Check them yourself
if it matters to you.

- **SolarBridge Technologies, Inc.** was founded in 2004 as a University
  of Illinois spin-out and made the Pantheon microinverter. SunPower used
  it in its first AC modules (2011).
- **SunPower** acquired SolarBridge in 2014.
- In **2018** SunPower sold the former SolarBridge microinverter business
  to **Enphase Energy**. Enphase does not support SolarBridge units.
- **SunPower** filed for bankruptcy in **2024** and its assets were sold.
  Legacy SunPower monitoring is serviced by SunStrong Management
  (see the community project [sungazer](https://sungazer.readthedocs.io/)).
- A new company, SolarBridge Technology Inc., revived the brand name in
  2025 and states it is unrelated to the original.
- The monitoring services `sunpowermonitor.com` (SunPower Monitoring
  System) and `theenergybridge.com` (SolarBridge) no longer work for these
  boxes.

## Software timeline from one box

From file dates, package records and logs on our unit:

| Date | Event |
|---|---|
| 2009-04 | Ubuntu 9.04 base |
| 2010-05 | Base system assembled |
| 2012-06 | Powerline tools and SBMS management app |
| 2012-2013 | Power Manager web UI |
| 2013-03-21 | Kernel 2.6.31.84-SBT built |
| 2013-04/05 | Inverter firmware 2406, 2407, 2357 |
| 2013-06-06 | SunPower tech note T13004 "ACPV Gen1 Firmware Upgrade Plan": known Supervisor freezes ("Please Wait"), lost communication, lifetime energy spikes, lost layouts; fixed by a "V3" Supervisor firmware and new inverter firmware |
| 2013-08-08 | Power Manager 3.0.10321 ("V3") installed remotely |
| 2013-11 | Inverters upgraded from 2357 to 2406 remotely, about 40 minutes per panel |
| 2013-12-31 | Data logger build b239 |
| 2014-02-10 | b239 installed remotely; the last vendor software update |
| 2018-04 | Last configuration change (cloud servers at `theenergybridge.com`) |
| 2021-11 | SD card corrupted; repaired by hand |
| 2026-11 | SD card failed again; this project |

## Related reading

- kuzyatech.com, "Debugging stuck SunPower SolarBridge": teardown with
  board photos and a card-cloning repair
- SolarPanelTalk forum threads: "Sunpower SolarBridge Gateway gets stuck
  on 'Starting application'", "Why your SolarBridge SPM-100, SPM-101,
  SPM-102, SPM-103 is not working", "Now that SolarBridge monitoring is
  gone", "Sunpower PVS6 / Solarbridge SPM-101-SPR Compatibility"
