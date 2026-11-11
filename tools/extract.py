#!/usr/bin/env python3
"""Extract the SunPower/SolarBridge SD card (/var partition) into a directory
tree plus a manifest that records what git cannot: owner, group, mode, mtime,
symlink targets, device numbers and hard links.

Usage: extract.py <card.img | partition.ext> <outdir> [--exclude FILE]

Needs e2fsprogs (debugfs). Works without root and never mounts or writes the
source. The tree is written to <outdir>/var and the manifest to
<outdir>/manifest.tsv.
"""
import argparse
import fnmatch
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile

SECTOR = 512
TYPE_BITS = {0o040000: 'd', 0o100000: 'f', 0o120000: 'l',
             0o020000: 'c', 0o060000: 'b', 0o010000: 'p', 0o140000: 's'}


def debugfs(image, commands):
    """Run a batch of debugfs commands; return {command: output}."""
    with tempfile.NamedTemporaryFile('w', suffix='.cmd', delete=False) as f:
        f.write('\n'.join(commands) + '\n')
        cmdfile = f.name
    try:
        env = dict(os.environ, DEBUGFS_PAGER='__none__', PAGER='__none__')
        out = subprocess.run(['debugfs', '-f', cmdfile, image], env=env,
                             capture_output=True, text=True,
                             errors='surrogateescape', check=True).stdout
    finally:
        os.unlink(cmdfile)
    results, current = {}, None
    for line in out.splitlines():
        if line.startswith('debugfs: '):
            current = line[len('debugfs: '):]
            results[current] = []
        elif current is not None:
            results[current].append(line)
    return results


def quote(path):
    return '"' + path.replace('\\', '\\\\').replace('"', '\\"') + '"'


def partition_image(src, workdir):
    """Return a path to a bare ext partition, carving it out of an MBR image."""
    with open(src, 'rb') as f:
        mbr = f.read(SECTOR)
        f.seek(1024 + 56)
        bare = f.read(2) == b'\x53\xef'
    if bare:
        return src
    if mbr[510:512] != b'\x55\xaa':
        sys.exit(f'{src}: neither an ext filesystem nor an MBR disk image')
    for i in range(4):
        entry = mbr[446 + 16 * i:462 + 16 * i]
        ptype, start, size = entry[4], *struct.unpack_from('<II', entry, 8)
        if ptype == 0x83:
            break
    else:
        sys.exit(f'{src}: no Linux partition in MBR')
    out = os.path.join(workdir, 'partition.ext')
    with open(src, 'rb') as fi, open(out, 'wb') as fo:
        fi.seek(start * SECTOR)
        remaining = size * SECTOR
        while remaining:
            chunk = fi.read(min(remaining, 1 << 22))
            if not chunk:
                break
            fo.write(chunk)
            remaining -= len(chunk)
    return out


def walk(image):
    """Breadth-first listing; returns [(path, inode, mode, uid, gid, size)]."""
    entries, level = [('/', 2, 0o040755, 0, 0, 0)], ['/']
    while level:
        cmds = [f'ls -p {quote(d)}' for d in level]
        out = debugfs(image, cmds)
        nxt = []
        for d, cmd in zip(level, cmds):
            for line in out.get(cmd, []):
                parts = line.split('/')
                if len(parts) < 7 or not parts[1]:
                    continue
                ino, mode, uid, gid = (int(parts[1]), int(parts[2], 8),
                                       int(parts[3]), int(parts[4]))
                name = '/'.join(parts[5:-2])
                size = int(parts[-2] or 0)
                if name in ('.', '..') or ino == 0:
                    continue
                path = d.rstrip('/') + '/' + name
                entries.append((path, ino, mode, uid, gid, size))
                if mode & 0o170000 == 0o040000:
                    nxt.append(path)
        level = nxt
    return entries


def inode_details(image, inodes):
    """mtime, link target and device numbers per inode."""
    info = {}
    inodes = sorted(set(inodes))
    for i in range(0, len(inodes), 2000):
        batch = inodes[i:i + 2000]
        out = debugfs(image, [f'stat <{n}>' for n in batch])
        for n in batch:
            text = '\n'.join(out.get(f'stat <{n}>', []))
            m = re.search(r'^\s*mtime: 0x([0-9a-f]+)', text, re.M)
            t = re.search(r'Fast link dest: "(.*)"', text)
            dev = re.search(r'Device major/minor number: (\d+):(\d+)', text)
            info[n] = {'mtime': int(m.group(1), 16) if m else 0,
                       'target': t.group(1) if t else None,
                       'dev': f'{dev.group(1)}:{dev.group(2)}' if dev else None}
    return info


def slow_link_target(image, path, workdir):
    tmp = os.path.join(workdir, 'link')
    debugfs(image, [f'dump {quote(path)} {quote(tmp)}'])
    with open(tmp, 'rb') as f:
        target = f.read().decode('utf-8', 'surrogateescape')
    os.unlink(tmp)
    return target


def load_excludes(path):
    """Return (drop, truncate) pattern lists."""
    drop, truncate = [], []
    if path:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('truncate '):
                    truncate.append(line.split(None, 1)[1])
                else:
                    drop.append(line)
    return drop, truncate


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, p) for p in patterns)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('image')
    ap.add_argument('outdir')
    ap.add_argument('--exclude', help='file of glob patterns (paths start with /)')
    args = ap.parse_args()

    drop, truncate = load_excludes(args.exclude)
    tree = os.path.join(args.outdir, 'var')
    if os.path.exists(tree):
        sys.exit(f'{tree} already exists; remove it first')
    os.makedirs(tree)

    with tempfile.TemporaryDirectory() as work:
        image = partition_image(args.image, work)
        entries = walk(image)
        info = inode_details(image, [e[1] for e in entries])

        seen, rows, dumps, skipped = {}, [], [], 0
        for path, ino, mode, uid, gid, size in entries:
            kind = TYPE_BITS.get(mode & 0o170000, '?')
            # Directories are always kept so the layout stays intact.
            if kind != 'd' and matches(path, drop):
                skipped += 1
                continue
            extra = ''
            if kind == 'l':
                extra = info[ino]['target'] or slow_link_target(image, path, work)
            elif kind in 'cb':
                extra = info[ino]['dev']
            elif kind == 'f' and ino in seen:
                kind, extra = 'h', seen[ino]
            elif kind == 'f':
                seen[ino] = path
            rows.append((path, kind, f'{mode & 0o7777:04o}', uid, gid,
                         info[ino]['mtime'], extra))

            local = os.path.join(tree, path.lstrip('/'))
            if kind == 'd':
                os.makedirs(local, exist_ok=True)
            elif kind == 'f' and matches(path, truncate):
                open(local, 'wb').close()
            elif kind == 'f':
                dumps.append(f'dump {quote(path)} {quote(local)}')
            elif kind == 'l':
                os.symlink(extra, local)

        # Directories exist by now, so file contents can go in a few batches.
        for i in range(0, len(dumps), 500):
            debugfs(image, dumps[i:i + 500])

    with open(os.path.join(args.outdir, 'manifest.tsv'), 'w',
              errors='surrogateescape') as f:
        f.write('# path\ttype\tmode\tuid\tgid\tmtime\textra\n')
        f.write('# type: d=dir f=file l=symlink(extra=target) h=hardlink(extra=first path)\n')
        f.write('#       c/b=char/block device(extra=major:minor) p=fifo s=socket\n')
        for r in rows:
            f.write('\t'.join(str(x) for x in r) + '\n')
    print(f'{len(rows)} entries written, {skipped} excluded', file=sys.stderr)


if __name__ == '__main__':
    main()
