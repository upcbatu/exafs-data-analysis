#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/artifacts/feff"
mkdir -p "$OUT"

if ! command -v atoms >/dev/null 2>&1; then
  echo "Missing required command: atoms" >&2
  exit 1
fi

if ! command -v feff6l >/dev/null 2>&1; then
  echo "Missing required command: feff6l" >&2
  exit 1
fi

rm -rf "$OUT/cu"
mkdir -p "$OUT/cu"
cp "$ROOT/data/inputs/atoms.inp" "$OUT/cu/atoms.inp"

(
  cd "$OUT/cu"
  atoms -q -f -o feff.inp atoms.inp > atoms.stdout.log 2> atoms.stderr.log
  feff6l > feff6l.log 2>&1
)

if [[ ! -s "$OUT/cu/feff.inp" ]]; then
  echo "Atoms did not produce feff.inp" >&2
  exit 1
fi

if ! find "$OUT/cu" -maxdepth 1 -name 'feff*.dat' | grep -q .; then
  echo "FEFF did not produce feff*.dat files" >&2
  exit 1
fi

printf 'FEFF output written to %s\n' "$OUT/cu"
