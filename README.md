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

## Command References

| Workflow step | Command or package | Purpose in this repository | Source |
| --- | --- | --- | --- |
| Install Demeter/Horae tools | `apt-get install horae` | Installs the Demeter/Horae command and GUI tools used by the pipeline, including `atoms`, `athena` and `artemis`. | [Debian `horae` package](https://packages.debian.org/sid/horae) |
| Install IFEFFIT tools | `apt-get install ifeffit` | Installs the command-line XAFS/EXAFS backend used here, including `ifeffit` and `feffit`. | [Debian `ifeffit` package](https://packages.debian.org/bookworm/ifeffit) |
| Generate FEFF input | `atoms -q -f -o feff.inp atoms.inp` | Converts the Cu crystallographic input into a FEFF input file. The `atoms` manpage defines `atoms` as a crystallographic input converter for FEFF and documents the `-o` output option. | [`atoms(1)` manpage](https://manpages.debian.org/testing/horae/atoms.1.en.html) |
| Check EXAFS backend | `ifeffit -x 'show @commands'` | Starts IFEFFIT non-interactively and prints available IFEFFIT commands for the CI probe log. The package description identifies IFEFFIT as a command-line XAFS analysis program. | [Debian `ifeffit` package](https://packages.debian.org/bookworm/ifeffit) |
| Run FEFF path generation | `feffit` or `feff6l` | Runs the FEFF-compatible executable available in the installed EXAFS stack. CI records the selected executable and package file list in `artifacts/probe/probe.log`. | [Debian `ifeffit` package](https://packages.debian.org/bookworm/ifeffit) |
| Extract measured datasets | `scripts/extract_cu_project.py data/inputs/cu.prj.gz` | Extracts the three stored `mu(E)` arrays from the compressed Cu project into CSV/JSON artifacts. This script is repository code because the project file is a serialized Demeter/Athena data container. | [script](scripts/extract_cu_project.py) |
| Run in CI | `runs-on: ubuntu-22.04` | Executes the workflow on a GitHub-hosted Ubuntu runner. | [GitHub-hosted runners](https://docs.github.com/en/actions/reference/github-hosted-runners-reference) |
