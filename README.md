# pypsbuilder

![master](https://github.com/ondrolexa/pypsbuilder/actions/workflows/master.yml/badge.svg)
[![Documentation Status](https://readthedocs.org/projects/pypsbuilder/badge/?version=latest)](https://pypsbuilder.readthedocs.io/en/latest/?badge=latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/ondrolexa/pypsbuilder/blob/master/LICENSE)
[![GitHub release (latest by date)](https://img.shields.io/github/v/release/ondrolexa/pypsbuilder)](https://github.com/ondrolexa/pypsbuilder/releases/latest)
[![Twitter](https://img.shields.io/twitter/url/http/shields.io.svg?style=social&url=https%3A%2F%2Fgithub.com%2Fondrolexa%2Fpypsbuilder)](https://twitter.com/intent/tweet?text=Wow:&url=https%3A%2F%2Fgithub.com%2Fondrolexa%2Fpypsbuilder)

Not that simplistic THERMOCALC front-end for constructing and visualizations of P-T, T-X and P-X pseudosections

## How to install

Easiest way to install **pypsbuilder** is to use conda package management system. Create conda environment from the included `environment.yml` file:

    conda env create -f environment.yml

or manually:

    conda create -n pyps python=3.8 pyqt=5 numpy matplotlib scipy networkx notebook shapely tqdm

Then activate the new environment:

    conda activate pyps

and install pypsbuilder using pip:

    pip install https://github.com/ondrolexa/pypsbuilder/archive/master.zip

or if you downloaded pypsbuilder repository, run in unzipped folder:

    pip install .

### Install development version

You can install latest development version from develop branch:

    pip install https://github.com/ondrolexa/pypsbuilder/archive/develop.zip

### Upgrade existing installation

To upgrade an already installed **pypsbuilder** to the latest master version:

    pip install --upgrade https://github.com/ondrolexa/pypsbuilder/archive/master.zip

or development version:

    pip install --upgrade https://github.com/ondrolexa/pypsbuilder/archive/develop.zip

## Documentation and tutorials

Check documentation and tutorials on RTD [https://pypsbuilder.readthedocs.io/en/latest/](https://pypsbuilder.readthedocs.io/en/latest/)

## License

pypsbuilder is free software: you can redistribute it and/or modify it under the terms of the MIT License. A copy of this license is provided in ``LICENSE`` file.
