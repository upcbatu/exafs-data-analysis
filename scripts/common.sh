#!/usr/bin/env bash

find_feff_runner() {
  local candidates=(feff6l feffit)
  local cmd
  for cmd in "${candidates[@]}"; do
    if command -v "$cmd" >/dev/null 2>&1; then
      command -v "$cmd"
      return 0
    fi
  done
  return 1
}
