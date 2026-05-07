#!/usr/bin/env bash

find_feff_runner() {
  local candidates=(feff8l feff6 feff6l)
  local cmd
  for cmd in "${candidates[@]}"; do
    if command -v "$cmd" >/dev/null 2>&1; then
      command -v "$cmd"
      return 0
    fi
  done
  return 1
}

run_feff_in_dir() {
  local runner="$1"
  local work_dir="$2"
  local runner_name
  runner_name="$(basename "$runner")"

  case "$runner_name" in
    feff8l)
      "$runner" "$work_dir"
      ;;
    feff6|feff6l)
      (cd "$work_dir" && "$runner")
      ;;
    *)
      echo "Unsupported FEFF runner: $runner" >&2
      return 2
      ;;
  esac
}
