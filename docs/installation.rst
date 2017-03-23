============
Installation
============

For Anaconda distribution (for now only Linux64 and Win64 supported) you can install from personal channel::

    conda install -c ondrolexa pypsbuilder

For other platforms install dependencies using conda::

    conda install numpy matplotlib scipy pyqt
    conda install -c conda-forge shapely descartes tqdm

or by any other mechanism (see `Installing Scientific Packages <https://packaging.python.org/science/>`_).

and than install pypsbuilder directly from github using pip::

    pip install https://github.com/ondrolexa/pypsbuilder/archive/master.zip

For upgrade use::

    pip install --upgrade --upgrade-strategy only-if-needed \
      https://github.com/ondrolexa/pypsbuilder/archive/master.zip


To install most recent (and likely less stable) development version use::

    pip install https://github.com/ondrolexa/pypsbuilder/archive/develop.zip
