#!/usr/bin/env bash
# Start (or create and start) the TrueNAS test VM for nAI's adapter test (see README.md here).
# All VM files live in $VM_DIR, outside the repo. No secrets are used or stored by this script.
#
#   scripts/truenas-vm/start-vm.sh            # boot from the installed boot disk
#   scripts/truenas-vm/start-vm.sh --install  # boot the installer ISO (first run)
#
# Host ports (localhost only): HTTPS 8443 -> 443, HTTP 8080 -> 80, SSH 2222 -> 22.
# Serial console: unix socket $VM_DIR/serial.sock; QEMU monitor: $VM_DIR/monitor.sock; VNC 127.0.0.1:5901.
set -euo pipefail

VM_DIR="${VM_DIR:-$HOME/vms/truenas-test}"
ISO="${ISO:-$VM_DIR/iso/TrueNAS-SCALE-25.10.8.iso}"
OVMF_CODE="${OVMF_CODE:-/usr/share/edk2/x64/OVMF_CODE.4m.fd}"
OVMF_VARS_TEMPLATE="${OVMF_VARS_TEMPLATE:-/usr/share/edk2/x64/OVMF_VARS.4m.fd}"
RAM_MB="${RAM_MB:-8192}"
CPUS="${CPUS:-4}"

mkdir -p "$VM_DIR"
cd "$VM_DIR"
[ -f boot.qcow2 ] || qemu-img create -q -f qcow2 boot.qcow2 32G
[ -f data1.qcow2 ] || qemu-img create -q -f qcow2 data1.qcow2 20G
[ -f data2.qcow2 ] || qemu-img create -q -f qcow2 data2.qcow2 20G
[ -f ovmf_vars.fd ] || cp "$OVMF_VARS_TEMPLATE" ovmf_vars.fd

if [ -f qemu.pid ] && kill -0 "$(cat qemu.pid)" 2>/dev/null; then
    echo "VM already running (pid $(cat qemu.pid))"
    exit 0
fi

cdrom=()
if [ "${1:-}" = "--install" ]; then
    [ -f "$ISO" ] || { echo "ISO not found: $ISO (see README.md: download and verify it first)" >&2; exit 1; }
    cdrom=(-drive "file=$ISO,media=cdrom,readonly=on,if=none,id=cd0" -device "ide-cd,drive=cd0,bootindex=0")
fi

rm -f serial.sock monitor.sock
qemu-system-x86_64 \
    -name truenas-test -machine q35,accel=kvm -cpu host -smp "$CPUS" -m "$RAM_MB" \
    -drive "if=pflash,format=raw,readonly=on,file=$OVMF_CODE" \
    -drive "if=pflash,format=raw,file=$VM_DIR/ovmf_vars.fd" \
    -drive "file=boot.qcow2,if=none,id=boot,format=qcow2" \
    -device "virtio-blk-pci,drive=boot,serial=NAIBOOT01,bootindex=1" \
    -drive "file=data1.qcow2,if=none,id=d1,format=qcow2" -device "virtio-blk-pci,drive=d1,serial=NAIDATA01" \
    -drive "file=data2.qcow2,if=none,id=d2,format=qcow2" -device "virtio-blk-pci,drive=d2,serial=NAIDATA02" \
    "${cdrom[@]}" \
    -netdev "user,id=n0,hostfwd=tcp:127.0.0.1:8443-:443,hostfwd=tcp:127.0.0.1:8080-:80,hostfwd=tcp:127.0.0.1:2222-:22" \
    -device virtio-net-pci,netdev=n0 \
    -serial "unix:$VM_DIR/serial.sock,server,nowait" \
    -monitor "unix:$VM_DIR/monitor.sock,server,nowait" \
    -vnc 127.0.0.1:1 \
    -daemonize -pidfile "$VM_DIR/qemu.pid"

echo "VM started (pid $(cat qemu.pid)); serial: $VM_DIR/serial.sock, VNC: 127.0.0.1:5901"
