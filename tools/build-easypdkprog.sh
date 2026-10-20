#!/usr/bin/env bash
# Build easypdkprog 1.3 (stable) with PFS122 / PFS121 / PFS172B support.
#
# Uses the PoGo430 fork of easy-pdk-programmer-software: the 1.3 release code with
# PFS122/PFS121/PFS172B added as names for the PFS172 (same chip ID). It talks to the
# stock 1.3 programmer firmware, so the programmer does NOT need a firmware update.
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
  No firmware update needed: it works with the 1.3 programmer firmware.
MSG
