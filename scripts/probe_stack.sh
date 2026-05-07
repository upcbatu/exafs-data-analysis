#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/common.sh"
OUT="$ROOT/artifacts/probe"
mkdir -p "$OUT"

LOG="$OUT/probe.log"
: > "$LOG"

log() {
  printf '%s\n' "$*" | tee -a "$LOG"
}

run_capture() {
  local name="$1"
  shift
  log ""
  log "## $name"
  set +e
  "$@" >>"$LOG" 2>&1
  local status=$?
  set -e
  log "[exit $status] $*"
  return 0
}

log "# EXAFS CLI Stack Probe"
log "Working root: $ROOT"
log "Date: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
log "OS:"
uname -a | tee -a "$LOG"

log ""
log "# Command availability"
commands=(perl python3 atoms ifeffit feffit feff6l athena artemis gnuplot)
missing=0
for cmd in "${commands[@]}"; do
  if command -v "$cmd" >/dev/null 2>&1; then
    log "OK      $cmd -> $(command -v "$cmd")"
  else
    log "MISSING $cmd"
    case "$cmd" in atoms|ifeffit) missing=1 ;; esac
  fi
done

FEFF_RUNNER="$(find_feff_runner || true)"
if [[ -n "$FEFF_RUNNER" ]]; then
  log "OK      FEFF runner -> $FEFF_RUNNER"
else
  log "MISSING FEFF runner: expected one of feff6l or feffit"
  missing=1
fi

run_capture "atoms version" atoms -v
run_capture "atoms help" atoms -h
run_capture "ifeffit startup" ifeffit -x 'show @commands'
run_capture "ifeffit package files" dpkg -L ifeffit
run_capture "horae package files" dpkg -L horae
if [[ -n "$FEFF_RUNNER" ]]; then
  run_capture "FEFF runner help" "$FEFF_RUNNER" -h
fi

if [[ "$missing" -ne 0 ]]; then
  log ""
  log "Required command-line tools are missing. Probe failed closed."
  exit 1
fi

WORK="$OUT/feff_cu"
rm -rf "$WORK"
mkdir -p "$WORK"
cp "$ROOT/data/inputs/atoms.inp" "$WORK/atoms.inp"

log ""
log "# Atoms -> feff.inp"
(
  cd "$WORK"
  atoms -q -f -o feff.inp atoms.inp > atoms.stdout.log 2> atoms.stderr.log
)

if [[ ! -s "$WORK/feff.inp" ]]; then
  log "Atoms did not produce a non-empty feff.inp."
  exit 1
fi
log "Generated $WORK/feff.inp"

log ""
log "# FEFF run: $FEFF_RUNNER"
(
  cd "$WORK"
  "$FEFF_RUNNER" > feff.log 2>&1
)

log "FEFF output files:"
find "$WORK" -maxdepth 1 -type f -print | sort | tee -a "$LOG"

if ! find "$WORK" -maxdepth 1 -name 'feff*.dat' | grep -q .; then
  log "FEFF did not produce feff*.dat path files."
  exit 1
fi

log ""
log "Probe passed: Atoms and FEFF can run headlessly."
