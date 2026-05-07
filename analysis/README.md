# EXAFS Fit Analysis

This folder documents the non-interactive fitting layer used after the
command-line Atoms and FEFF6 preparation steps.

The fitting script uses XrayLarch to:

1. convert the extracted `mu(E)` datasets to `chi(k)` with `autobk`;
2. load the generated FEFF6 `feffNNNN.dat` scattering paths;
3. fit the 10 K dataset up to 4.5 Angstrom with two models:
   - single-scattering paths only;
   - single- and multiple-scattering paths;
4. fit the first Cu-Cu shell for 10 K, 50 K and 150 K;
5. write reports, plots and summary tables under `artifacts/analysis/`.

Run after the FEFF artifacts have been generated:

```bash
./scripts/extract_cu_project.py data/inputs/cu.prj.gz --out artifacts/cu_project
./scripts/run_feff.sh
./scripts/fit_exafs_larch.py \
  --data-dir artifacts/cu_project \
  --feff-dir artifacts/feff/cu \
  --out artifacts/analysis
```

The generated analysis outputs are uploaded by the GitHub Actions workflow and
are not committed.
