# pypsbuilder

![master ci](https://github.com/ondrolexa/pypsbuilder/actions/workflows/master.yml/badge.svg)
[![Documentation Status](https://readthedocs.org/projects/pypsbuilder/badge/?version=latest)](https://pypsbuilder.readthedocs.io/en/latest/?badge=latest)
[![MIT License](https://img.shields.io/apm/l/atomic-design-ui.svg?)](https://github.com/tterb/atomic-design-ui/blob/master/LICENSEs)
[![Twitter](https://img.shields.io/twitter/url/http/shields.io.svg?style=social&url=https%3A%2F%2Fgithub.com%2Fondrolexa%2Fpypsbuilder)](https://twitter.com/intent/tweet?text=Wow:&url=https%3A%2F%2Fgithub.com%2Fondrolexa%2Fpypsbuilder)

Not that simplistic THERMOCALC front-end for constructing and visualizations of P-T, T-X and P-X pseudosections

## How to install

Easiest way to install **pypsbuilder** is to use conda package management system. Create conda environment from the included `environment.yml` file:

    conda env create -f environment.yml

or manually:

    conda create -n pyps python=3.8 pyqt=5 numpy matplotlib scipy networkx notebook shapely descartes tqdm

Then activate the new environment:

    conda activate pyps

and install pypsbuilder using pip:

    pip install https://github.com/ondrolexa/pypsbuilder/archive/master.zip

or if you downloaded pypsbuilder repository, run in unzipped folder:

    pip install .

## Documentation and tutorials

Check documentation and tutorials on RTD [https://pypsbuilder.readthedocs.io/en/latest/](https://pypsbuilder.readthedocs.io/en/latest/)

## License

pypsbuilder is free software: you can redistribute it and/or modify it under the terms of the MIT License. A copy of this license is provided in ``LICENSE`` file.
