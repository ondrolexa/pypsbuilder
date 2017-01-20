============
Installation
============

For Anaconda distribution (for now only Linux64 and Win64 supported) you can install from personal channel::

    $ conda install -c ondrolexa pypsbuilder

For other platforms install dependencies using conda::

    $ conda install numpy matplotlib pyqt

or by any other mechanism (see `Installing Scientific Packages <https://packaging.python.org/science/>`_.

Than install pypsbuilder directly from github using pip::

    $ pip install https://github.com/ondrolexa/pypsbuilder/archive/master.zip

To upgrade to latest version use::

    $ pip install --upgrade https://github.com/ondrolexa/pypsbuilder/archive/master.zip \
          --upgrade-strategy only-if-needed

To install most recent (and likely less stable) developement version use::

    $ pip install https://github.com/ondrolexa/pypsbuilder/archive/develop.zip