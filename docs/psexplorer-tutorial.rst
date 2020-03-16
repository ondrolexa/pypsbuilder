``psexplorer`` tutorial
=======================

Using ``psexplorer`` from command-line
--------------------------------------

``psexplorer`` allows you visualize finalized pseudosection, create isopleths
diagrams or generate `drawpd` file. It provides four command-line scipts
`psgrid`, `psdrawpd`, `psshow` and `psiso`.

To use ``psexplorer`` interactively in Python or Jupyter notebook check
:doc:`api`.

Draw pseudosections
-------------------

Before any further calculations you can check and draw your pseudosection using
`psshow` command which construct finished areas within your project. It has few
options to label pseudosection with assamblages or highlight out phase lines.::

    $ psshow -h
		usage: psshow [-h] [-o OUT [OUT ...]] [-l] [-b] [--cmap CMAP] [--alpha ALPHA]
		              [--connect] [--high HIGH [HIGH ...]]
		              project

		Draw pseudosection from project file

		positional arguments:
		  project               builder project file

		optional arguments:
		  -h, --help            show this help message and exit
		  -o OUT [OUT ...], --out OUT [OUT ...]
		                        highlight out lines for given phases
		  -l, --label           show area labels
		  -b, --bulk            show bulk composition on figure
		  --cmap CMAP           name of the colormap
		  --alpha ALPHA         alpha of colormap
		  --connect             whether mouse click echo stable assemblage
		  --high HIGH [HIGH ...]
		                        highlight field defined by set of phases

For example, to draw pseudosection with marked epidote-out and chlorite-out
lines execute::

    $ psshow '/path/to/project.psb' -o ep chl

.. image:: images/psshow_out.png

Draw isopleths diagrams
-----------------------

To create isopleths diagrams the pseudoction should be gridded at first (In
other case only values from univariant lines and invariant points are used and
interpolated accross areas). Command `psgrid` will do all calculations and
result are saved afterwards, so next time results are automatically loaded. Be
aware that calculations takes some time.::

    $ psgrid -h
		usage: psgrid [-h] [--nx NX] [--ny NY] project

		Calculate compositions in grid

		positional arguments:
		  project     builder project file

		optional arguments:
		  -h, --help  show this help message and exit
		  --nx NX     number of T steps
		  --ny NY     number of P steps

For gridding pseudosection with grid 50x50 run following command::

    $ psgrid '/path/to/project.psb' --nx 50 --ny 50
		Gridding: 100%|█████████████████████████████| 2500/2500 [01:30<00:00, 27.62it/s]
		Grid search done. 0 empty grid points left.

Once gridded you can draw isopleths diagrams using `psiso` command::

		$ psiso -h
		usage: psiso [-h] [-e EXPR] [-f] [-o] [--nosplit] [-b] [--step STEP]
		             [--ncont NCONT] [--colors COLORS] [--cmap CMAP] [--smooth SMOOTH]
		             [--clabel CLABEL [CLABEL ...]] [--high HIGH [HIGH ...]]
		             project phase

		Draw isopleth diagrams

		positional arguments:
		  project               builder project file
		  phase                 phase used for contouring

		optional arguments:
		  -h, --help            show this help message and exit
		  -e EXPR, --expr EXPR  expression evaluated to calculate values
		  -f, --filled          filled contours
		  -o, --out             highlight out line for given phase
		  --nosplit             controls whether the underlying contour is removed or
		                        not
		  -b, --bulk            show bulk composition on figure
		  --step STEP           contour step
		  --ncont NCONT         number of contours
		  --colors COLORS       color for all levels
		  --cmap CMAP           name of the colormap
		  --smooth SMOOTH       smoothness of the approximation
		  --clabel CLABEL [CLABEL ...]
		                        label contours in field defined by set of phases
		  --high HIGH [HIGH ...]
		                        highlight field defined by set of phases

Following example shows isopleths of garnet mode::

    $ psiso '/path/to/project.psb' -f g -e mode

.. image:: images/psiso_mode.png

If the *expression* argument is not provided, the ``psexplorer`` shows list of
all calculated variables available for given phase. ::

		$ psiso '/path/to/project.psb' -f g
		Missing expression argument. Available variables for phase g are:
		mode x z m f xMgX xFeX xMnX xCaX xAlY xFe3Y H2O SiO2 Al2O3 CaO MgO FeO K2O
		Na2O TiO2 MnO O factor G H S V rho

To draw isopleths of almandine garnet proportion you can use expression from a-x
file `alm = x + (-m) x + (-x) z`::

    $ psiso '/path/to/project.psb' -f g -e 'x-m*x-x*z'

or use variable `xFeX`::

		$ psiso tutorial.psb -f g -e xFeX

.. image:: images/psiso_alm.png

If you need to label contour lines, you can use clabel option to define field,
where contour labels are plotted::

    $ psiso '/path/to/project.psb' g -e mode --clabel H2O bi g mu pa pl q ru
		--step 0.005 --colors m

.. image:: images/psiso_clabels.png

Another example of some other options::

    $ psiso tutorial.psb -f g -e mode --step 0.005 --high H2O bi g mu pa pl q ru
    --out chl ep --cmap YlGnBu_r

.. image:: images/psiso_other.png
