# pypsbuilder

[![PyPI - Version](https://img.shields.io/pypi/v/pypsbuilder)](https://pypi.org/project/pypsbuilder/)
[![Testing](https://github.com/ondrolexa/pypsbuilder/actions/workflows/testing.yml/badge.svg?event=push)](https://github.com/ondrolexa/pypsbuilder)
[![Documentation Status](https://readthedocs.org/projects/polylx/badge/?version=stable)](https://pypsbuilder.readthedocs.io/en/latest/?badge=latest)

Not that simplistic THERMOCALC front-end for constructing and visualizations of P-T, T-X and P-X pseudosections

## How to install

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

#### Upgrade existing installation

To upgrade an already installed **pypsbuilder** to the latest release:

    pip install --upgrade pypsbuilder

or to the latest master version:

    pip install --upgrade https://github.com/ondrolexa/pypsbuilder/archive/master.zip

## Documentation and tutorials

Check documentation and tutorials on RTD [https://pypsbuilder.readthedocs.io/en/latest/](https://pypsbuilder.readthedocs.io/en/latest/)

## License

pypsbuilder is free software: you can redistribute it and/or modify it under the terms of the MIT License. A copy of this license is provided in ``LICENSE`` file.
