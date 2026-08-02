#!/usr/bin/env bash
#
# Create the self-signed code-signing certificate release.sh expects.
#
#   ./packaging/macos/make-dev-cert.sh
#
# Signing with a stable identity is what stops macOS from revoking the app's
# Accessibility grant on every rebuild — the permission is bound to the code
# signature, and an unsigned binary gets a new identity each time it is built.
#
# The certificate lands in a dedicated keychain rather than the login one, so
# no login password is needed and removing it later is a single command:
#
#   security delete-keychain ~/Library/Keychains/flow-st8-signing.keychain-db
#
# This is NOT a Developer ID: Gatekeeper still blocks the app on other Macs.
# See the README for what that means for distribution.

set -euo pipefail

IDENTITY="${SIGN_IDENTITY:-flow-st8-dev}"
KEYCHAIN="$HOME/Library/Keychains/flow-st8-signing.keychain-db"
KEYCHAIN_PASSWORD="flow-st8"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }

if security find-identity -p codesigning 2>/dev/null | grep -qF "\"$IDENTITY\""; then
    echo "Certificado '$IDENTITY' já existe. Nada a fazer."
    exit 0
fi

step "Gerando certificado autoassinado '$IDENTITY'"
# /usr/bin/openssl deliberately, not whatever is first on PATH: OpenSSL 3 from
# Homebrew writes PKCS12 with algorithms the macOS Security framework rejects
# ("MAC verification failed"), while the system one is compatible by default.
SYS_OPENSSL=/usr/bin/openssl
P12_PASS=flow-st8

"$SYS_OPENSSL" req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
    -keyout "$WORK/key.pem" -out "$WORK/cert.pem" \
    -subj "/CN=$IDENTITY/O=flow-st8/C=BR" \
    -addext "basicConstraints=critical,CA:false" \
    -addext "keyUsage=critical,digitalSignature" \
    -addext "extendedKeyUsage=critical,codeSigning" 2>/dev/null
"$SYS_OPENSSL" pkcs12 -export -out "$WORK/cert.p12" \
    -inkey "$WORK/key.pem" -in "$WORK/cert.pem" -passout "pass:$P12_PASS" 2>/dev/null

step "Instalando no chaveiro dedicado"
if [[ ! -f "$KEYCHAIN" ]]; then
    security create-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN"
fi
security unlock-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN"
# Never expire the unlock, or a long build fails halfway through.
security set-keychain-settings "$KEYCHAIN"

# -A lets codesign use the key without a per-use prompt; the key is protected
# by this keychain's own password, not the login one.
security import "$WORK/cert.p12" -k "$KEYCHAIN" -P "$P12_PASS" -A -T /usr/bin/codesign
security set-key-partition-list -S apple-tool:,apple:,codesign: \
    -s -k "$KEYCHAIN_PASSWORD" "$KEYCHAIN" >/dev/null

# Put the keychain on the search list so codesign -s "$IDENTITY" resolves it.
existing="$(security list-keychains -d user | sed -e 's/^[[:space:]]*"//' -e 's/"$//')"
if ! grep -qF "$KEYCHAIN" <<<"$existing"; then
    # shellcheck disable=SC2086
    security list-keychains -d user -s $existing "$KEYCHAIN"
fi

step "Conferindo"
# -v lists only trusted identities; a self-signed cert is reported as
# CSSMERR_TP_NOT_TRUSTED but codesign uses it fine, so check the full list.
security find-identity -p codesigning | grep -F "\"$IDENTITY\"" || {
    echo "ERRO: o certificado não apareceu como identidade de assinatura." >&2
    exit 1
}
echo "(CSSMERR_TP_NOT_TRUSTED é esperado: autoassinado não é confiável para o"
echo " Gatekeeper, mas serve para assinar e estabilizar as permissões.)"
echo
echo "Pronto. Agora: ./packaging/macos/release.sh"
