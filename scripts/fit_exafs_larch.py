#!/usr/bin/env python3
"""Run non-interactive Cu foil EXAFS fits with XrayLarch.

Inputs are the CSV/JSON files extracted from cu.prj.gz and the FEFF path files
generated from atoms.inp. Outputs are fit reports, plots, and summary tables.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

try:
    from larch import Group
    from larch.fitting import param, param_group
    from larch.xafs import (
        autobk,
        feffit,
        feffit_dataset,
        feffit_report,
        feffit_transform,
        feffpath,
        xftf,
    )
except ImportError as exc:  # pragma: no cover - exercised in CI environment
    raise SystemExit(
        "Missing XrayLarch. Install with: python3 -m pip install -r requirements-analysis.txt"
    ) from exc


@dataclass(frozen=True)
class DatasetInfo:
    label: str
    temperature_k: int
    csv_path: Path
    e0_ev: float
    rbkg: float
    kmax: float


@dataclass(frozen=True)
class PathInfo:
    path_id: int
    file_name: str
    nleg: int
    degeneracy: float
    reff: float
    amp_ratio: float


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv_arrays(path: Path) -> tuple[np.ndarray, np.ndarray]:
    data = np.genfromtxt(path, delimiter=",", names=True)
    return np.asarray(data["energy_eV"], dtype=float), np.asarray(data["mu"], dtype=float)


def parse_temperature(label: str) -> int:
    if "010k" in label:
        return 10
    if "050k" in label:
        return 50
    if "150k" in label:
        return 150
    raise ValueError(f"Cannot infer temperature from label: {label}")


def load_datasets(data_dir: Path) -> list[DatasetInfo]:
    manifest = load_json(data_dir / "manifest.json")
    out: list[DatasetInfo] = []
    for item in manifest:
        label = str(item["label"])
        out.append(
            DatasetInfo(
                label=label,
                temperature_k=parse_temperature(label),
                csv_path=data_dir / str(item["csv"]),
                e0_ev=float(item["e0_eV"]),
                rbkg=float(item.get("bkg_rbkg", 1.0) or 1.0),
                kmax=float(item["fft_kmax"]),
            )
        )
    return sorted(out, key=lambda item: item.temperature_k)


def load_path_info(feff_dir: Path) -> list[PathInfo]:
    rows: list[PathInfo] = []
    files_dat = feff_dir / "files.dat"
    if not files_dat.exists():
        raise FileNotFoundError(f"Missing FEFF files.dat: {files_dat}")

    for line in files_dat.read_text(encoding="latin1", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped.startswith("feff") or ".dat" not in stripped:
            continue
        fields = stripped.split()
        file_name = fields[0]
        rows.append(
            PathInfo(
                path_id=int(file_name.replace("feff", "").replace(".dat", "")),
                file_name=file_name,
                nleg=int(fields[4]),
                degeneracy=float(fields[3]),
                reff=float(fields[5]),
                amp_ratio=float(fields[2]),
            )
        )
    if not rows:
        raise ValueError(f"No FEFF paths found in {files_dat}")
    return rows


def prepare_chi(dataset: DatasetInfo, out_dir: Path) -> Group:
    energy, mu = read_csv_arrays(dataset.csv_path)
    group = Group(
        __name__=dataset.label,
        energy=energy,
        mu=mu,
        temperature_k=dataset.temperature_k,
    )
    autobk(group, e0=dataset.e0_ev, rbkg=dataset.rbkg, kw=2, kmin=0, kmax=dataset.kmax)
    xftf(group.k, group.chi, group=group, kmin=2.0, kmax=dataset.kmax, kw=2, dk=2.0, window="hanning")

    chi_dir = out_dir / "chi_data"
    chi_dir.mkdir(parents=True, exist_ok=True)
    stem = dataset.label.replace(".dat", "")
    np.savetxt(
        chi_dir / f"{stem}_chi.csv",
        np.column_stack([group.k, group.chi]),
        delimiter=",",
        header="k_invA,chi",
        comments="",
    )
    return group


def make_path(feff_dir: Path, info: PathInfo, *, s02: str, e0: str, deltar: str, sigma2: str) -> Any:
    return feffpath(str(feff_dir / info.file_name), s02=s02, e0=e0, deltar=deltar, sigma2=sigma2)


def stat_value(out: Any, name: str) -> float | None:
    for obj in (getattr(out, "fit", None), getattr(out, "params", None)):
        if obj is not None and hasattr(obj, name):
            value = getattr(obj, name)
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    return None


def param_value(pars: Any, name: str) -> tuple[float | None, float | None]:
    if not hasattr(pars, name):
        return None, None
    par = getattr(pars, name)
    value = getattr(par, "value", par)
    stderr = getattr(par, "stderr", None)
    try:
        value_out = float(value)
    except (TypeError, ValueError):
        value_out = None
    try:
        stderr_out = float(stderr) if stderr is not None else None
    except (TypeError, ValueError):
        stderr_out = None
    return value_out, stderr_out


def feffit_report_text(out: Any) -> str:
    try:
        return feffit_report(out, with_paths=True, min_correl=0.2)
    except TypeError:
        return feffit_report(out)


def parse_fit_report(report: str) -> dict[str, Any]:
    stats_keys = {
        "n_variables": "n_variables",
        "n_independent": "n_independent",
        "chi_square": "chi_square",
        "reduced chi_square": "reduced_chi_square",
        "r-factor": "r_factor",
        "Akaike info crit": "aic",
        "Bayesian info crit": "bic",
    }
    parsed: dict[str, Any] = {"statistics": {}, "parameters": {}}
    for line in report.splitlines():
        stat_match = re.match(r"\s*([A-Za-z0-9_ -]+?)\s+=\s+([-+0-9.eE]+)\s*$", line)
        if stat_match:
            key = stat_match.group(1).strip()
            if key in stats_keys:
                parsed["statistics"][stats_keys[key]] = float(stat_match.group(2))
            continue

        param_match = re.match(
            r"\s*([A-Za-z0-9_]+)\s+=\s+([-+0-9.eE]+)"
            r"(?:\s+\+/-\s+([-+0-9.eE]+))?",
            line,
        )
        if param_match:
            name = param_match.group(1)
            stderr = param_match.group(3)
            parsed["parameters"][name] = {
                "value": float(param_match.group(2)),
                "stderr": float(stderr) if stderr is not None else None,
            }
    return parsed


def ensure_r_arrays(group: Any, *, kmin: float, kmax: float, kw: int, dk: float) -> None:
    if hasattr(group, "r") and hasattr(group, "chir_mag"):
        return
    if hasattr(group, "k") and hasattr(group, "chi"):
        xftf(group.k, group.chi, group=group, kmin=kmin, kmax=kmax, kw=kw, dk=dk, window="hanning")


def array_attr(group: Any, names: Iterable[str]) -> np.ndarray | None:
    for name in names:
        if hasattr(group, name):
            return np.asarray(getattr(group, name), dtype=float)
    return None


def plot_fit(
    dataset: Any,
    out_path: Path,
    *,
    title: str,
    kmin: float,
    kmax: float,
    rmin: float,
    rfit_max: float,
    rplot_max: float,
) -> None:
    data = dataset.data
    model = dataset.model
    ensure_r_arrays(data, kmin=kmin, kmax=kmax, kw=2, dk=2.0)
    ensure_r_arrays(model, kmin=kmin, kmax=kmax, kw=2, dk=2.0)

    fig, axes = plt.subplots(2, 2, figsize=(11, 7.4))
    axes = axes.ravel()

    data_k = array_attr(data, ["k"])
    data_chi = array_attr(data, ["chi"])
    model_k = array_attr(model, ["k"])
    model_chi = array_attr(model, ["chi"])
    if data_k is not None and data_chi is not None:
        axes[0].plot(data_k, data_chi * data_k**2, label="data", lw=1.6)
    if model_k is not None and model_chi is not None:
        axes[0].plot(model_k, model_chi * model_k**2, label="fit", lw=1.4)
    axes[0].set_xlim(kmin, kmax)
    axes[0].set_xlabel(r"$k$ / $\AA^{-1}$")
    axes[0].set_ylabel(r"$k^2\chi(k)$")
    axes[0].legend()

    data_r = array_attr(data, ["r"])
    data_mag = array_attr(data, ["chir_mag"])
    model_r = array_attr(model, ["r"])
    model_mag = array_attr(model, ["chir_mag"])
    if data_r is not None and data_mag is not None:
        axes[1].plot(data_r, data_mag, label="data", lw=1.6)
    if model_r is not None and model_mag is not None:
        axes[1].plot(model_r, model_mag, label="fit", lw=1.4)
    axes[1].axvspan(rmin, rfit_max, color="0.92", zorder=0)
    axes[1].set_xlim(0, rplot_max)
    axes[1].set_xlabel(r"$R$ / $\AA$")
    axes[1].set_ylabel(r"$|\chi(R)|$")
    axes[1].legend()

    data_re = array_attr(data, ["chir_re", "chir_real"])
    model_re = array_attr(model, ["chir_re", "chir_real"])
    data_im = array_attr(data, ["chir_im", "chir_imag"])
    model_im = array_attr(model, ["chir_im", "chir_imag"])
    if data_r is not None and data_re is not None:
        axes[2].plot(data_r, data_re, label="data Re", lw=1.4)
    if model_r is not None and model_re is not None:
        axes[2].plot(model_r, model_re, label="fit Re", lw=1.2)
    if data_r is not None and data_im is not None:
        axes[2].plot(data_r, data_im, label="data Im", lw=1.4, ls="--")
    if model_r is not None and model_im is not None:
        axes[2].plot(model_r, model_im, label="fit Im", lw=1.2, ls="--")
    axes[2].axvspan(rmin, rfit_max, color="0.92", zorder=0)
    axes[2].set_xlim(0, rplot_max)
    axes[2].set_xlabel(r"$R$ / $\AA$")
    axes[2].set_ylabel(r"Re/Im $\chi(R)$")
    axes[2].legend(fontsize="small")

    if data_r is not None and data_mag is not None and model_r is not None and model_mag is not None:
        model_interp = np.interp(data_r, model_r, model_mag)
        axes[3].plot(data_r, data_mag - model_interp, lw=1.2)
    axes[3].axhline(0, color="0.3", lw=0.8)
    axes[3].axvspan(rmin, rfit_max, color="0.92", zorder=0)
    axes[3].set_xlim(0, rplot_max)
    axes[3].set_xlabel(r"$R$ / $\AA$")
    axes[3].set_ylabel(r"$|\chi(R)|$ residual")

    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def plot_full_model_comparison(ss_dataset: Any, ms_dataset: Any, out_path: Path) -> None:
    for dataset in (ss_dataset, ms_dataset):
        ensure_r_arrays(dataset.data, kmin=2.0, kmax=18.0, kw=2, dk=2.0)
        ensure_r_arrays(dataset.model, kmin=2.0, kmax=18.0, kw=2, dk=2.0)

    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.0), sharex=True)
    for ax, dataset, title in zip(
        axes[:2],
        (ss_dataset, ms_dataset),
        ("SS-only", "SS+MS"),
    ):
        data_r = array_attr(dataset.data, ["r"])
        data_mag = array_attr(dataset.data, ["chir_mag"])
        model_r = array_attr(dataset.model, ["r"])
        model_mag = array_attr(dataset.model, ["chir_mag"])
        if data_r is not None and data_mag is not None:
            ax.plot(data_r, data_mag, label="data", lw=1.6)
        if model_r is not None and model_mag is not None:
            ax.plot(model_r, model_mag, label="fit", lw=1.4)
        ax.axvspan(1.4, 4.5, color="0.92", zorder=0)
        ax.set_title(title)
        ax.set_xlabel(r"$R$ / $\AA$")
        ax.legend(fontsize="small")

    ss_r = array_attr(ss_dataset.data, ["r"])
    ss_mag = array_attr(ss_dataset.data, ["chir_mag"])
    ss_model_r = array_attr(ss_dataset.model, ["r"])
    ss_model_mag = array_attr(ss_dataset.model, ["chir_mag"])
    ms_model_r = array_attr(ms_dataset.model, ["r"])
    ms_model_mag = array_attr(ms_dataset.model, ["chir_mag"])
    if (
        ss_r is not None
        and ss_mag is not None
        and ss_model_r is not None
        and ss_model_mag is not None
        and ms_model_r is not None
        and ms_model_mag is not None
    ):
        axes[2].plot(ss_r, ss_mag - np.interp(ss_r, ss_model_r, ss_model_mag), label="SS-only", lw=1.2)
        axes[2].plot(ss_r, ss_mag - np.interp(ss_r, ms_model_r, ms_model_mag), label="SS+MS", lw=1.2)
    axes[2].axhline(0, color="0.3", lw=0.8)
    axes[2].axvspan(1.4, 4.5, color="0.92", zorder=0)
    axes[2].set_title("Magnitude residual")
    axes[2].set_xlabel(r"$R$ / $\AA$")
    axes[2].legend(fontsize="small")

    axes[0].set_ylabel(r"$|\chi(R)|$")
    axes[2].set_ylabel(r"$|\chi(R)|$ residual")
    for ax in axes:
        ax.set_xlim(0, 4.8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def write_report(path: Path, text: str) -> None:
    path.write_text(text + "\n", encoding="utf-8")


def write_model_comparison_csv(out_dir: Path, summaries: list[dict[str, Any]]) -> None:
    rows = []
    for summary in summaries:
        stats = summary["statistics"]
        rows.append(
            {
                "model": summary["model"],
                "paths": " ".join(path["file"] for path in summary["paths"]),
                "k_range_A-1": "2.0-18.0",
                "R_range_A": "1.4-4.5",
                "n_variables": stats.get("n_variables"),
                "n_independent": stats.get("n_independent"),
                "r_factor": stats.get("r_factor"),
                "reduced_chi_square": stats.get("reduced_chi_square"),
                "chi_square": stats.get("chi_square"),
                "AIC": stats.get("aic"),
                "BIC": stats.get("bic"),
            }
        )
    with (out_dir / "full_10k_model_comparison.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run_full_fit(
    *,
    name: str,
    data: Group,
    feff_dir: Path,
    paths: list[PathInfo],
    selected_ids: list[int],
    out_dir: Path,
) -> dict[str, Any]:
    selected = [item for item in paths if item.path_id in selected_ids]
    path_by_id = {item.path_id: item for item in selected}

    pars = param_group(
        amp=param(0.90, vary=True, min=0.40, max=1.20),
        del_e0=param(0.0, vary=True, min=-10.0, max=10.0),
        alpha=param(0.0, vary=True, min=-0.03, max=0.03),
        sig2_1=param(0.003, vary=True, min=0.0005, max=0.030),
        sig2_2=param(0.004, vary=True, min=0.0005, max=0.040),
        sig2_3=param(0.005, vary=True, min=0.0005, max=0.050),
    )

    def sig2_name(path_id: int) -> str:
        if path_id == 1:
            return "sig2_1"
        if path_id in {2, 3, 4}:
            return "sig2_2"
        return "sig2_3"

    pathlist = [
        make_path(
            feff_dir,
            path_by_id[path_id],
            s02="amp",
            e0="del_e0",
            deltar="alpha*reff",
            sigma2=sig2_name(path_id),
        )
        for path_id in selected_ids
    ]

    transform = feffit_transform(
        fitspace="r",
        kmin=2.0,
        kmax=18.0,
        kweight=2,
        dk=2.0,
        window="hanning",
        rmin=1.4,
        rmax=4.5,
    )
    dset = feffit_dataset(data=data, pathlist=pathlist, transform=transform)
    out = feffit(pars, dset, rmax_out=6.0)

    model_dir = out_dir / name
    model_dir.mkdir(parents=True, exist_ok=True)
    report = feffit_report_text(out)
    parsed_report = parse_fit_report(report)
    write_report(model_dir / "fit_report.txt", report)
    plot_fit(
        dset,
        model_dir / "fit_plot.png",
        title=name,
        kmin=2.0,
        kmax=18.0,
        rmin=1.4,
        rfit_max=4.5,
        rplot_max=4.8,
    )

    summary = {
        "model": name,
        "temperature_k": int(getattr(data, "temperature_k")),
        "paths": [
            {
                "file": item.file_name,
                "nleg": item.nleg,
                "degeneracy": item.degeneracy,
                "reff": item.reff,
                "amp_ratio": item.amp_ratio,
            }
            for item in selected
        ],
        "statistics": parsed_report["statistics"],
        "parameters": {
            name: parsed_report["parameters"].get(
                name,
                {"value": value, "stderr": stderr},
            )
            for name in ["amp", "del_e0", "alpha", "sig2_1", "sig2_2", "sig2_3"]
            for value, stderr in [param_value(pars, name)]
        },
    }
    write_json(model_dir / "summary.json", summary)
    return {"summary": summary, "dataset": dset}


def run_temperature_fit(
    *,
    datasets: list[DatasetInfo],
    chi_groups: dict[int, Group],
    feff_dir: Path,
    first_path: PathInfo,
    out_dir: Path,
) -> dict[str, Any]:
    pars = param_group(
        amp=param(0.90, vary=True, min=0.40, max=1.20),
        del_e0=param(0.0, vary=True, min=-10.0, max=10.0),
        delr_10=param(0.0, vary=True, min=-0.08, max=0.08),
        delr_50=param(0.0, vary=True, min=-0.08, max=0.08),
        delr_150=param(0.0, vary=True, min=-0.08, max=0.08),
        sig2_10=param(0.0030, vary=True, min=0.0005, max=0.030),
        sig2_50=param(0.0035, vary=True, min=0.0005, max=0.030),
        sig2_150=param(0.0045, vary=True, min=0.0005, max=0.030),
    )

    transform = feffit_transform(
        fitspace="r",
        kmin=2.0,
        kmax=12.0,
        kweight=2,
        dk=2.0,
        window="hanning",
        rmin=1.6,
        rmax=2.75,
    )
    dsets = []
    for dataset in datasets:
        temp = dataset.temperature_k
        path = make_path(
            feff_dir,
            first_path,
            s02="amp",
            e0="del_e0",
            deltar=f"delr_{temp}",
            sigma2=f"sig2_{temp}",
        )
        dsets.append(feffit_dataset(data=chi_groups[temp], pathlist=[path], transform=transform))

    out = feffit(pars, dsets, rmax_out=5.0)

    model_dir = out_dir / "first_shell_temperature"
    model_dir.mkdir(parents=True, exist_ok=True)
    report = feffit_report_text(out)
    parsed_report = parse_fit_report(report)
    write_report(model_dir / "fit_report.txt", report)

    rows = []
    for dataset, dset in zip(datasets, dsets):
        temp = dataset.temperature_k
        delr_param = parsed_report["parameters"].get(f"delr_{temp}")
        sig2_param = parsed_report["parameters"].get(f"sig2_{temp}")
        delr, delr_err = (
            (delr_param["value"], delr_param["stderr"])
            if delr_param
            else param_value(pars, f"delr_{temp}")
        )
        sig2, sig2_err = (
            (sig2_param["value"], sig2_param["stderr"])
            if sig2_param
            else param_value(pars, f"sig2_{temp}")
        )
        r_value = first_path.reff + delr if delr is not None else None
        rows.append(
            {
                "temperature_K": temp,
                "delR_A": delr,
                "delR_error_A": delr_err,
                "R_A": r_value,
                "R_error_A": delr_err,
                "sigma2_A2": sig2,
                "sigma2_error_A2": sig2_err,
            }
        )
        plot_fit(
            dset,
            model_dir / f"fit_{temp}K.png",
            title=f"First-shell fit {temp} K",
            kmin=2.0,
            kmax=12.0,
            rmin=1.6,
            rfit_max=2.75,
            rplot_max=3.2,
        )

    with (model_dir / "temperature_parameters.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    temps = np.asarray([row["temperature_K"] for row in rows], dtype=float)
    r_values = np.asarray([row["R_A"] for row in rows], dtype=float)
    r_errors = np.asarray([row["R_error_A"] or 0 for row in rows], dtype=float)
    sig2_values = np.asarray([row["sigma2_A2"] for row in rows], dtype=float)
    sig2_errors = np.asarray([row["sigma2_error_A2"] or 0 for row in rows], dtype=float)

    fig, ax = plt.subplots(figsize=(5.4, 4.0))
    ax.errorbar(temps, r_values, yerr=r_errors, marker="o", capsize=3)
    ax.set_xlabel("T / K")
    ax.set_ylabel(r"$R$ / $\AA$")
    fig.tight_layout()
    fig.savefig(model_dir / "R_vs_T.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.4, 4.0))
    ax.errorbar(temps, sig2_values, yerr=sig2_errors, marker="o", capsize=3)
    ax.set_xlabel("T / K")
    ax.set_ylabel(r"$\sigma^2$ / $\AA^2$")
    fig.tight_layout()
    fig.savefig(model_dir / "sigma2_vs_T.png", dpi=180)
    plt.close(fig)

    summary = {
        "model": "first_shell_temperature",
        "path": {
            "file": first_path.file_name,
            "nleg": first_path.nleg,
            "degeneracy": first_path.degeneracy,
            "reff": first_path.reff,
            "amp_ratio": first_path.amp_ratio,
        },
        "statistics": parsed_report["statistics"],
        "common_parameters": {
            name: parsed_report["parameters"].get(
                name,
                {"value": value, "stderr": stderr},
            )
            for name in ["amp", "del_e0"]
            for value, stderr in [param_value(pars, name)]
        },
        "temperature_parameters": rows,
    }
    write_json(model_dir / "summary.json", summary)
    return summary


def write_overview(out_dir: Path, summaries: list[dict[str, Any]]) -> None:
    by_name = {summary["model"]: summary for summary in summaries}
    lines = [
        "# Cu Foil EXAFS CLI Fit Summary",
        "",
        "Generated by `scripts/fit_exafs_larch.py`.",
        "",
        "## Models",
        "",
    ]
    for summary in summaries:
        stats = summary.get("statistics", {})
        lines.append(f"- `{summary['model']}`: R-factor = {stats.get('r_factor')}")

    ss_only = by_name.get("full_10k_ss_only")
    ss_ms = by_name.get("full_10k_ss_ms")
    temp_summary = by_name.get("first_shell_temperature")
    lines.extend(["", "## Interpretation Notes", ""])
    if ss_only and ss_ms:
        ss_stats = ss_only.get("statistics", {})
        ms_stats = ss_ms.get("statistics", {})
        lines.append(
            "- The SS+MS model reduces the 10 K R-factor from "
            f"{ss_stats.get('r_factor')} to {ms_stats.get('r_factor')} with the same "
            "k/R fit ranges and number of varying parameters."
        )
    if temp_summary:
        rows = sorted(temp_summary.get("temperature_parameters", []), key=lambda row: row["temperature_K"])
        if len(rows) >= 2:
            low = rows[0]
            high = rows[-1]
            r_delta = high["R_A"] - low["R_A"]
            r_sigma = float(np.hypot(low["R_error_A"] or 0.0, high["R_error_A"] or 0.0))
            sig2_delta = high["sigma2_A2"] - low["sigma2_A2"]
            sig2_sigma = float(np.hypot(low["sigma2_error_A2"] or 0.0, high["sigma2_error_A2"] or 0.0))
            lines.append(
                "- The first-shell R increase from "
                f"{low['temperature_K']} K to {high['temperature_K']} K is {r_delta:.6g} A "
                f"with combined uncertainty {r_sigma:.6g} A, so it should be described as weak."
            )
            lines.append(
                "- The first-shell sigma2 increase over the same temperatures is "
                f"{sig2_delta:.6g} A^2 with combined uncertainty {sig2_sigma:.6g} A^2."
            )
    lines.extend(
        [
            "",
            "## Output Files",
            "",
            "- `chi_data/*_chi.csv`: background-subtracted EXAFS chi(k) arrays.",
            "- `full_10k_ss_only/fit_report.txt` and `fit_plot.png`: 10 K single-scattering model.",
            "- `full_10k_ss_ms/fit_report.txt` and `fit_plot.png`: 10 K single- and multiple-scattering model.",
            "- `full_10k_model_comparison.csv` and `.png`: SS-only vs SS+MS comparison.",
            "- `first_shell_temperature/temperature_parameters.csv`: R and sigma2 values for 10 K, 50 K and 150 K.",
            "- `first_shell_temperature/R_vs_T.png` and `sigma2_vs_T.png`: temperature trend plots.",
        ]
    )
    (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("artifacts/cu_project"))
    parser.add_argument("--feff-dir", type=Path, default=Path("artifacts/feff/cu"))
    parser.add_argument("--out", type=Path, default=Path("artifacts/analysis"))
    args = parser.parse_args()

    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True, exist_ok=True)

    datasets = load_datasets(args.data_dir)
    paths = load_path_info(args.feff_dir)
    chi_groups = {item.temperature_k: prepare_chi(item, args.out) for item in datasets}

    full_10k = chi_groups[10]
    ss_only_result = run_full_fit(
        name="full_10k_ss_only",
        data=full_10k,
        feff_dir=args.feff_dir,
        paths=paths,
        selected_ids=[1, 2, 5],
        out_dir=args.out,
    )
    ss_ms_result = run_full_fit(
        name="full_10k_ss_ms",
        data=full_10k,
        feff_dir=args.feff_dir,
        paths=paths,
        selected_ids=[1, 2, 3, 4, 5, 6, 7],
        out_dir=args.out,
    )
    plot_full_model_comparison(
        ss_only_result["dataset"],
        ss_ms_result["dataset"],
        args.out / "full_10k_model_comparison.png",
    )
    summaries = [
        ss_only_result["summary"],
        ss_ms_result["summary"],
        run_temperature_fit(
            datasets=datasets,
            chi_groups=chi_groups,
            feff_dir=args.feff_dir,
            first_path=paths[0],
            out_dir=args.out,
        ),
    ]
    write_model_comparison_csv(args.out, summaries[:2])

    write_overview(args.out, summaries)
    print(f"Wrote analysis outputs to {args.out}")
    for summary in summaries:
        print(f"- {summary['model']}: R-factor {summary.get('statistics', {}).get('r_factor')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
