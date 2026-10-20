#!/usr/bin/env bash
# Build easypdkprog + programmer firmware from the free-pdk *development* branch.
#
# Needed for the PFS122 / PFS121 / PFS172B / PFS123 / PFS173B: the 1.3 release
# does not know these names. The development software talks a newer protocol
# (1.5 vs 1.3), so the programmer firmware must be updated to match.
#
#   tools/build-easypdkprog-dev.sh [install-dir]      (default: ~/easy-pdk-dev)
#
# Linux packages (Debian/Ubuntu):
#   sudo apt install build-essential git gcc-arm-none-eabi libnewlib-arm-none-eabi dfu-util
set -euo pipefail

DEST="${1:-$HOME/easy-pdk-dev}"
REPO=https://github.com/free-pdk/easy-pdk-programmer-software.git

if [ -d "$DEST/.git" ]; then
  git -C "$DEST" fetch origin development
  git -C "$DEST" checkout development
  git -C "$DEST" pull --ff-only origin development
else
  git clone -b development "$REPO" "$DEST"
fi

echo "== Building easypdkprog"
make -C "$DEST" -j"$(nproc 2>/dev/null || echo 2)"

echo "== Building programmer firmware"
if command -v arm-none-eabi-gcc >/dev/null && command -v dfu-suffix >/dev/null; then
  make -C "$DEST/Firmware/source" -j"$(nproc 2>/dev/null || echo 2)" all
  FW="$DEST/Firmware/source/build/EASYPDKPROG.dfu"
else
  FW=""
  echo "arm-none-eabi-gcc or dfu-suffix not found, skipping firmware"
  echo "(install gcc-arm-none-eabi libnewlib-arm-none-eabi dfu-util)."
fi

cat <<MSG

Done.
  Programmer software: $DEST/easypdkprog
    Use it from your project:   make program EASYPDKPROG=$DEST/easypdkprog
    or copy it onto your PATH:  sudo cp $DEST/easypdkprog /usr/local/bin/
MSG
if [ -n "$FW" ]; then
cat <<MSG
  Firmware: $FW
    Flash it (once):
      1. Unplug the programmer.
      2. Hold its button, plug in USB, then release the button.
      3. dfu-util -d 0483:df11 -a "@Internal Flash  /0x08000000/064*0002Kg" \\
           --dfuse-address 0x08000000 -D "$FW"
      4. Unplug and replug. Check with:  $DEST/easypdkprog probe
MSG
fi
