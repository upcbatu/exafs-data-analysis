#!/usr/bin/env python3
"""Extract the Cu foil project datasets into CSV and metadata JSON.

`cu.prj.gz` is a gzip-compressed Demeter/Athena-format project. The project
stores each dataset as Perl-ish arrays named `@x` and `@y`, with an `@args`
array containing labels, background settings and titles. This script extracts
only those recorded raw mu(E) arrays. It does not perform fitting.
"""

from __future__ import annotations

import argparse
import ast
import csv
import gzip
import json
import re
from pathlib import Path
from typing import Any

EXPECTED_DATASETS = {
    "cu010k.dat": 612,
    "cu050k.dat": 620,
    "cu150k.dat": 618,
}


def read_project(path: Path) -> str:
    with path.open("rb") as fh:
        magic = fh.read(2)
    if magic == b"\x1f\x8b":
        with gzip.open(path, "rt", encoding="latin1") as fh:
            return fh.read()
    return path.read_text(encoding="latin1")


def parse_perl_tuple(text: str) -> list[Any]:
    return list(ast.literal_eval("(" + text + ")"))


def as_args_dict(values: list[Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for idx in range(0, len(values) - 1, 2):
        out[str(values[idx])] = values[idx + 1]
    return out


def safe_stem(label: str) -> str:
    label = label.replace(".dat", "")
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("_")


def extract_records(project_text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    chunks = project_text.split("$old_group = ")
    for chunk in chunks[1:]:
        if "@args =" not in chunk or "@x =" not in chunk or "@y =" not in chunk:
            continue

        group_match = re.match(r"'([^']+)'", chunk)
        args_match = re.search(r"@args = \((.*?)\);\n@x", chunk, flags=re.S)
        x_match = re.search(r"@x = \((.*?)\);\n@y", chunk, flags=re.S)
        y_match = re.search(r"@y = \((.*?)\);\n\[record\]", chunk, flags=re.S)
        if not (group_match and args_match and x_match and y_match):
            continue

        args_dict = as_args_dict(parse_perl_tuple(args_match.group(1)))
        x_values = [float(v) for v in parse_perl_tuple(x_match.group(1))]
        y_values = [float(v) for v in parse_perl_tuple(y_match.group(1))]
        if len(x_values) != len(y_values):
            raise ValueError(
                f"Length mismatch for {args_dict.get('label', group_match.group(1))}: "
                f"{len(x_values)} energies vs {len(y_values)} mu values"
            )

        records.append(
            {
                "group": group_match.group(1),
                "label": args_dict.get("label", group_match.group(1)),
                "args": args_dict,
                "energy_eV": x_values,
                "mu": y_values,
            }
        )
    return records


def write_outputs(records: list[dict[str, Any]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []

    for rec in records:
        stem = safe_stem(str(rec["label"]))
        csv_path = out_dir / f"{stem}.csv"
        meta_path = out_dir / f"{stem}.json"

        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["energy_eV", "mu"])
            writer.writerows(zip(rec["energy_eV"], rec["mu"]))

        args = rec["args"]
        metadata = {
            "group": rec["group"],
            "label": rec["label"],
            "points": len(rec["energy_eV"]),
            "source_file": args.get("file"),
            "e0_eV": float(args["bkg_e0"]) if "bkg_e0" in args else None,
            "edge_step": float(args["bkg_step"]) if "bkg_step" in args else None,
            "bkg_rbkg": float(args["bkg_rbkg"]) if "bkg_rbkg" in args else None,
            "bkg_kw": float(args["bkg_kw"]) if "bkg_kw" in args else None,
            "bkg_window": args.get("bkg_win"),
            "fft_kmin": float(args["fft_kmin"]) if "fft_kmin" in args else None,
            "fft_kmax": float(args["fft_kmax"]) if "fft_kmax" in args else None,
            "fft_dk": float(args["fft_dk"]) if "fft_dk" in args else None,
            "fft_window": args.get("fft_win"),
            "titles": args.get("titles", []),
            "csv": csv_path.name,
        }
        meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        manifest.append(metadata)

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("--out", type=Path, default=Path("artifacts/cu_project"))
    args = parser.parse_args()

    records = extract_records(read_project(args.project))
    if not records:
        raise SystemExit(f"No Athena records found in {args.project}")

    labels = {str(rec["label"]) for rec in records}
    expected_labels = set(EXPECTED_DATASETS)
    if labels != expected_labels:
        raise SystemExit(
            f"Unexpected dataset labels: got {sorted(labels)}, expected {sorted(expected_labels)}"
        )
    for rec in records:
        label = str(rec["label"])
        expected_points = EXPECTED_DATASETS[label]
        if len(rec["energy_eV"]) != expected_points:
            raise SystemExit(
                f"Unexpected point count for {label}: got {len(rec['energy_eV'])}, "
                f"expected {expected_points}"
            )

    write_outputs(records, args.out)
    print(f"Extracted {len(records)} datasets to {args.out}")
    for rec in records:
        print(f"- {rec['label']}: {len(rec['energy_eV'])} points")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
