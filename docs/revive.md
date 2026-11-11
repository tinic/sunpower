# Step by step: revive the box

Time: about an hour. You need a computer with an SD card reader (macOS or
Linux), Python 3 and e2fsprogs, and a new SD card of 2 GB or more. Use a
high-endurance or industrial card; the original failed from wear.

The commands below are for macOS. On Linux use `lsblk` instead of
`diskutil list`, `/dev/sdX` instead of `/dev/rdiskN`, and add
`status=progress` to `dd` if you like.

## 1. Get the card out

Disconnect the box's power, open the enclosure and take out the SD card.
Note how it sits. (We have no photos yet; contributions welcome.)

## 2. Image the old card first

Do this before anything else, and keep the image. It is your only copy of
your box's configuration (inverter list, grid settings, layout).

```sh
diskutil list                       # find the card, e.g. /dev/disk4
diskutil unmountDisk /dev/disk4
sudo dd if=/dev/rdisk4 of=old-card.img bs=4m
```

Double-check the disk number: `dd` overwrites without asking, and a wrong
`of=` destroys that disk. macOS will say it cannot read the card (ext3);
click **Ignore**, not Initialize.

If `dd` stops with read errors, the card is dying. Use `ddrescue`
(`brew install ddrescue`) to get as much as possible:
`sudo ddrescue -d /dev/rdisk4 old-card.img old-card.map`.

## 3. Check the image

```sh
brew install e2fsprogs
export PATH=$(brew --prefix e2fsprogs)/sbin:$PATH
dd if=old-card.img of=part.ext bs=1m skip=1     # partition starts at 1 MiB
e2fsck -fn part.ext                             # read-only check
```

If `e2fsck` reports errors, repair a **copy**: `cp part.ext fixed.ext;
e2fsck -fy fixed.ext`, and use `fixed.ext` in the next step. `extract.py`
takes either a whole card image or a bare partition.

## 4. Extract, apply the overlay, build

```sh
git clone https://github.com/tinic/sunpower.git && cd sunpower
tools/extract.py ../old-card.img ../mycard --exclude tools/exclude.txt
```

`extract.py` writes `mycard/var/` (the files) and `mycard/manifest.tsv`
(owner, group, mode, time, links and FIFOs for every entry, which the card
needs and a normal copy loses). The exclude list drops logs, archives and
other runtime state; live log files are kept empty so their owners survive.

Make an SSH key for the box. It runs OpenSSH 5.1, so it must be RSA:

```sh
ssh-keygen -t rsa -b 4096 -f ~/.ssh/sunpower_rsa
```

Optional: configure the Home Assistant bridge
([home-assistant.md](home-assistant.md)):

```sh
cp overlay/home/sunbridge/sunbridge.conf.example ../mqtt.conf
# edit host, port, user, password
```

Apply our changes and build the card image:

```sh
tools/apply-overlay.py ../mycard --ssh-key ~/.ssh/sunpower_rsa.pub --mqtt-conf ../mqtt.conf
tools/make-card.py --repo ../mycard --out ../new-card.img
```

`apply-overlay.py` disables the vendor cloud software
([vendor-cloud.md](vendor-cloud.md)), installs boot hooks, SSH access and
the bridge, and removes about 300 MB of unused install bundles and caches.
Use `--no-trim` to keep everything. `make-card.py` builds the ext3
filesystem the 2013 kernel needs and checks it with `e2fsck`.

## 5. Write the new card

```sh
diskutil list                        # find the NEW card
diskutil unmountDisk /dev/diskN
sudo dd if=../new-card.img of=/dev/rdiskN bs=4m
sync
# verify: read it back and compare checksums
sudo dd if=/dev/rdiskN bs=4m count=477 | head -c $(stat -f%z ../new-card.img) | shasum -a 256
shasum -a 256 ../new-card.img
diskutil eject /dev/diskN
```

Some USB card readers disconnect after a large write. If the read-back
finds no disk, unplug and replug the reader.

## 6. Boot and check

Put the card in and power the box on. The first boot runs a full
filesystem check and takes a few minutes longer.

Find the box on your network (DHCP; look in your router, or scan for the
SSH port: `nc -z -G 1 <ip> 45871`). Then:

```sh
ssh -p 45871 -i ~/.ssh/sunpower_rsa \
    -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa \
    root@<box-ip>
```

(See [ssh.md](ssh.md) for a config entry.) On the box:

```sh
mount | grep ' /var '                    # /dev/mmcblk0p1 on /var type ext3
ps aux | grep -E 'pmSysCtl|sysmon|data_logger' | grep -v grep   # nothing
ps aux | grep -E 'sbtmenu|apache2' | grep -v grep               # running
export LD_LIBRARY_PATH=/home/data_logger/lib
/home/data_logger/bin/sbti -v            # Power Manager hardware and software version
/home/data_logger/bin/sbti -l            # the inverters it knows
```

In daylight, `sbti -m <serial>` shows live readings from one inverter.
At night the inverters are off and `sbti -m` fails with
"InvDir Error Code (1) Generic failure of transaction".

## 7. Back up the internal flash

While you are logged in, back up the internal flash too. It is the other
half of the system. See [internal-flash.md](internal-flash.md). Do this
before you change anything on the flash.

## Keeping it alive

- The vendor software wrote logs to the card all the time. The overlay
  sends those to `/dev/null` or RAM; what still writes is listed in
  [software.md](software.md#what-writes-to-the-card). Keep your image and
  `mycard` directory so you can make a new card in minutes.
- Keep the box on your LAN only. It runs 2009-era software that can not be
  updated, and it does not need the internet any more.
