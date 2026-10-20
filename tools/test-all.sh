#!/usr/bin/env bash
# Build the template and every example for each device and report the result.
#   tools/test-all.sh                     # PFS154 PFS122 PMS150C
#   tools/test-all.sh PFS173 PMS152       # other devices
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEVICES="${*:-PFS154 PFS122 PMS150C}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fail=0

for dev in $DEVICES; do
  for ex in template $(ls "$ROOT/examples"); do
    dir="$WORK/$dev-$ex"
    if [ "$ex" = template ]; then
      "$ROOT/new-project.sh" "$dir" "$dev" >/dev/null
    else
      "$ROOT/new-project.sh" "$dir" "$dev" "$ex" >/dev/null
    fi
    if out="$(make -C "$dir" -s 2>&1)"; then
      usage="$(echo "$out" | awk '/ROM:|RAM:/ {printf "%s %s/%s  ", $1, $2, $4}')"
      printf "  ok    %-8s %-14s %s\n" "$dev" "$ex" "$usage"
    else
      printf "  FAIL  %-8s %s\n" "$dev" "$ex"
      echo "$out" | sed 's/^/        /' | tail -15
      fail=1
    fi
  done
done
exit $fail
