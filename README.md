# Cu Foil EXAFS Analysis

Reproducible command-line workflow for Cu foil EXAFS data measured at 10 K,
50 K and 150 K.

The pipeline uses the standard Atoms, FEFF and IFEFFIT toolchain:

```text
atoms.inp -> atoms -> feff.inp -> feff6l -> FEFF paths
cu.prj.gz -> extracted mu(E) datasets
```

The GitHub Actions workflow runs on Ubuntu 22.04, installs the EXAFS stack,
extracts the three Cu datasets, generates FEFF input from the crystallographic
model, runs FEFF, and uploads the generated files as artifacts.

## Inputs

```text
data/inputs/atoms.inp
data/inputs/cu.prj.gz
```

`atoms.inp` contains fcc Cu crystallographic data. `cu.prj.gz` contains the
three measured Cu foil datasets.

## Run Locally

On Ubuntu 22.04:

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  horae ifeffit xvfb gnuplot python3 python3-numpy python3-matplotlib

./scripts/probe_stack.sh
./scripts/extract_cu_project.py data/inputs/cu.prj.gz --out artifacts/cu_project
./scripts/run_feff.sh
```

## Outputs

The workflow writes generated files under `artifacts/`:

```text
artifacts/probe/probe.log
artifacts/cu_project/*.csv
artifacts/cu_project/*.json
artifacts/feff/cu/feff.inp
artifacts/feff/cu/feff*.dat
```

These files are uploaded by CI and are not committed.

## References

- `horae` provides the Demeter/Horae tools used here, including `atoms`,
  `athena` and `artemis`: https://packages.debian.org/sid/horae
- `atoms` is the command-line tool used to generate `feff.inp` from
  `atoms.inp`: https://manpages.debian.org/testing/horae/atoms.1.en.html
- `ifeffit` provides the command-line XAFS/EXAFS backend and `feffit`:
  https://packages.debian.org/bookworm/ifeffit
- The workflow runs on GitHub-hosted Ubuntu runners:
  https://docs.github.com/en/actions/reference/github-hosted-runners-reference
