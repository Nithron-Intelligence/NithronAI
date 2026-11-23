#!/usr/bin/env bash
# Make a small private CA and a TrueNAS web UI certificate signed by it (TrueNAS 25.10 no longer creates
# CAs itself). The CA certificate is what nAI gets as NAI_TRUENAS_CA_FILE; configure.py --cert/--key imports
# the server certificate into TrueNAS and makes it the web UI certificate.
#
#   scripts/truenas-vm/make-cert.sh <out-dir> [SAN ...]     # default SANs: DNS:localhost IP:127.0.0.1
#
# Keys are written with mode 600 to <out-dir> (keep it outside the repo).
set -euo pipefail

out="${1:?usage: make-cert.sh <out-dir> [SAN ...]}"
shift
sans=("$@")
[ ${#sans[@]} -gt 0 ] || sans=("DNS:localhost" "IP:127.0.0.1")
san_list=$(IFS=,; echo "${sans[*]}")

mkdir -p "$out"
umask 077
cd "$out"
if [ ! -f ca.key ]; then
    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 3650 \
        -subj "/CN=nAI test CA" -keyout ca.key -out ca.pem \
        -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null
fi
openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -subj "/CN=${sans[0]#*:}" \
    -keyout server.key -out server.csr 2>/dev/null
openssl x509 -req -in server.csr -CA ca.pem -CAkey ca.key -CAcreateserial -days 825 -out server.pem \
    -extfile <(printf 'subjectAltName=%s\nbasicConstraints=CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\n' "$san_list") \
    2>/dev/null
rm -f server.csr
chmod 644 ca.pem server.pem
echo "CA: $out/ca.pem  server cert: $out/server.pem (SAN $san_list)  keys: mode 600"
