# pypsbuilder

[![Build Status](https://travis-ci.org/ondrolexa/pypsbuilder.svg?branch=develop)](https://travis-ci.org/github/ondrolexa/pypsbuilder)
[![Documentation Status](https://readthedocs.org/projects/pypsbuilder/badge/?version=develop)](https://pypsbuilder.readthedocs.io/en/latest/?badge=develop)
[![HitCount](http://hits.dwyl.com/ondrolexa/pypsbuilder.svg)](http://hits.dwyl.com/ondrolexa/pypsbuilder)
[![Twitter](https://img.shields.io/twitter/url?style=social&url=https%3A%2F%2Fgithub.com%2Fondrolexa%2Fpypsbuilder)](https://twitter.com/intent/tweet?text=Wow:&url=https%3A%2F%2Fgithub.com%2Fondrolexa%2Fpypsbuilder)

Not that simplistic THERMOCALC front-end for constructing pseudosections

## Install development version

Easiest way to install latest version of pypsbuilder is to use conda package management system. Create psbuilder conda environment from the included `environment.yml` file:

    conda env create -f environment.yml

or manually:

    conda create -n pyps python=3.8 pyqt=5 numpy matplotlib scipy networkx notebook jupyterlab shapely descartes tqdm

Then activate the new environment:

    conda activate pyps

and install pypsbuilder using pip:

    pip install https://github.com/ondrolexa/pypsbuilder/archive/develop.zip

or if you downloaded pypsbuilder repository, run in unzipped folder:

    pip install .

## Documentation an tutorials

Check documentation and tutorials for developement version [https://pypsbuilder.readthedocs.io/en/develop](https://pypsbuilder.readthedocs.io/en/develop)

## License

pypsbuilder is free software: you can redistribute it and/or modify it under the terms of the MIT License. A copy of this license is provided in ``LICENSE`` file.
