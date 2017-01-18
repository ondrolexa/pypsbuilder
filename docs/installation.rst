============
Installation
============

For Anaconda distribution (for now only Linux64 supported) you can install from personal channel::

    $ conda install -c https://conda.anaconda.org/ondrolexa pypsbuilder

For Anaconda distribution on Windows you can install all dependencies from official channel::

    $ conda install numpy matplotlib networkx pyqt

and install pypsbuilder directly from github using pip::

    $ pip install https://github.com/ondrolexa/pypsbuilder/archive/master.zip

To upgrade to latest version use::

    $ pip install --upgrade https://github.com/ondrolexa/pypsbuilder/archive/master.zip \
          --upgrade-strategy only-if-needed

