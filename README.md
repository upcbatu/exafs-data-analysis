# Cu Foil EXAFS Analysis

Reproducible command-line workflow for Cu foil EXAFS data measured at 10 K,
50 K and 150 K.

The pipeline uses the standard Atoms, FEFF6 and IFEFFIT toolchain:

```text
atoms.inp -> atoms -> feff.inp -> feff6 -> FEFF paths
cu.prj.gz -> extracted mu(E) datasets
```

The GitHub Actions workflow runs on Ubuntu 22.04, installs the EXAFS stack,
extracts the three Cu datasets, generates FEFF input from the crystallographic
model, runs FEFF6 to produce `feffNNNN.dat` path files, runs the scripted EXAFS
fits, and uploads the generated files as artifacts.

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
python3 -m pip install -r requirements-analysis.txt
python3 scripts/fit_exafs_larch.py \
  --data-dir artifacts/cu_project \
  --feff-dir artifacts/feff/cu \
  --out artifacts/analysis
```

## Outputs

The workflow writes generated files under `artifacts/`:

```text
artifacts/probe/probe.log
artifacts/cu_project/*.csv
artifacts/cu_project/*.json
artifacts/feff/cu/feff.inp
artifacts/feff/cu/feff*.dat
artifacts/analysis/**/*.txt
artifacts/analysis/**/*.csv
artifacts/analysis/**/*.png
```

These files are uploaded by CI and are not committed.

## Command References

| Workflow step | Command or package | Purpose in this repository | Source |
| --- | --- | --- | --- |
| Install Demeter/Horae tools | `apt-get install horae` | Installs the Demeter/Horae utilities checked by the pipeline, including `atoms`, `athena` and `artemis`. | [Debian `horae` package](https://packages.debian.org/sid/horae) |
| Install IFEFFIT tools | `apt-get install ifeffit` | Installs the command-line XAFS/EXAFS backend used here, including `ifeffit`, `feffit` and `feff6`. | [Ubuntu `ifeffit` package](https://launchpad.net/ubuntu/jammy/+package/ifeffit) |
| Generate FEFF input | `atoms -q -f -o feff.inp atoms.inp` | Converts the Cu crystallographic input into a FEFF input file. The `atoms` manpage defines `atoms` as a crystallographic input converter for FEFF and documents the `-o` output option. | [`atoms(1)` manpage](https://manpages.debian.org/testing/horae/atoms.1.en.html) |
| Check EXAFS backend | `ifeffit -x 'show @commands'` | Starts IFEFFIT non-interactively and prints available IFEFFIT commands for the CI probe log. The package description identifies IFEFFIT as a command-line XAFS analysis program. | [Ubuntu `ifeffit` package](https://launchpad.net/ubuntu/jammy/+package/ifeffit) |
| Run FEFF6 path generation | `feff6` | Runs FEFF6 in the folder containing `feff.inp`, producing `feffNNNN.dat` path outputs consumed by the fitting script. CI verifies the installed executable through `dpkg -L ifeffit` in `artifacts/probe/probe.log`. | [Ubuntu `ifeffit` package](https://launchpad.net/ubuntu/jammy/+package/ifeffit) |
| Extract measured datasets | `scripts/extract_cu_project.py data/inputs/cu.prj.gz` | Extracts the three stored `mu(E)` arrays from the compressed Cu project into CSV/JSON artifacts. This script is repository code because the project file is a serialized Demeter/Athena data container. | [script](scripts/extract_cu_project.py) |
| Fit EXAFS models | `scripts/fit_exafs_larch.py` | Converts `mu(E)` to `chi(k)` with `autobk`, fits generated FEFF paths with `feffit`, and writes fit reports, parameter tables and plots. | [XrayLarch FEFF fitting](https://xraypy.github.io/xraylarch/xafs_feffit.html) |
| Install fit library | `pip install -r requirements-analysis.txt` | Installs XrayLarch for non-interactive FEFF-path fitting. | [XrayLarch installation](https://xraypy.github.io/xraylarch/installation.html) |
| Run in CI | `runs-on: ubuntu-22.04` | Executes the workflow on a GitHub-hosted Ubuntu runner. | [GitHub-hosted runners](https://docs.github.com/en/actions/reference/github-hosted-runners-reference) |
