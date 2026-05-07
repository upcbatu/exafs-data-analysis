#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/common.sh"
OUT="$ROOT/artifacts/feff"
mkdir -p "$OUT"

if ! command -v atoms >/dev/null 2>&1; then
  echo "Missing required command: atoms" >&2
  exit 1
fi

FEFF_RUNNER="$(find_feff6_runner || true)"
if [[ -z "$FEFF_RUNNER" ]]; then
  echo "Missing required FEFF6 runner: expected feff6 or feff6l" >&2
  exit 1
fi

rm -rf "$OUT/cu"
mkdir -p "$OUT/cu"
cp "$ROOT/data/inputs/atoms.inp" "$OUT/cu/atoms.inp"

generate_feff6_input "$OUT/cu"
run_feff6_in_dir "$FEFF_RUNNER" "$OUT/cu" > "$OUT/cu/feff.log" 2>&1

if [[ ! -s "$OUT/cu/feff.inp" ]]; then
  echo "Atoms did not produce feff.inp" >&2
  exit 1
fi

if ! find "$OUT/cu" -maxdepth 1 -name 'feff*.dat' | grep -q .; then
  echo "FEFF6 did not produce feff*.dat files" >&2
  exit 1
fi

printf 'FEFF6 output written to %s\n' "$OUT/cu"
