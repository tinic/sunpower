# Internal flash

256 MB Hynix NAND, 128 KiB erase blocks, three partitions:

| Partition | Size | Contents |
|---|---|---|
| `mtd0` "nand.bootloader" | 3 MB | Bootloader ("Board: i.MX25 SBT SIM") |
| `mtd1` "nand.kernel" | 5 MB | U-Boot image `Linux-2.6.31.84-SBT` |
| `mtd2` "nand.userfs" | 248 MB | Root filesystem, JFFS2 |

## Back it up

From the box, streaming to your computer, without writing anything to the
box. `nanddump` (mtd-utils 2009) is installed. `-o` leaves out the OOB
data, which JFFS2 does not use.

```sh
for n in 0 1 2; do
    ssh sunpower "nanddump -q -o -f /dev/stdout /dev/mtd$n" > mtd$n.bin
    ssh sunpower "nanddump -q -o -f /dev/stdout /dev/mtd$n | md5sum"   # compare with:
    md5 -q mtd$n.bin
done
```

The root filesystem is mounted read-write, so a dump of `mtd2` taken while
the system writes to it will not match a second read. Remount it
read-only for the dump and switch back afterwards:

```sh
ssh sunpower 'sync; mount -o remount,ro /'
# ... dump mtd2 ...
ssh sunpower 'cd / && tar --numeric-owner --one-file-system -cpf - .' > rootfs.tar
ssh sunpower 'mount -o remount,rw /'
```

The remount is refused if a file is open for writing; nothing changes
then. The tar takes about five minutes (slow CPU, JFFS2 decompression).

To restore a partition (only from a known-good boot; a bad bootloader or
kernel image leaves the box unbootable without serial or JTAG access):

```sh
flash_eraseall /dev/mtdN
nandwrite -p /dev/mtdN mtdN.bin
```

## It is probably almost full

Ours was 95% full, with only 6.3 MB of erased blocks. JFFS2 needs some
free blocks for garbage collection; when it runs short, the box stalls
(the kernel thread `jffs2_gcd_mtd2` uses all CPU) and writes can fail.

What we removed (all safe on our unit, all restorable from the backup):

| Item | Space | Notes |
|---|---|---|
| Java: `dpkg --purge ca-certificates-java icedtea-6-jre-cacao openjdk-6-jre-headless openjdk-6-jre-lib tzdata-java java-common` | ~38 MB on flash (78 MB unpacked) | Nothing depends on it or starts it. Only vendor cloud tools and the old SBMS app use it. Do a dry run first: `dpkg --no-act --purge ...` |
| `/lib/modules/2.6.31.59-SBT`, `/lib/modules/2.6.31.71-SBT` | 1.7 MB | Modules for older kernels; check `uname -r` first |
| `/usr/bin/qemu-arm-static` | 1.3 MB | Leftover from building the image on a PC |
| `*.dpkg-old`, `*.old`, `crontab.bak`, `trusted.gpg~` in `/etc` | small | |

Usage went from 235 MB to 182 MB.

**Do not remove `/usr/local/sbin/plctools/*_old`.** They look like
leftovers and belong to no package, but `sbti -m` needs `plcioctl_old`;
without it, it fails with `File does not exist: /usr/local/sbin/plctools/plcioctl_old`.

Expect the box to be sluggish for a few minutes after deleting while
JFFS2 reclaims the space.

## What on the flash is vendor-specific

About 93% of the files are unmodified Ubuntu packages. The SolarBridge
parts are the bootloader, the kernel and its modules, the packages
`powermanager` (V3 tools, init scripts, `/sbin/sbtmenu`), `libsbidirect`
(the inverter API library), `plctools`, a patched `debsums`, and
configuration in `/etc`: `rc.local`, `crontab`, `sshd_config`,
`fstab`, Apache and PHP configs, `init.d/mountsdcardfs.sh`,
`sbt-release` ("Power Manager Software (56.2c)").

So a working box needs both: the card and the flash.
