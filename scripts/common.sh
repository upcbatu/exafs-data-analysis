#!/usr/bin/env bash

ATOMS_CLUSTER_RMAX="${ATOMS_CLUSTER_RMAX:-6.0}"
FEFF_PATH_RMAX="${FEFF_PATH_RMAX:-5.0}"

find_feff6_runner() {
  local candidates=(feff6 feff6l)
  local cmd
  for cmd in "${candidates[@]}"; do
    if command -v "$cmd" >/dev/null 2>&1; then
      command -v "$cmd"
      return 0
    fi
  done
  return 1
}

generate_feff6_input() {
  local work_dir="$1"
  (
    cd "$work_dir"
    atoms -q -f -r "$ATOMS_CLUSTER_RMAX" -o feff.inp atoms.inp > atoms.stdout.log 2> atoms.stderr.log
    awk -v rmax="$FEFF_PATH_RMAX" '
      /^[[:space:]]*RMAX[[:space:]]+/ {
        printf " RMAX        %s\n", rmax
        next
      }
      { print }
    ' feff.inp > feff.inp.tmp
    mv feff.inp.tmp feff.inp
  )
}

run_feff6_in_dir() {
  local runner="$1"
  local work_dir="$2"
  local runner_name
  runner_name="$(basename "$runner")"

  case "$runner_name" in
    feff6|feff6l)
      (cd "$work_dir" && "$runner")
      ;;
    *)
      echo "Unsupported FEFF6 runner: $runner" >&2
      return 2
      ;;
  esac
}
