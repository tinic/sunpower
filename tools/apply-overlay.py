#!/usr/bin/env python3
"""Apply our changes to a card tree made by extract.py.

Usage: apply-overlay.py <tree> [--ssh-key KEY.pub] [--mqtt-conf FILE] [--no-trim]

<tree> holds var/ and manifest.tsv. The script:
  - disables the vendor cloud software (stubs; originals are moved to
    home/data_logger/vendor-disabled/ so they can be restored)
  - points the Power Manager's cloud servers in sb/pm.conf to 127.0.0.1
  - installs our boot hooks (home/sunpwrscripts/) and the MQTT bridge
    (home/sunbridge/)
  - installs an SSH key for root logins if --ssh-key is given
  - installs the bridge config if --mqtt-conf is given
  - removes files nothing on the box uses (unless --no-trim)
Running it twice is safe. Build the card afterwards with make-card.py.
"""
import argparse
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OVERLAY = os.path.join(os.path.dirname(HERE), 'overlay')
DL = '/home/data_logger'
DISABLED = DL + '/vendor-disabled'
# Vendor files replaced by stubs, kept in vendor-disabled/.
STUBBED = [DL + '/bin/data_logger', DL + '/bin/connect',
           DL + '/util/sysmon.sh', DL + '/util/sync_docs.sh']
SSH_HOOK = '/home/sunpwrscripts/20-ssh-key.sh'
# Removed by --trim: install bundles, caches and apps nothing uses.
TRIM_TREES = ['/sb/upgrades/', '/sb/packages/', '/home/updatetmp/']  # emptied
TRIM_DIRS = ['/home/sbtech/sbms', '/home/sbtech/56tov3.save']          # removed
TRIM_FILES_IN = ['/cache/apt/', '/lib/apt/lists/']
TRIM_FILES = ['/home/sbtech/56tov3.sql', '/home/sbtech/56tov3-export.log',
              DL + '/devices_mi_update.bak', DL + '/bin/sbti.orig']


class Tree(object):
    def __init__(self, root):
        self.root = root
        self.var = os.path.join(root, 'var')
        self.manifest = os.path.join(root, 'manifest.tsv')
        self.head, self.rows = [], {}
        with open(self.manifest, errors='surrogateescape') as f:
            for line in f:
                if line.startswith('#'):
                    self.head.append(line)
                else:
                    r = line.rstrip('\n').split('\t')
                    self.rows[r[0]] = r

    def local(self, path):
        return os.path.join(self.var, path.lstrip('/'))

    def has(self, path):
        return path in self.rows

    def add(self, path, kind, mode, uid=0, gid=0, extra=''):
        self.rows[path] = [path, kind, '%04o' % mode, str(uid), str(gid),
                           str(int(time.time())), extra]

    def touch(self, path):
        self.rows[path][5] = str(int(time.time()))

    def remove(self, path):
        local = self.local(path)
        if os.path.islink(local) or os.path.isfile(local):
            os.unlink(local)
        elif os.path.isdir(local):
            shutil.rmtree(local)
        for p in [p for p in self.rows if p == path or p.startswith(path + '/')]:
            del self.rows[p]

    def ensure_dir(self, path, like=None):
        os.makedirs(self.local(path), exist_ok=True)
        if not self.has(path):
            r = self.rows.get(like)
            self.add(path, 'd', int(r[2], 8) if r else 0o755,
                     r[3] if r else 0, r[4] if r else 0)

    def save(self):
        with open(self.manifest, 'w', errors='surrogateescape') as f:
            f.writelines(self.head)
            for r in self.rows.values():
                f.write('\t'.join(r) + '\n')


def disable_vendor(tree):
    tree.ensure_dir(DISABLED, like=DL)
    for path in STUBBED:
        if not tree.has(path):
            continue
        saved = DISABLED + '/' + os.path.basename(path)
        if not tree.has(saved):
            shutil.copy2(tree.local(path), tree.local(saved))
            tree.rows[saved] = [saved] + tree.rows[path][1:]
        stub = os.path.join(OVERLAY, path.lstrip('/'))
        shutil.copyfile(stub, tree.local(path))
        tree.touch(path)  # owner and mode stay the vendor's
    conf = tree.local('/sb/pm.conf')
    if os.path.exists(conf):
        text = open(conf).read()
        new = re.sub(r'[A-Za-z0-9.-]*theenergybridge\.com', '127.0.0.1', text)
        if new != text:
            open(conf, 'w').write(new)
            tree.touch('/sb/pm.conf')


def install_overlay(tree, ssh_key, mqtt_conf):
    for d, _, files in os.walk(OVERLAY):
        rel = '/' + os.path.relpath(d, OVERLAY).replace(os.sep, '/')
        rel = '' if rel == '/.' else rel
        for name in sorted(files):
            path = rel + '/' + name
            if path in STUBBED or name.endswith('.example'):
                continue
            if path == SSH_HOOK and not ssh_key:
                continue
            tree.ensure_dir(rel)
            src = os.path.join(d, name)
            if path == SSH_HOOK:
                key = open(ssh_key).read().strip()
                if not key.startswith('ssh-rsa '):
                    sys.exit('--ssh-key: the box runs OpenSSH 5.1 and only takes '
                             'ssh-rsa keys (ssh-keygen -t rsa -b 4096)')
                text = re.sub(r"'@KEY@'.*", "'%s'" % key, open(src).read())
                open(tree.local(path), 'w').write(text)
            else:
                shutil.copyfile(src, tree.local(path))
            mode = 0o755 if name.endswith('.sh') else 0o644
            tree.add(path, 'f', mode)
    if mqtt_conf:
        shutil.copyfile(mqtt_conf, tree.local('/home/sunbridge/sunbridge.conf'))
        tree.add('/home/sunbridge/sunbridge.conf', 'f', 0o600)


def trim(tree):
    for d in TRIM_DIRS:
        if tree.has(d):
            tree.remove(d)
    for top in TRIM_TREES:
        for p in [p for p in tree.rows if p.startswith(top)]:
            if tree.has(p):
                tree.remove(p)
    for top in TRIM_FILES_IN:
        for p in [p for p, r in tree.rows.items() if p.startswith(top) and r[1] != 'd']:
            tree.remove(p)
    for p in TRIM_FILES + [p for p in tree.rows
                           if re.match(re.escape(DL) + r'/inverter_release_.*\.bfe$', p)]:
        if tree.has(p):
            tree.remove(p)
    # Old data logger config versions; keep what config/devices(.bak) point to.
    keep = set()
    for link in ('config.lua', 'config.bak', 'devices.lua', 'devices.bak'):
        r = tree.rows.get(DL + '/' + link)
        if r and r[1] == 'l':
            keep.add(r[6])
    for p, r in list(tree.rows.items()):
        name = p[len(DL) + 1:] if p.startswith(DL + '/') else ''
        if re.match(r'^[cd][0-9a-f]{7}\.lua$', name) and r[1] == 'f' and name not in keep:
            tree.remove(p)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('tree')
    ap.add_argument('--ssh-key', help='ssh-rsa public key for root logins')
    ap.add_argument('--mqtt-conf', help='bridge config (see sunbridge.conf.example)')
    ap.add_argument('--no-trim', action='store_true')
    args = ap.parse_args()
    tree = Tree(args.tree)
    if not tree.has(DL):
        sys.exit(f'{args.tree}: no {DL} in the manifest; is this a PV Supervisor card?')
    disable_vendor(tree)
    install_overlay(tree, args.ssh_key, args.mqtt_conf)
    if not args.no_trim:
        trim(tree)
    tree.save()
    print(f'applied overlay to {args.tree}: {len(tree.rows)} entries', file=sys.stderr)
    if not args.ssh_key:
        print('note: no --ssh-key given, so you will not be able to log in', file=sys.stderr)


if __name__ == '__main__':
    main()
