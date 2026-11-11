# SSH access

## How the vendor set it up

From `/etc/ssh/sshd_config` on the internal flash:

- Port **45871** (not 22)
- `AllowUsers root` and `PermitRootLogin yes`: only root can log in
- `PasswordAuthentication no`: keys only
- `AuthorizedKeysFile /etc/ssh/authorized_keys`: one key file for root,
  **on the internal flash** (`/etc/config/ssh` is a symlink to `/etc/ssh`)
- OpenSSH **5.1p1** (Ubuntu 9.04): RSA keys only, no ed25519 or ECDSA

So keys in `/home/sbtech/.ssh/authorized_keys` (on the card) do not work,
and you can not log in until your key is in `/etc/ssh/authorized_keys`.
The file holds the vendor's support keys.

`/etc/rc.local` also manages that file at boot: after more than 5 boots it
rewrites it without lines that end in `remove`, keeps copies in
`authorized_keys.new`, `.bak` and `.x`, and 30 minutes after boot moves
`.x` over the live file.

## How to get in without opening the flash

Everything in `/home/sunpwrscripts/` (on the card) runs as root at the end
of every boot. Our hook `20-ssh-key.sh` appends your key to
`authorized_keys` and to the `.new` and `.x` copies, so the vendor's
30-minute restore keeps it. `tools/apply-overlay.py --ssh-key` installs the
hook with your key; see [revive.md](revive.md).

The alternative is the serial console (`ttymxc0`, 115200 8N1), where a
getty runs, but you need a login password for it.

## Client configuration

Modern OpenSSH has the old algorithms turned off. Add this to
`~/.ssh/config`:

```
Host sunpower
    HostName <box-ip>
    Port 45871
    User root
    IdentityFile ~/.ssh/sunpower_rsa
    IdentitiesOnly yes
    HostKeyAlgorithms +ssh-rsa
    PubkeyAcceptedAlgorithms +ssh-rsa
    KexAlgorithms +diffie-hellman-group14-sha1,diffie-hellman-group1-sha1
```

Then `ssh sunpower`. `ssh-dss` is no longer known to current clients; do
not add it.

## Tips for working on the box

- `scp` and `sftp` from new clients use SFTP by default; for copying, it
  is simpler to pipe `tar` over `ssh`:
  `tar -cf - files | ssh sunpower 'tar -xf - -C /tmp'`
- There is no `timeout` command; `sed` has no `-E` (use `-r`);
  `readlink` takes one file at a time.
- `/tmp` is RAM. Work there if you do not want to write to the card.
- The vendor tools need `LD_LIBRARY_PATH=/home/data_logger/lib`.
