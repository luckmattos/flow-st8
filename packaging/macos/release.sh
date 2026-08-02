#!/usr/bin/env bash
#
# Build, sign and package flow-st8 as a macOS .app inside a .dmg.
#
#   ./packaging/macos/release.sh
#
# Free path (default): self-signed certificate, no hardened runtime, no
# notarization. The app runs fine locally and keeps its Accessibility grant
# across rebuilds. Downloaders have to clear quarantine by hand — see README.
#
#   SIGN_IDENTITY   name of the signing certificate  (default: flow-st8-dev)
#
# Paid path: set NOTARY_PROFILE to a notarytool keychain profile and
# SIGN_IDENTITY to the "Developer ID Application: ..." certificate. That turns
# on the hardened runtime, the entitlements, and the notarize + staple steps.
#
#   xcrun notarytool store-credentials flow-st8-notary \
#     --key AuthKey_XXXX.p8 --key-id XXXX --issuer <issuer-id>
#
#   SIGN_IDENTITY="Developer ID Application: Nome (TEAMID)" \
#   NOTARY_PROFILE=flow-st8-notary ./packaging/macos/release.sh

set -euo pipefail

SIGN_IDENTITY="${SIGN_IDENTITY:-flow-st8-dev}"
NOTARY_PROFILE="${NOTARY_PROFILE:-}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

VERSION="$(tr -d '[:space:]' < VERSION)"
BUILD_DIR="$ROOT/build/macos"
APP="$ROOT/dist/flow-st8.app"
DMG="$ROOT/dist/flow-st8-${VERSION}-arm64.dmg"
ICNS="$BUILD_DIR/flow-st8.icns"
ENTITLEMENTS="$ROOT/packaging/macos/entitlements.plist"

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31mERRO: %s\033[0m\n' "$1" >&2; exit 1; }

[[ "$(uname -s)" == "Darwin" ]] || fail "este script só roda no macOS."
[[ "$(uname -m)" == "arm64" ]] || fail "o spec tem target_arch=arm64; rode num Mac Apple Silicon."
command -v pyinstaller >/dev/null || fail "pyinstaller não encontrado (pip install pyinstaller)."

# -v hides self-signed certs (CSSMERR_TP_NOT_TRUSTED) that codesign accepts.
if ! security find-identity -p codesigning | grep -qF "\"$SIGN_IDENTITY\""; then
    fail "certificado '$SIGN_IDENTITY' não encontrado no chaveiro.
     Crie um com: ./packaging/macos/make-dev-cert.sh"
fi

# ---------------------------------------------------------------- icon
step "Gerando o .icns a partir de assets/icon.png"
ICONSET="$BUILD_DIR/flow-st8.iconset"
rm -rf "$ICONSET"
mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
    sips -z "$size" "$size" assets/icon.png \
        --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
    sips -z "$((size * 2))" "$((size * 2))" assets/icon.png \
        --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$ICNS"

# ---------------------------------------------------------------- build
step "Compilando o bundle (PyInstaller)"
rm -rf "$APP" "$ROOT/dist/flow-st8" "$DMG"
pyinstaller --noconfirm --distpath "$ROOT/dist" --workpath "$BUILD_DIR/work" \
    packaging/macos/flow-st8-mac.spec
[[ -d "$APP" ]] || fail "PyInstaller não produziu $APP."

# ---------------------------------------------------------------- sign
if [[ -n "$NOTARY_PROFILE" ]]; then
    step "Assinando com hardened runtime (caminho notarizado)"
    SIGN_FLAGS=(--force --timestamp --options runtime --entitlements "$ENTITLEMENTS")
    INNER_FLAGS=(--force --timestamp --options runtime)
else
    step "Assinando com certificado local (sem hardened runtime)"
    SIGN_FLAGS=(--force --timestamp=none)
    INNER_FLAGS=(--force --timestamp=none)
fi

# Inside-out: every nested Mach-O first, the bundle last. --deep is deprecated
# and signs nested code with the wrong entitlements.
while IFS= read -r -d '' binary; do
    codesign "${INNER_FLAGS[@]}" --sign "$SIGN_IDENTITY" "$binary"
done < <(find "$APP" -type f \( -name '*.so' -o -name '*.dylib' \) -print0)

codesign "${SIGN_FLAGS[@]}" --sign "$SIGN_IDENTITY" "$APP"
codesign --verify --strict --verbose=2 "$APP"

# ---------------------------------------------------------------- dmg
step "Montando o DMG"
if command -v create-dmg >/dev/null; then
    create-dmg \
        --volname "flow-st8 $VERSION" \
        --icon "flow-st8.app" 150 190 \
        --app-drop-link 450 190 \
        --window-size 600 400 \
        --no-internet-enable \
        "$DMG" "$APP"
else
    STAGE="$BUILD_DIR/dmg"
    rm -rf "$STAGE"
    mkdir -p "$STAGE"
    cp -R "$APP" "$STAGE/"
    ln -s /Applications "$STAGE/Applications"
    hdiutil create -volname "flow-st8 $VERSION" -srcfolder "$STAGE" \
        -ov -format UDZO "$DMG" >/dev/null
fi

codesign --force --sign "$SIGN_IDENTITY" "$DMG"

# ---------------------------------------------------------------- notarize
if [[ -n "$NOTARY_PROFILE" ]]; then
    step "Enviando para a Apple (leva alguns minutos)"
    xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait
    xcrun stapler staple "$DMG"
    step "Conferindo como o Gatekeeper vê"
    spctl -a -t open --context context:primary-signature -v "$DMG"
fi

step "Pronto"
echo "  $DMG"
du -h "$DMG" | cut -f1 | sed 's/^/  tamanho: /'
if [[ -z "$NOTARY_PROFILE" ]]; then
    echo
    echo "  Build não notarizado. Quem baixar precisa liberar com:"
    echo "    xattr -dr com.apple.quarantine /Applications/flow-st8.app"
fi
