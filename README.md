# VCF Genotype Browser

A Django project that loads genotypes from a VCF file into a database and lets you search them
by chromosome and genomic region. Data is split across five related models, so genotypes from
several samples can be stored side by side without duplicating variants.

## Requirements

Python 3.11, Django 5.1, SQLite. All dependencies are listed in `dev.yml`.

## Quick start

```bash
mamba env create -f dev.yml
mamba activate test-task-django
```

Download a VCF file:

```bash
wget https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/NA12878_HG001/latest/GRCh38/HG001_GRCh38_1_22_v4.2.1_benchmark.vcf.gz
```

Create the database and load the file:

```bash
python manage.py migrate
python manage.py load_vcf HG001_GRCh38_1_22_v4.2.1_benchmark.vcf.gz
```

Run the server:

```bash
python manage.py runserver
```

The search page is at http://127.0.0.1:8000/genotypes/

## Project structure

```
config/                                    project settings
find_genotype/                             the app
  management/commands/load_vcf.py          VCF loader
  templates/find_genotype/                 search page template
  migrations/                              database schema
  models.py, forms.py, views.py
dev.yml                                    conda environment
pyproject.toml                             ruff configuration
```

## Data model

| Model | What it holds |
|---|---|
| `Assembly` | reference genome build, e.g. `GRCh38` |
| `Chromosome` | chromosome within an assembly, with its length |
| `Coordinate` | position, `REF` and `ALT` — a fact about the genome |
| `Sample` | one sample from one VCF file |
| `Genotype` | `GT`, `DP`, `GQ`, `QUAL`, `FILTER`, `INFO` — a fact about the sample |

The split follows the VCF format itself: the first eight columns describe a position in the
genome and are the same for everyone, while the sample columns describe one person. Loading a
second sample therefore adds genotypes but reuses the existing coordinates.

`QUAL`, `FILTER` and `INFO` are stored on `Genotype` rather than on `Coordinate`, because they
describe how confidently a variant was called in one particular call set, not the variant itself.

Two constraints keep the data consistent:

- `unique_variant` — a coordinate is unique per chromosome, position, `REF` and `ALT`;
- `unique_genotype` — a sample has at most one genotype per coordinate.

## load_vcf

```
python manage.py load_vcf PATH [--assembly NAME]
```

- `PATH` — plain `.vcf` or gzipped `.vcf.gz`; the archive is read as a stream, not unpacked to disk.
- `--assembly` — assembly name. If omitted, it is taken from the `assembly=` attribute of the
  `##contig` header, and falls back to `unknown`.

The loader reads the header first (contig lengths, sample names), then streams the data rows in
batches of 3000. Each batch reuses coordinates that already exist and creates only the missing
ones. The whole load runs in a single transaction, so a failure leaves no partial data behind.

The benchmark file above contains 3 893 341 variants across 22 chromosomes. Loading it takes
about 7 minutes and produces a 2.3 GB SQLite database.

## Search page

- chromosome and sample are picked from drop-down lists, so there is nothing to mistype;
- the region is given as start and end positions; `start` must not be greater than `end`;
- results are paginated, 50 rows per page;
- the remaining VCF fields are available per row under **Read more**.

Coordinates are indexed by chromosome and position — the `unique_variant` constraint doubles as
that index — so a query stays cheap on the full dataset: searching the whole of `chr1` matches
307 854 genotypes and still renders its first page in about 0.1 s.

## Tests

```bash
pytest
```

With a coverage report:

```bash
pytest --cov=find_genotype --cov-report=term-missing
```

The suite checks form validation, the loader (row counts, a second sample reusing existing
coordinates, a repeated sample being rejected, per-sample `QUAL`/`FILTER`, gzipped input) and the
search page (opening with no query, filtering by region and by sample). It runs on small VCF
fixtures from `tests/data/` and takes under a second. Current coverage is 96%.

## Development

The code is formatted and linted with `ruff`:

```bash
ruff format .
ruff check .
```

## Assumptions and limitations

- Header parsing is simplified: quoted values containing commas are not supported.
- Chromosome names are stored as they appear in the file, so `chr1` and `1` are treated as
  different chromosomes.
- `QUAL`, `FILTER` and `INFO` are duplicated across samples that come from the same multi-sample
  file. This is a deliberate trade-off: keeping them per call set would require a sixth model.
- Loading a sample that is already in the database is rejected, so a single sample split across
  several files (one per chromosome, for example) cannot be loaded.
- If the same variant appears twice in one file, only the last occurrence is kept.
