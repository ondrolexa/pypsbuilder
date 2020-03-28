``psbuilder`` tutorial
======================

Before you can successfully run ``psbuilder`` you have to prepare working
directory, which contain `THERMOCALC` and `drawpd` executables, preferences
file, thermodynamic dataset and a-x file. Builder will work only with certain
setting, like ``calcmode`` must be 1, ``calctatp`` have to be ask etc.
Psbuilder checks for valid  settings and gives warning if some action is needed.

**The only special need is to place ptguess tags and dogmin tags in your
scriptfile, to allow ``psbuilder`` manage starting guesses and dogmin runs**.

Just insert following comment lines to your script file to line where normally
starting guesses should be placed (definitely before last `*` and before
standard or samecoding guesses).::

		%{PSBGUESS-BEGIN}
		%{PSBGUESS-END}

for dogmin replace existing ``dogmin`` script with::

		%{PSBDOGMIN-BEGIN}
		dogmin no
		%{PSBDOGMIN-END}

and for bulk composition place before and after existing ``setbulk`` script(s)
these tags::

%{PSBBULK-BEGIN}
setbulk ....
%{PSBBULK-END}

If you are not sure, which scripts should be set on and off, you can check
example scriptfile in ``examples/avgpelite`` directory.

New P-T pseudosection project
-----------------------------

Use the terminal or an Anaconda Prompt, activate the ``pyps`` environment and
run ``psbuilder``::

		$ conda activate pyps
		(pyps) $ psbuilder

To create the new project (File->New project), you have to select working
directory. ``psbuilder`` automatically execute `THERMOCALC`, check settings in your
script file and initialize project. Available phases are automatically
populated to `Phases` list and default P-T range from scriptfile is set.

.. image:: images/psbuilder_init.png

Create invariant point
----------------------

In *Phases* list you select phases which should be in stable assemblage, while
in lower pane you select two phases for which modal proportion should be zero.
Than just click either ``Calc P`` or ``Calc T`` and invariant point will appear
on diagram and in the list of invariant points in lower right part of window.

.. image:: images/psbuilder_inv.png

Create univariant line
----------------------

Similarly, you can create univariant line, when only one phase is selected to
have zero modal proportion. In addition ``psbuilder`` allows you to create
univariant lines based on already calculated invariant points. Right-click on
invariant points will show context menu with possible choices of univariant
lines passing trough this point and which are not yet calculated. Hit **Calc T**
or **Calc P** according to dp/dT of univariant line. Once calculated, result is
added to diagram and to the list of univariant lines in upper right part of the
window. Within this list you can define begin and end by selecting appropriate
invariant points.

.. image:: images/psbuilder_uni.png

By default, ``psbuilder`` use 50 steps to calculate univariant lines. You can
change it in `Settings` pane. When you need to calculate some short univariant
lines you can zoom into this part of pseudosection and hit one of the ``Calc``
buttons. Active region (possibly extended, check *Extend view range to
calculation range* setting) will be used as computational P-T range. Moreover,
you can manually add univariant line to simply connect two invariant points by
straight line. For ''Manual'' addition of both invariant point or univariant
line present phases and zero mode phases have to be properly selected. Manually
added lines or points are shown in italics in lists. Unconnected univariant
lines are shown in bold.

Double-clicking any univariant line or invariant point in the list will
highlight that line/point on diagram marked by calculated points.

.. highlights::

   Note that double-click name of univariant (or invariant) line will populate
   `Modes` and `Full output` panes at the bottom of application, so you can
   always check what is going on along lines. Double-clicking of tabs heading
   open outputs in larger separate window.

.. image:: images/psbuilder_modes.png

Starting guesses
----------------

``psbuilder`` stores all relevant information for each point or line already
calculated. If you need to update starting guesses during construction of
pseudosection, just choose invariant point or univariant line from which the
starting guesses should be copied and click ``Set ptguess`` button.
``psbuilder`` stores new starting guesses to your script file, so next
calculation will use it. You can any time check and/or modify your script file
with integrated editor on `Script file` pane. The `Log` pane always shows
standard output of last `THERMOCALC` execution.

Phase out lines
---------------

Double click on any phase in *Phases* list will highlight all univariant lines
with zero modal proportion of selected phase and all phase present univariant
lines.

.. image:: images/psbuilder_highlight.png

Manual invariant points or univariant lines
-------------------------------------------

``Manual`` button allows to add user-defined point or line. You need to select
stable phases and zero mode phases accordingly. For manual univariant line
begin and end invariant point must be specified. For manual invariant point, you
can either specify position of point by clicking on diagram by mouse or when
more than two univariant lines passing trough that point already exists,
calculated intersection could be used.

Dogmin
------

``Gmin`` button runs THERMOCALC dogmin script, which tries to calculate phase
equilibria between all possible subsets of a list of selected phases. The
pressure and temperature is indicated by clicking on the diagram. Maximum
variance to be considered (higher max variance -> fewer phases in smallest
assemblage) is set in spin widget next to ``Gmin`` button. Ranked the equilibria
in order of stability by comparing the Gibbs energies of each assemblage are
shown in *Modes* pane.  On *Dogmin* pane you can use ``Select`` button to select
found assemblage in *Phases* and ``Set guesses`` to use ptguess of found
solution.

.. image:: images/psbuilder_dogmin.png

Finished pseudosection should contain topologically correct set of univariant
lines and invariant points. Topology could be checked by creating areas
(Tools>Show areas or Ctrl-A) of stable assemblages.

.. image:: images/psbuilder_finished.png

.. image:: images/psbuilder_areas.png
