# TrueNAS test VM

Reproducible manual test of nAI's TrueNAS adapter against a real TrueNAS in a KVM/QEMU VM. Last run:
**TrueNAS Community Edition 25.10.8, 2026-11-23** (results in
[packaging/truenas/README.md](../../packaging/truenas/README.md#manual-test-truenas-vm)).

All VM files live outside the repo (`$VM_DIR`, default `~/vms/truenas-test/`). Secrets live in
`$VM_DIR/secrets.env` (mode 600) and are never printed or committed.

Needs: `qemu-system-x86_64`, `qemu-img`, OVMF (`/usr/share/edk2/x64/`), `/dev/kvm`, `openssl`, about 8 GB free
RAM, and a Python venv with `websockets` (the TrueNAS steps) and `pexpect`/`pyte` (only if you script the
installer over the serial console). `install_app.py` imports `configure.py`, so run it from this folder.

## Steps

```bash
VM=~/vms/truenas-test; mkdir -p $VM/iso && cd $VM/iso
# 1. ISO: take the current stable version and its SHA-256 from https://www.truenas.com/download-tn-scale/
V=25.10.8; B=https://download.sys.truenas.net/TrueNAS-SCALE-Goldeye/$V
curl -fLO $B/TrueNAS-SCALE-$V.iso.sha256 && curl -fLO $B/TrueNAS-SCALE-$V.iso
echo "$(cat TrueNAS-SCALE-$V.iso.sha256)  TrueNAS-SCALE-$V.iso" | sha256sum -c   # also compare with the page
cd -

# 2. Admin password (never printed)
umask 077; printf 'TRUENAS_ADMIN_USER=truenas_admin\nTRUENAS_ADMIN_PASSWORD=%s\n' \
    "$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')" > $VM/secrets.env

# 3. Install: boots the ISO with serial console, VNC on 127.0.0.1:5901 as a fallback
scripts/truenas-vm/start-vm.sh --install
```

Installer (serial console `$VM/serial.sock`, or VNC): GRUB entry **"Start TrueNAS SCALE Installation (115200
baud)"** (hotkey `j`), then 1 Install/Upgrade, select `vda` (32 GiB) with Space, Enter, Yes, 1 Administrative
user (truenas_admin), password twice (Down arrow between the fields), Enter. After "Installation
Succeeded": Enter, 4 Shutdown System. To script it, connect to the socket (one client at a time) and send
those keys; `pyte` renders the dialog screens readably.

```bash
# 4. Boot the installed system (the web UI/API answers on https://localhost:8443 after ~2-3 minutes)
scripts/truenas-vm/start-vm.sh

# 5. Own certificate (TrueNAS 25.10 can't create CAs; its default cert names only "localhost")
scripts/truenas-vm/make-cert.sh $VM/pki DNS:localhost IP:127.0.0.1

# 6. Pool, datasets, sample files, SMB + NFS shares, read-only user + API key, UI certificate
$VM/venv/bin/python -I scripts/truenas-vm/configure.py --secrets $VM/secrets.env \
    --ca-out $VM/truenas-ca.pem --cert $VM/pki/server.pem --key $VM/pki/server.key --ca $VM/pki/ca.pem

# 7. The adapter test, with only the read-only key (by host name and by IP)
for u in localhost 127.0.0.1; do
    apps/nai-core/.venv/bin/python scripts/truenas-vm/test_adapter.py --url wss://$u:8443/api/current \
        --secrets $VM/secrets.env --ca-file $VM/truenas-ca.pem
done

# 8. nAI as a TrueNAS custom app (2026-11-23): local image, no registry. The certificate must also name the
#    VM's own IP (10.0.2.15), which the app container uses: re-run step 5 with IP:10.0.2.15 and step 6.
docker build -f apps/nai-core/Dockerfile -t nai-core:lab-stage-0 .
ssh-keygen -q -t ed25519 -N "" -f $VM/ssh/id_ed25519
(cd scripts/truenas-vm && $VM/venv/bin/python install_app.py --secrets $VM/secrets.env --ca $VM/pki/ca.pem \
    --ssh-pubkey $VM/ssh/id_ed25519.pub --skip-app)     # SSH key + sudo docker + TCP forwarding, Apps pool, datasets, ACL, CA file
SSH="ssh -i $VM/ssh/id_ed25519 -p 2222 -o UserKnownHostsFile=$VM/ssh/known_hosts"
docker save nai-core:lab-stage-0 | $SSH truenas_admin@localhost sudo -n docker load
(cd scripts/truenas-vm && $VM/venv/bin/python install_app.py --secrets $VM/secrets.env --ca $VM/pki/ca.pem)
$SSH -M -S $VM/ssh/tunnel.sock -fN -L 18000:127.0.0.1:8000 truenas_admin@localhost
apps/nai-core/.venv/bin/python scripts/truenas-vm/test_app.py --secrets $VM/secrets.env
$SSH -S $VM/ssh/tunnel.sock -O exit truenas_admin@localhost

# 9. Shut down (keeps all files); start again with step 4
echo system_powerdown | python3 -c "import socket,sys; s=socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); s.sendall(sys.stdin.buffer.read())" $VM/monitor.sock
```

`configure.py` is idempotent. Without `--cert/--key/--ca` it exports TrueNAS's default certificate as the CA
file instead, which only works with `wss://localhost:...` (its only SAN).
