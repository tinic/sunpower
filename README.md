# Reviving a SunPower ACPV Supervisor / SolarBridge PV Supervisor

How to bring a dead **SunPower ACPV Supervisor** (also sold as the
**SolarBridge PV Supervisor**, internally the **SolarBridge PM850 Power
Manager**; forum posts call these units **SPM-100, SPM-101, SPM-101-SPR,
SPM-102, SPM-103**) back to life, and how to get your panel data into
**Home Assistant** over **MQTT** now that SunPower monitoring and the
SolarBridge cloud are gone.

This is the box that sits next to the electrical panel of a SunPower **AC
module (ACPV)** system, for example **SPR-240E-WHT-U ACPV** or
**SPR-225E-BLK-U ACPV** panels with **SolarBridge Pantheon**
microinverters. It talks to the panels over the house wiring (powerline)
and used to upload to `sunpowermonitor.com` and `theenergybridge.com`.

## Typical symptoms

- The LCD is stuck on **"Starting application"** or **"Please Wait"**
- The box reboots in a loop, or works for a few hours and then hangs
- No data in the SunPower app or website (the services were shut down)
- Panels show 0 W in the local web page

In most cases **the SD card inside the box is worn out or corrupted**. The
card holds the box's `/var` partition: the application, its configuration
and all logs. The vendor software also logs and archives data forever, so
the card fills up and wears out. The operating system lives on internal
flash and is usually fine.

**Your panels keep producing power without the Supervisor.** SunPower's own
tech note T13004 says: "ACPV modules will continue to produce energy in
the absence of monitoring functionality." The Supervisor is for
monitoring and configuration.

## What this repo gives you

- [Step-by-step revival](docs/revive.md): image the old card, rebuild a
  clean card, flash it, check it
- Tools that work on a Mac or Linux without root and without mounting
  anything:
  - [`tools/extract.py`](tools/extract.py): card image → file tree plus a
    manifest of owners, modes and links
  - [`tools/apply-overlay.py`](tools/apply-overlay.py): disables the dead
    vendor cloud software, stops the logging that wears out the card,
    adds SSH access and the Home Assistant bridge, removes unused files
  - [`tools/make-card.py`](tools/make-card.py): file tree → flashable card
    image in the exact ext3 format the box's 2013 kernel needs
- [Home Assistant MQTT bridge](docs/home-assistant.md): per-panel power,
  energy, voltages and temperature, with MQTT discovery, in a few hundred lines
  of Python 2.6 that run on the box itself
- Documentation of everything we found:
  [hardware](docs/hardware.md), [software and boot process](docs/software.md),
  [SSH access](docs/ssh.md), [vendor cloud and why to disable it](docs/vendor-cloud.md),
  [internal flash](docs/internal-flash.md), [microinverters and `sbti`](docs/inverters.md),
  [history of the companies and services](docs/history.md),
  [troubleshooting](docs/troubleshooting.md)

**This repo contains no SunPower or SolarBridge software.** Their code is
copyrighted, so the tools work on an image of *your own* card. Keep a copy
of your old card image; if it is too damaged, see
[troubleshooting](docs/troubleshooting.md).

## Quick start

You need: a card reader, a new SD card of 2 GB or more (high-endurance or
industrial recommended), Python 3, and e2fsprogs
(`brew install e2fsprogs` on macOS, `apt install e2fsprogs` on Linux).

```sh
# 1. Image the old card (find the right disk first: diskutil list / lsblk)
sudo dd if=/dev/rdiskN of=old-card.img bs=4m

# 2. Extract it, apply our changes, build a new card image
tools/extract.py old-card.img mycard --exclude tools/exclude.txt
ssh-keygen -t rsa -b 4096 -f ~/.ssh/sunpower_rsa        # RSA only, see docs/ssh.md
cp overlay/home/sunbridge/sunbridge.conf.example mqtt.conf   # edit for your broker
tools/apply-overlay.py mycard --ssh-key ~/.ssh/sunpower_rsa.pub --mqtt-conf mqtt.conf
tools/make-card.py --repo mycard --out new-card.img

# 3. Write it to the new card and put the card in the box
sudo dd if=new-card.img of=/dev/rdiskN bs=4m
```

Details, checks and pitfalls are in [docs/revive.md](docs/revive.md).

## Status

Done on our own box (19 Pantheon microinverters, November 2026):

- New card built and booting; vendor cloud software disabled
- Root SSH access; internal flash backed up and cleaned up (it was 95%
  full)
- Bridge tested on the box against a broker, including broker down,
  broker restart and crash cases

Still open:

- Parsing the live output of `sbti -m` (the inverters only answer in
  daylight); until then the bridge publishes zeros. See
  [docs/inverters.md](docs/inverters.md)

Contributions and reports from other owners are welcome, especially from
other SPM models and other panel brands (the software supports AUO, BenQ,
Blueline, Eoplly, ET Solar, Mage, Solarland, Talesun and Tindo branding).
