# pypsbuilder

[![PyPI - Version](https://img.shields.io/pypi/v/pypsbuilder)](https://pypi.org/project/pypsbuilder/)
[![Testing](https://github.com/ondrolexa/pypsbuilder/actions/workflows/testing.yml/badge.svg?event=push)](https://github.com/ondrolexa/pypsbuilder)
[![Documentation Status](https://readthedocs.org/projects/pypsbuilder/badge/?version=latest)](https://pypsbuilder.readthedocs.io/en/latest/?badge=latest)

Not that simplistic THERMOCALC front-end for constructing and visualizations of P-T, T-X and P-X pseudosections

## How to install

### Using uv (recommended)

If you don't already have [uv](https://docs.astral.sh/uv/) installed, see the
[installation instructions](https://docs.astral.sh/uv/getting-started/installation/).

Create an isolated environment and install **pypsbuilder** into it. **You should choose the UI framework using option** `pyqt5` **or** `pyqt6`:

    uv venv
    uv pip install pypsbuilder[pyqt6]

JupyterLab could also be installed providing the `jupyter` option:

    uv pip install pypsbuilder[pyqt6,jupyter]

### Using pip and venv

It is strongly suggested to install **pypsbuilder** into separate environment. You can create
Python virtual environment. For Linux and macOS use:

    python -m venv .venv
    source .venv/bin/activate

for Windows use Command Prompt or PowerShell:

    python -m venv .venv
    .venv\Scripts\activate

or, if you will got error *'python' is not recognized as an internal or external command*, try:

    py -m venv .venv
    .venv\Scripts\activate

> [!NOTE]
> On Microsoft Windows, it may be required to set the execution policy in PowerShell for the user.
> You can do this by issuing the following PowerShell command:
> ```
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

and install **pypsbuilder** using pip within the environment. **You should choose the UI framework using option** `pyqt5` **or** `pyqt6`:

    pip install pypsbuilder[pyqt6]

JupyterLab could also be installed providing the `jupyter` option:

    pip install pypsbuilder[pyqt6,jupyter]

## I'm using conda or mamba to manage environments

If you have already have conda or mamba installed, you can create environment with:

    conda create -n pyps python=3.12.8 matplotlib shapely pyqt tqdm scikit-image qtpy jupyterlab

or

    mamba create -n pyps python=3.12.8 matplotlib shapely pyqt tqdm scikit-image qtpy jupyterlab

Then activate the new environment:

    conda activate pyps

or

    mamba activate pyps

and install with pip. As PyQt is already installed with mamba/conda, we will install **pypsbuilder** without UI framework:

    pip install pypsbuilder

> [!NOTE]
> If you encounter errors during install, try to install without upgrading dependencies:
> ```
> pip install --no-deps pypsbuilder
> ```

### Upgrade existing installation

To upgrade an already installed **pypsbuilder** to the latest release:

    pip install --upgrade pypsbuilder

or to the latest master version:

    pip install --upgrade https://github.com/ondrolexa/pypsbuilder/archive/master.zip

## Contributing / development install

Clone the repository and install with uv:

    uv sync --extra pyqt6 --extra jupyter --extra tests --extra docs --group dev

This installs pypsbuilder in editable mode with UI, notebook, test and docs
extras plus dev tooling (ruff, pre-commit), matching the committed
`uv.lock`.

### Running tests

Run the full test suite (must be run from the repo root, since tests
reference `./examples/outputs` with a relative path):

    uv run pytest
    uv run pytest --cov --cov-report=xml

Run a single test:

    uv run pytest pypsbuilder/tests/test_pclasses.py::test_parse_ini1

### Formatting and linting

pypsbuilder uses [ruff](https://docs.astral.sh/ruff/) for both formatting and linting:

    uv run ruff format pypsbuilder
    uv run ruff check pypsbuilder

### pre-commit hooks

Formatting, linting and the test suite also run automatically via
[pre-commit](https://pre-commit.com/):

    uv run pre-commit install
    uv run pre-commit run --all-files

### Building the package

    uv build

### Rebuilding Qt UI modules

After editing a `.ui` file in Qt Designer, regenerate the corresponding
`ui_*.py` module (requires `pyuic6`):

    cd pypsbuilder/ui && ./compile_ui.sh

The script rewrites each generated file's `PyQt6` imports to `qtpy`
imports, so the app stays usable with either `pyqt5` or `pyqt6`.

## Documentation and tutorials

Check documentation and tutorials on RTD [https://pypsbuilder.readthedocs.io/en/latest/](https://pypsbuilder.readthedocs.io/en/latest/)

## License

pypsbuilder is free software: you can redistribute it and/or modify it under the terms of the MIT License. A copy of this license is provided in ``LICENSE`` file.
