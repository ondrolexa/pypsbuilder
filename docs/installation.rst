Installation
============

Easiest way is to use `Anaconda <https://www.anaconda.com/distribution>`_/
`Miniconda <https://docs.conda.io/en/latest/miniconda.html>`_ distribution.

You can create an environment from an ``environment.yml`` file. Use the terminal
or an Anaconda Prompt for the following steps:

  1. Create the environment from the ``environment.yml`` file::

      conda env create -f environment.yml

  2. Activate the new environment::

      conda activate pyps

  3. Install pypsbuilder directly from github using pip::

		  pip install https://github.com/ondrolexa/pypsbuilder/archive/develop.zip
