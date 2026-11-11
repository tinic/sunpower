# Hardware

What we found on our unit by reading `/proc/cpuinfo`, the kernel log and
the vendor datasheet. Other units may differ in details.

## Identification

| Field | Value |
|---|---|
| Marketing name | SunPower ACPV Supervisor; SolarBridge PV Supervisor |
| `/proc/cpuinfo` "Hardware" | **SolarBridge PM850 Power Manager** |
| Assembly number ("ASM #") | 850-00016 |
| Revision / Release / Version | 06 / 40 / 0002 |
| Forum model names | SPM-100, SPM-101 (SPM-101-SPR), SPM-102, SPM-103 |
| Enclosure | Type 3R, 13.3 x 7.9 x 3.5 in (33.8 x 20 x 8.9 cm) (datasheet) |

The Power Manager serial number is the CPU serial (`Serial` in
`/proc/cpuinfo`, printed by `/home/data_logger/bin/getuid`).

## Main parts

| Part | Details | Linux view |
|---|---|---|
| CPU | Freescale **i.MX25**, ARM926EJ-S (ARMv5TEJ), 24 MHz reference clock, BogoMIPS 199 | `armv5tejl`, machine "SolarBridge PM850 Power Manager", board code derived from the Freescale `mx25_3stack` |
| RAM | 256 MB (2 x 128 MB) | `MemTotal: 255920 kB` |
| Internal flash | 256 MB Hynix NAND (ID 0xad/0xda), 128 KiB erase blocks | `mtd0` bootloader 3 MB, `mtd1` kernel 5 MB, `mtd2` root filesystem 248 MB (JFFS2). See [internal-flash.md](internal-flash.md) |
| SD card slot | SDHC, Freescale `mxsdhci` | `/dev/mmcblk0`, partition 1 is mounted as **`/var`** |
| Ethernet | i.MX25 FEC with SMSC **LAN8710/LAN8720** PHY | `eth0`, DHCP |
| Powerline modem | Talks to the microinverters over the AC wiring; attached over SPI. A teardown by kuzyatech.com reports an ST7540 powerline transceiver | kernel module `plcspi`, device `/dev/plc`, options in `/etc/default/plcspi` |
| LCD | HD44780-compatible character LCD (LCD-Linux 0.13.9 driver) | module `hd44780`; driven by `/sbin/sbtmenu` |
| Buttons | GPIO keys for the LCD menu, power key | `gpio-keys`, `mxc_init_power_key` |
| Temperature sensor | TI **TMP421** on I2C (address 0x2a) | module `tmp421` |
| Real-time clock | Intersil **ISL12008** on I2C (address 0x68) | `/dev/rtc0` |
| Watchdog | i.MX watchdog, 60 s initial timeout | `/dev/watchdog` |
| USB | One host port (EHCI); udev rules auto-mount USB sticks; a stick labelled `SBT_UPDATE` triggers the vendor update tool | module `ehci_hcd` |
| ADC | i.MX25 touchscreen/ADC block (`imx_adc`) | |
| Serial console | i.MX UART 1 at **115200 baud** | `ttymxc0`, kernel command line `console=ttymxc0,115200`; a getty runs on it (`/etc/event.d/ttymxc0`) |

We have not opened our unit, so we cannot say where the serial header is.
The kuzyatech.com teardown ("Debugging stuck SunPower SolarBridge") has
board photos.

## Communication paths

- **To the panels:** powerline communication (PLC) on the AC branch
  circuit. Each microinverter has a 15-digit serial number (for example
  `0070512100xxxxx` or `1940512300xxxxx`).
- **To your network:** Ethernet. The firmware also has setup pages for
  Wi-Fi and cellular (`wificomm.tmpl`, `cellcomm.tmpl`, `set_cellular.sh`);
  we have not seen that hardware.

## Panels and microinverters

| Item | Details |
|---|---|
| Panels | SunPower ACPV (AC module) Gen 1: **SPR-225E-BLK-U ACPV**, **SPR-240E-WHT-U ACPV**, **SPR-245NE-WHT-U-240 ACPV** |
| Microinverter | SolarBridge **Pantheon** (Gen 1), mounted on the panel |
| Panel (SPR-240E) | 240 W, 19.3% efficiency, Vmpp 40.5 V, Impp 5.93 A, Voc 48.6 V, Isc 6.30 A |
| Microinverter output | 225 W AC max continuous, 240 V nominal (211-264 V), 60 Hz (59.3-60.5 Hz), 0.94 A, power factor 0.99, CEC efficiency 94.5% |
| Limits | Max 17 units per 20 A branch circuit; -40 to +85 C |
| Firmware | 2357 (original), 2406 and 2407 (2013). See [inverters.md](inverters.md) |

Figures are from the SunPower datasheets that ship on the box's own card.
