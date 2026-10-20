#!/usr/bin/env bash
# Build easypdkprog 1.4 = the stable 1.3 release code + native PFS122 support.
#
# Uses the PoGo430 fork of easy-pdk-programmer-software. The PFS122 is written in its
# datasheet's limited-voltage programming mode, which needs the 1.4 programmer firmware
# (prebuilt in the fork: Firmware/EASYPDKPROG_1.4.dfu). All other chips also work with
# the stock 1.3 firmware.
#
#   tools/build-easypdkprog.sh [install-dir]          (default: ~/easy-pdk)
#   BRANCH=<branch> tools/build-easypdkprog.sh        (build another branch of the fork)
#
# Linux packages (Debian/Ubuntu):  sudo apt install build-essential git
set -euo pipefail

DEST="${1:-$HOME/easy-pdk}"
REPO="${REPO:-https://github.com/PoGo430/easy-pdk-programmer-software.git}"
BRANCH="${BRANCH:-master}"

if [ -d "$DEST/.git" ]; then
  git -C "$DEST" fetch origin "$BRANCH"
  git -C "$DEST" checkout -q "$BRANCH" 2>/dev/null || git -C "$DEST" checkout -q -b "$BRANCH" "origin/$BRANCH"
  git -C "$DEST" pull -q --ff-only origin "$BRANCH"
else
  git clone -b "$BRANCH" "$REPO" "$DEST"
fi

make -C "$DEST" -j"$(nproc 2>/dev/null || echo 2)"

if "$DEST/easypdkprog" list | grep -q "PFS122"; then
  echo
  echo "Built $DEST/easypdkprog ($("$DEST/easypdkprog" --version)) with PFS122 support."
else
  echo "Built, but this branch doesn't list the PFS122. Check BRANCH=$BRANCH." >&2
  exit 1
fi
cat <<MSG
  Use it from a project:     make program EASYPDKPROG=$DEST/easypdkprog
  or put it on your PATH:    sudo cp $DEST/easypdkprog /usr/local/bin/

  For the PFS122, flash the 1.4 programmer firmware once:
    1. unplug the programmer, hold its button, plug in USB, release the button
    2. dfu-util -d 0483:df11 -a "@Internal Flash  /0x08000000/064*0002Kg" \\
         --dfuse-address 0x08000000 -D $DEST/Firmware/EASYPDKPROG_1.4.dfu
    3. unplug, plug back in:  $DEST/easypdkprog -v probe   (shows Firmware:1.4)
  Other chips work with the 1.3 or the 1.4 firmware.
MSG
