#!/bin/zsh
set -euo pipefail

ROOT_DIR="${0:A:h:h}"
CONFIGURATION="${1:-release}"
APP_DIR="$ROOT_DIR/dist/Comodoro.app"
CONTENTS_DIR="$APP_DIR/Contents"
MODULE_CACHE="$ROOT_DIR/.build/module-cache"
SWIFTPM_CACHE="$ROOT_DIR/.build/swiftpm-cache"
SWIFTPM_CONFIG="$ROOT_DIR/.build/swiftpm-config"
SWIFTPM_SECURITY="$ROOT_DIR/.build/swiftpm-security"

if [[ -z "${DEVELOPER_DIR:-}" && -d /Applications/Xcode.app/Contents/Developer ]]; then
    export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
fi

cd "$ROOT_DIR"
mkdir -p "$MODULE_CACHE" "$SWIFTPM_CACHE" "$SWIFTPM_CONFIG" "$SWIFTPM_SECURITY"
export SWIFTPM_MODULECACHE_OVERRIDE="$MODULE_CACHE"
export CLANG_MODULE_CACHE_PATH="$MODULE_CACHE"

SWIFT_ARGS=(
    --disable-sandbox
    --cache-path "$SWIFTPM_CACHE"
    --config-path "$SWIFTPM_CONFIG"
    --security-path "$SWIFTPM_SECURITY"
)

swift build -c "$CONFIGURATION" "${SWIFT_ARGS[@]}"
BIN_DIR="$(swift build -c "$CONFIGURATION" --show-bin-path "${SWIFT_ARGS[@]}")"

rm -rf "$APP_DIR"
mkdir -p "$CONTENTS_DIR/MacOS" "$CONTENTS_DIR/Resources"
cp "$BIN_DIR/Comodoro" "$CONTENTS_DIR/MacOS/Comodoro"

cat > "$CONTENTS_DIR/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>Comodoro</string>
    <key>CFBundleIdentifier</key>
    <string>com.kevinlin.comodoro</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>Comodoro</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHumanReadableCopyright</key>
    <string>Copyright © 2026 Kevin Lin</string>
</dict>
</plist>
PLIST

codesign --force --sign - "$APP_DIR"
echo "$APP_DIR"
