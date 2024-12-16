# pypsbuilder

[![PyPI version](https://badge.fury.io/py/pypsbuilder.svg)](https://badge.fury.io/py/pypsbuilder)
[![Testing](https://github.com/ondrolexa/pypsbuilder/actions/workflows/testing.yml/badge.svg?event=push)](https://github.com/ondrolexa/pypsbuilder)
[![Documentation Status](https://readthedocs.org/projects/polylx/badge/?version=stable)](https://pypsbuilder.readthedocs.io/en/latest/?badge=latest)

Not that simplistic THERMOCALC front-end for constructing and visualizations of P-T, T-X and P-X pseudosections

## How to install

It is strongly suggested to install **pypsbuilder** into separate environment. You can create
Python virtual environment. For Linux and macOS use:

    python -m venv pyps
    source pyps/bin/activate

for Windows use PowerShell:

    py -m venv pyps
    pyps\Scripts\activate

#### I'm using conda or mamba to manage environments

If you have already have conda or mamba installed, you can create environment with:

    conda create -n pyps numpy matplotlib scipy networkx shapely pyqt tqdm jupyterlab

or

    mamba create -n pyps numpy matplotlib scipy networkx shapely pyqt tqdm jupyterlab

Then activate the new environment:

    conda activate pyps

or

    mamba activate pyps

#### Install pypsbuilder

To install **pypsbuilder**, use pip within the environment:

    pip install pypsbuilder

#### Note for macOS

If you have environment created with conda/mamba install the pypsbuilder with:

    pip install pypsbuilder --no-deps

#### Install master version

You can install latest version from master branch on GitHub:

    pip install https://github.com/ondrolexa/pypsbuilder/archive/master.zip

#### Upgrade existing installation

To upgrade an already installed **pypsbuilder** to the latest release:

    pip install --upgrade pypsbuilder

or to latest master version:

    pip install --upgrade https://github.com/ondrolexa/pypsbuilder/archive/master.zip

## Documentation and tutorials

Check documentation and tutorials on RTD [https://pypsbuilder.readthedocs.io/en/latest/](https://pypsbuilder.readthedocs.io/en/latest/)

## License

pypsbuilder is free software: you can redistribute it and/or modify it under the terms of the MIT License. A copy of this license is provided in ``LICENSE`` file.
