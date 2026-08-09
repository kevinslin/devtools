#!/bin/zsh
set -euo pipefail

ROOT_DIR="${0:A:h:h}"
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

swift test \
    --disable-sandbox \
    --cache-path "$SWIFTPM_CACHE" \
    --config-path "$SWIFTPM_CONFIG" \
    --security-path "$SWIFTPM_SECURITY"
