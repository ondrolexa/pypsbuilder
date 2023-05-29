Installation
============

In the moment you need to have Python and needed modules installed locally and
**pypsbuilder** must be installed from source. Just follow these steps:

  1. Easiest way to install Python is to use `Anaconda <https://www.anaconda.com/distribution>`_/
  `Miniconda <https://docs.conda.io/en/latest/miniconda.html>`_/
  `Miniforge <https://github.com/conda-forge/miniforge>`_ distribution.
  Download it and follow installation steps.

  2. Download latest version of `pypsbuilder <https://github.com/ondrolexa/pypsbuilder/archive/master.zip>`_
  and unzip to folder of your choice.

  3. Use conda to create an environment from an ``environment.yml``
  file. Open the terminal, change directory where you unzip the source
  and execute following command::

      $ conda env create -f environment.yml

  .. image:: images/create_environment.png

  4. Activate the new environment and install from current directory::

      $ conda activate pyps
      (pyps) $ pip install .

  .. image:: images/install_locally.png

Alternatively, you can use ``pip`` to install pypsbuilder::

      (pyps) $ pip install pypsbuilder

Upgrade to latest version
-------------------------

You can anytime upgrade your existing pypsbuilder to the latest released version::

		  (pyps) $ pip install --upgrade pypsbuilder

or to latest master version at github::

      (pyps) $ pip install --upgrade https://github.com/ondrolexa/pypsbuilder/archive/master.zip
