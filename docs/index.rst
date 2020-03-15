.. pypsbuilder documentation master file, created by
   sphinx-quickstart on Wed Jan 18 19:28:46 2017.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to PyPSbuilder documentation!
=======================================

.. toctree::
   :maxdepth: 1

   tutorial
   installation
   usage
   api
   authors

THERMOCALC is a thermodynamic calculation program (Powell & Holland 1988) that
uses an internally-consistent thermodynamic dataset (Holland & Powell, 1998, 2011)
to undertake thermobarometry and phase diagram calculations for metamorphic rocks.
However, using thermocalc to create a diagram is quite laborious; each curve
must be calculated by hand and the Schreinemaker's analysis must
be done manually. The curves must be built up one by one, and manually combined.

**PyPSbuilder** is developed with idea to make this tedious process much easier
and more enjoyable while keeping the concept to force users really understand
the Phase Rule, Schreinemaker's analysis, and how variance changes across field
boundaries.

Check :doc:`tutorial` to see how it works.


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
