# FINA

FINA is a Python project focused on extracting stock market insights, computing relevant metrics, and sharing results in a clear format.

## Current Status

This repository is currently a scaffold and includes a basic entrypoint in `main.py`.

## Tech Stack

- Python `3.13.x`
- [uv](https://docs.astral.sh/uv/) for dependency and environment management

## Requirements

- `uv` installed locally
- Python compatible with `>=3.13, <3.14` (as defined in `pyproject.toml`)

## Project Structure

```text
fina/
├── main.py
├── pyproject.toml
└── README.md
```

## Setup

From the repository root:

```bash
cd fina
uv sync
```

This creates a virtual environment and installs project dependencies.

## Run

```bash
cd fina
uv run python main.py
```

Current output:

```text
Hello from fina!
```

## Development Notes

- Dependencies are defined in `pyproject.toml`.
- Add new packages with:

```bash
uv add <package-name>
```

## Roadmap

- Ingest market data from reliable sources
- Compute core metrics (returns, volatility, drawdown, momentum)
- Build reusable analysis modules
- Export insights to reports or dashboards

## License

all rights reserved.