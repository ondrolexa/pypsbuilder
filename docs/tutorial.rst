First steps with PyPSbuilder
============================

Before you can successfully run PyPSbuilder you have to prepare working directory,
which contain THERMOCALC 3.40 and Drawpd 1.16 executables, preferences file,
thermodynamic dataset and a-x file. PyPSbuilder will work only with certain setting,
like calcmode must be 1, setexcess keyword have to be present to skip question,
calctatp have to be ask etc. If you are nor sure, what scripts should be set on and off,
you can download sample working directory or download preferences and user files from
Richard's White `Dataset 6 webpage <http://www.metamorph.geo.uni-mainz.de/thermocalc/dataset6/index.html>`_.

New project
-----------

When you create new project, you have to select prepared working directory. PyPSbuilder automatically
execute THERMOCALC, check settings in your scriptfile and initialize project. Available phases are
automatically loaded and default P-T range is set.

.. image:: images/psbuilder_init.png

Create invariant point
----------------------

In upper left pane you select phases which occurs within your field, while in lower left pane you
select two phases which modal proportion should be zero. Than just click *Calc P* or *Calc T* and
invariant point will appear on diagram and in the list of invariant points in lower right part of window.

Create univariant line
----------------------

Similarly, you can create univariant line, when only one phase is selected to have zero modal
proportion. Click *Calc T* or *Calc p* according to dp/dT of univariant line. Once calculated,
result is added to diagram and to the list of univariant lines in upper right part of the window.
Within this list you can define begin and end by selecting appropriate invariant points.

By default, PyPSbuilder use 50 steps to calculate univariant lines. You can change it in Setting pane.

When you need to calculate some short univariant lines you can zoom into this part of pseudosection
and hit *Calc* button. Active region will be used as computational P-T range. Moreover, you can manually
add univariant line to simply connect two invariant points by straight line. Note that for *Manual* addition
of both invariant point or univariant line phases and zero modal proportion phase have to be properly selected

Double-clicking any univariant line in the list will highlight that line on diagram marked by
calculated points. Note that double-click name of univariant (or invariant) line will populate Modes and
Full output panes at the bottom of application, so you can always check what is going on along lines.

Project management and Export
-----------------------------

You can save your project, so next time you will open it all your previous work is restored.
When you are happy with P-T pseudosection, you can either export diagram directly by clicking save button
of graphic toolbar (eps, svg, pdf, jpg and png formats are supported) or you can generate drawpd file (File->Export Drawpd file).

