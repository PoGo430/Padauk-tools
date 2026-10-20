#!/usr/bin/env bash
# Create a new Padauk project from template/.
#
#   ./new-project.sh <dir> [DEVICE] [EXAMPLE]
#
#   ./new-project.sh ~/padauk/blinky                    # PFS154, template main.c
#   ./new-project.sh ~/padauk/test122 PFS122            # PFS122
#   ./new-project.sh ~/padauk/hello PMS150C serial_hello
#
# EXAMPLE is a folder name from examples/ (its main.c replaces the template one).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$ROOT/template"

usage() {
  sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
  echo "Devices:  $(make -s -C "$TEMPLATE" devices | tail -n +2 | awk '{print $1}' | tr '\n' ' ')"
  echo "Examples: $(ls "$ROOT/examples" | tr '\n' ' ')"
  exit 1
}

[ $# -ge 1 ] && [ "$1" != "-h" ] && [ "$1" != "--help" ] || usage
DEST="$1"
DEVICE="${2:-PFS154}"
EXAMPLE="${3:-}"
DEVICE="$(echo "$DEVICE" | tr '[:lower:]' '[:upper:]')"
NAME="$(basename "$DEST" | tr -c 'A-Za-z0-9_\n-' '_')"

make -s -C "$TEMPLATE" devices | awk 'NR > 1 {print $1}' | grep -qx "$DEVICE" \
  || { echo "Unknown device '$DEVICE'."; usage; }
[ -z "$EXAMPLE" ] || [ -f "$ROOT/examples/$EXAMPLE/main.c" ] \
  || { echo "Unknown example '$EXAMPLE'."; usage; }
[ ! -e "$DEST" ] || { echo "'$DEST' already exists, not overwriting."; exit 1; }

mkdir -p "$DEST"
tar -C "$TEMPLATE" --exclude=.build --exclude=.output -cf - . | tar -C "$DEST" -xf -
[ -z "$EXAMPLE" ] || cp "$ROOT/examples/$EXAMPLE/main.c" "$DEST/main.c"

sed -i.bak -e "s/^PROJECT_NAME  ?= .*/PROJECT_NAME  ?= $NAME/" \
           -e "s/^DEVICE        ?= [A-Z0-9]*/DEVICE        ?= $DEVICE/" "$DEST/Makefile"
sed -i.bak -e "s/<Option title=\"[^\"]*\"/<Option title=\"$NAME\"/" "$DEST/padauk.cbp"
mv "$DEST/padauk.cbp" "$DEST/$NAME.cbp"
rm -f "$DEST"/*.bak

echo "Created $DEST  (DEVICE=$DEVICE${EXAMPLE:+, example=$EXAMPLE})"
echo "Next:  cd \"$DEST\" && make && make program"
