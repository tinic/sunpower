#!/usr/bin/env python3
"""Build a flashable SD card image from the repo tree and manifest.

Usage: make-card.py [--repo DIR] [--out sunpower-card.img]

Creates an MBR disk with one Linux partition holding an ext3 filesystem laid
out like the original card (it is mounted as /var on the box, kernel 2.6.31).
Owners, modes, mtimes, hard links and FIFOs come from manifest.tsv, and a fresh
64 MB swap file is written. Needs e2fsprogs (mke2fs, debugfs, e2fsck); no root.
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import uuid

SECTOR = 512
BLOCK = 4096
FS_BLOCKS = 487936          # same size as the original partition
PART_START = 2048           # sectors; 1 MiB alignment like the original
INODES = 122160
SWAP_PATH = '/swaps/swapfile'
SWAP_SIZE = 64 << 20         # the box uses ~40 MB of its 256 MB RAM
FEATURES = ('none,has_journal,ext_attr,resize_inode,dir_index,filetype,'
            'sparse_super,large_file')
TYPE_BITS = {'d': 0o040000, 'f': 0o100000, 'h': 0o100000, 'l': 0o120000,
             'c': 0o020000, 'b': 0o060000, 'p': 0o010000, 's': 0o140000}


def run(*cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def quote(path):
    return '"' + path.replace('\\', '\\\\').replace('"', '\\"') + '"'


def debugfs_write(image, commands):
    with tempfile.NamedTemporaryFile('w', suffix='.cmd', delete=False) as f:
        f.write('\n'.join(commands) + '\n')
        cmdfile = f.name
    try:
        out = run('debugfs', '-w', '-f', cmdfile, image,
                  env=dict(os.environ, DEBUGFS_PAGER='__none__'))
    finally:
        os.unlink(cmdfile)
    # debugfs reports per-command failures on stderr but still exits 0.
    errors = [l for l in out.stderr.splitlines()
              if l and not l.startswith('debugfs ')]
    if errors:
        sys.exit('debugfs errors:\n' + '\n'.join(errors[:20]))


def read_manifest(path):
    rows = []
    with open(path, errors='surrogateescape') as f:
        for line in f:
            if line.startswith('#'):
                continue
            p, kind, mode, uid, gid, mtime, extra = line.rstrip('\n').split('\t')
            rows.append(dict(path=p, kind=kind, mode=int(mode, 8), uid=int(uid),
                             gid=int(gid), mtime=int(mtime), extra=extra))
    return rows


def swap_header():
    """Linux swap v1 header for a SWAP_SIZE file (what mkswap writes)."""
    page = bytearray(BLOCK)
    struct.pack_into('<III', page, 1024, 1, SWAP_SIZE // BLOCK - 1, 0)
    page[1036:1052] = uuid.uuid4().bytes
    page[BLOCK - 10:] = b'SWAPSPACE2'
    return bytes(page)


def stage(repo, rows, staging):
    """Copy the tree and add what git cannot hold: hard links, FIFOs, swap."""
    shutil.copytree(os.path.join(repo, 'var'), staging, symlinks=True)
    # Git drops empty directories; the manifest has them all.
    for r in rows:
        if r['kind'] == 'd':
            os.makedirs(os.path.join(staging, r['path'].lstrip('/')), exist_ok=True)
    for r in rows:
        local = os.path.join(staging, r['path'].lstrip('/'))
        if r['kind'] == 'h':
            os.link(os.path.join(staging, r['extra'].lstrip('/')), local)
        elif r['kind'] == 'p':
            os.mkfifo(local)
        elif r['kind'] in 'cbs':
            sys.exit(f"{r['path']}: device/socket entries are not supported yet")
    # Real data in every block: mke2fs skips all-zero blocks, and swapon
    # refuses files with holes. Pages after the header are never read before
    # being written, so their content does not matter.
    with open(os.path.join(staging, SWAP_PATH.lstrip('/')), 'wb') as f:
        f.write(swap_header())
        filler = b'\xff' * BLOCK
        for _ in range(SWAP_SIZE // BLOCK - 1):
            f.write(filler)


def fix_metadata(image, rows):
    cmds = []
    for r in rows:
        if r['kind'] == 'h':
            continue  # shares the inode of the first path
        p = quote(r['path'])
        stamp = time.strftime('%Y%m%d%H%M%S', time.gmtime(r['mtime']))
        cmds += [f"sif {p} mode 0{TYPE_BITS[r['kind']] | r['mode']:o}",
                 f"sif {p} uid {r['uid']}", f"sif {p} gid {r['gid']}",
                 f"sif {p} mtime {stamp}", f"sif {p} atime {stamp}",
                 f"sif {p} ctime {stamp}"]
    cmds += [f'sif {SWAP_PATH} mode 0100600', f'sif {SWAP_PATH} uid 0',
             f'sif {SWAP_PATH} gid 0']
    debugfs_write(image, cmds)


def write_mbr(disk, part_sectors):
    mbr = bytearray(SECTOR)
    struct.pack_into('<I', mbr, 440, uuid.uuid4().int & 0xffffffff)
    # Bootable Linux partition; CHS fields set to the LBA-only marker.
    entry = struct.pack('<B3sB3sII', 0x80, b'\xfe\xff\xff', 0x83,
                        b'\xfe\xff\xff', PART_START, part_sectors)
    mbr[446:462] = entry
    mbr[510:512] = b'\x55\xaa'
    disk.write(mbr)
    disk.write(bytes(PART_START * SECTOR - SECTOR))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--repo', default=os.path.dirname(here))
    ap.add_argument('--out', default='sunpower-card.img')
    args = ap.parse_args()

    if not os.path.isfile(os.path.join(args.repo, 'manifest.tsv')):
        sys.exit(f'{args.repo}: no manifest.tsv; pass the tree made by extract.py with --repo')
    rows = read_manifest(os.path.join(args.repo, 'manifest.tsv'))
    with tempfile.TemporaryDirectory() as work:
        staging = os.path.join(work, 'root')
        part = os.path.join(work, 'partition.ext')
        print('staging tree...', file=sys.stderr)
        stage(args.repo, rows, staging)

        print('creating ext3 filesystem...', file=sys.stderr)
        run('mke2fs', '-F', '-q', '-t', 'ext3', '-b', str(BLOCK), '-I', '256',
            '-N', str(INODES), '-m', '1', '-J', 'size=32', '-O', FEATURES,
            '-E', 'root_owner=0:0', '-d', staging, part, str(FS_BLOCKS))
        fix_metadata(part, rows)
        # The box checks the filesystem at boot; start with a clean, fresh one.
        run('tune2fs', '-c', '38', '-i', '1d', '-C', '0', '-T', 'now', part)
        fsck = subprocess.run(['e2fsck', '-fn', part], capture_output=True, text=True)
        if fsck.returncode:
            sys.exit('e2fsck found problems:\n' + fsck.stdout + fsck.stderr)

        print(f'writing {args.out}...', file=sys.stderr)
        with open(args.out, 'wb') as disk, open(part, 'rb') as src:
            write_mbr(disk, FS_BLOCKS * BLOCK // SECTOR)
            shutil.copyfileobj(src, disk, 1 << 22)
    size = os.path.getsize(args.out)
    print(f'{args.out}: {size} bytes ({size / 1e9:.2f} GB); '
          'any 2 GB or larger card works', file=sys.stderr)


if __name__ == '__main__':
    main()
