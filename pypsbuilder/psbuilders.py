"""
Visual pseudosection builder for THERMOCALC
"""
# author: Ondrej Lexa
# website: petrol.natur.cuni.cz/~ondro

import sys
import os
try:
  import cPickle as pickle
except ImportError:
  import pickle
import gzip
from pathlib import Path
from datetime import datetime
import itertools

from pkg_resources import resource_filename
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QT_VERSION_STR
from PyQt5.Qt import PYQT_VERSION_STR

import numpy as np
import matplotlib
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar)
from matplotlib.widgets import Cursor
from matplotlib import cm
from matplotlib.colors import ListedColormap, BoundaryNorm, Normalize
from descartes import PolygonPatch
from shapely.geometry import Point
from scipy.interpolate import interp1d

try:
    import networkx as nx
    NX_OK = True
except ImportError as e:
    NX_OK = False

from .ui_psbuilder import Ui_PSBuilder
from .ui_txbuilder import Ui_TXBuilder
from .ui_pxbuilder import Ui_PXBuilder
from .ui_addinv import Ui_AddInv
from .ui_adduni import Ui_AddUni
from .ui_uniguess import Ui_UniGuess
from .psclasses import (TCAPI, InvPoint, UniLine, Dogmin, polymorphs,
                        PTsection, TXsection, PXsection)
from . import __version__

# Make sure that we are using QT5
matplotlib.use('Qt5Agg')

matplotlib.rcParams['xtick.direction'] = 'out'
matplotlib.rcParams['ytick.direction'] = 'out'

unihigh_kw = dict(lw=3, alpha=1, marker='o', ms=4, color='red', zorder=10)
invhigh_kw = dict(alpha=1, ms=8, color='red', zorder=10)
outhigh_kw = dict(lw=3, alpha=1, marker=None, ms=4, color='red', zorder=10)
presenthigh_kw = dict(lw=9, alpha=0.6, marker=None, ms=4, color='grey', zorder=-10)

app_icons = dict(PSBuilder='images/psbuilder.png',
                 TXBuilder='images/txbuilder.png',
                 PXBuilder='images/pxbuilder.png')


class BuildersBase(QtWidgets.QMainWindow):
    """Main base class for pseudosection builders
    """
    def __init__(self, parent=None):
        super(BuildersBase, self).__init__(parent)
        self.setupUi(self)
        res = QtWidgets.QDesktopWidget().screenGeometry()
        self.resize(min(1280, res.width() - 10), min(720, res.height() - 10))
        self.setWindowTitle(self.builder_name)
        window_icon = resource_filename('pypsbuilder', app_icons[self.builder_name])
        self.setWindowIcon(QtGui.QIcon(window_icon))
        self.__changed = False
        self.about_dialog = AboutDialog(self.builder_name, __version__)
        self.unihigh = None
        self.invhigh = None
        self.outhigh = None
        self.presenthigh = None
        self.cid = None

        # Create figure
        self.figure = Figure(facecolor='white')
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setParent(self.tabPlot)
        self.canvas.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.mplvl.addWidget(self.canvas)
        self.toolbar = NavigationToolbar(self.canvas, self.tabPlot,
                                         coordinates=True)
        # remove "Edit curves lines and axes parameters"
        actions = self.toolbar.findChildren(QtWidgets.QAction)
        for a in actions:
            if a.text() == 'Customize':
                self.toolbar.removeAction(a)
                break
        self.mplvl.addWidget(self.toolbar)
        self.canvas.draw()

        # CREATE MODELS
        # Create phasemodel and define some logic
        self.phasemodel = QtGui.QStandardItemModel(self.phaseview)
        self.phaseview.setModel(self.phasemodel)
        self.phaseview.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.phaseview.show()
        # Create outmodel
        self.outmodel = QtGui.QStandardItemModel(self.outview)
        self.outview.setModel(self.outmodel)
        self.outview.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.outview.show()

        # SET PT RANGE VALIDATORS
        validator = QtGui.QDoubleValidator()
        validator.setLocale(QtCore.QLocale.c())
        self.tminEdit.setValidator(validator)
        self.tminEdit.textChanged.connect(self.check_validity)
        self.tminEdit.textChanged.emit(self.tminEdit.text())
        self.tmaxEdit.setValidator(validator)
        self.tmaxEdit.textChanged.connect(self.check_validity)
        self.tmaxEdit.textChanged.emit(self.tmaxEdit.text())
        self.pminEdit.setValidator(validator)
        self.pminEdit.textChanged.connect(self.check_validity)
        self.pminEdit.textChanged.emit(self.pminEdit.text())
        self.pmaxEdit.setValidator(validator)
        self.pmaxEdit.textChanged.connect(self.check_validity)
        self.pmaxEdit.textChanged.emit(self.pmaxEdit.text())

        # SET OUTPUT TEXT FIXED FONTS
        f = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.textOutput.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.textOutput.setReadOnly(True)
        self.textOutput.setFont(f)
        self.textFullOutput.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.textFullOutput.setReadOnly(True)
        self.textFullOutput.setFont(f)
        self.outScript.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.outScript.setFont(f)
        self.logText.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.logText.setReadOnly(True)
        self.logText.setFont(f)
        self.logDogmin.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.logDogmin.setReadOnly(True)
        self.logDogmin.setFont(f)

        self.initViewModels()
        self.common_ui_settings()
        self.builder_ui_settings()

        self.app_settings()
        self.populate_recent()
        self.ready = False
        self.project = None
        self.statusBar().showMessage('PSBuilder version {} (c) Ondrej Lexa 2020'. format(__version__))

    def initViewModels(self):
        # INVVIEW
        self.invmodel = InvModel(self.ps, self.invview)
        self.invview.setModel(self.invmodel)
        # enable sorting
        self.invview.setSortingEnabled(False)
        # hide column
        #self.invview.setColumnHidden(2, True)
        # select rows
        self.invview.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.invview.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.invview.horizontalHeader().setMinimumSectionSize(40)
        self.invview.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.invview.horizontalHeader().hide()
        self.invsel = self.invview.selectionModel()
        # default unconnected ghost
        #self.invmodel.appendRow([0, 'Unconnected', {}])
        #self.invview.setRowHidden(0, True)
        self.invview.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # signals
        self.invsel.selectionChanged.connect(self.sel_changed)

        # UNIVIEW
        self.unimodel = UniModel(self.ps, self.uniview)
        self.uniview.setModel(self.unimodel)
        # enable sorting
        self.uniview.setSortingEnabled(False)
        # hide column
        self.uniview.setColumnHidden(4, True)
        self.uniview.setItemDelegateForColumn(2, ComboDelegate(self.ps, self.invmodel, self.uniview))
        self.uniview.setItemDelegateForColumn(3, ComboDelegate(self.ps, self.invmodel, self.uniview))
        # select rows
        self.uniview.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.uniview.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.uniview.horizontalHeader().setMinimumSectionSize(40)
        self.uniview.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.uniview.horizontalHeader().hide()
        # edit trigger
        self.uniview.setEditTriggers(QtWidgets.QAbstractItemView.CurrentChanged | QtWidgets.QAbstractItemView.SelectedClicked)
        self.uniview.viewport().installEventFilter(self)
        self.uniview.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # signals
        self.unimodel.dataChanged.connect(self.uni_edited)
        self.unisel = self.uniview.selectionModel()
        self.unisel.selectionChanged.connect(self.sel_changed)

        # DOGVIEW
        self.dogmodel = DogminModel(self.ps, self.dogview)
        self.dogview.setModel(self.dogmodel)
        # enable sorting
        self.dogview.setSortingEnabled(False)
        # select rows
        self.dogview.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.dogview.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.dogview.horizontalHeader().setMinimumSectionSize(40)
        self.dogview.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.dogview.horizontalHeader().hide()
        # signals
        self.dogsel = self.dogview.selectionModel()
        self.dogsel.selectionChanged.connect(self.dogmin_changed)

    def common_ui_settings(self):
        # CONNECT SIGNALS
        self.actionNew.triggered.connect(self.initProject)
        self.actionOpen.triggered.connect(self.openProject)
        self.actionSave.triggered.connect(self.saveProject)
        self.actionSave_as.triggered.connect(self.saveProjectAs)
        self.actionQuit.triggered.connect(self.close)
        # self.actionExport_Drawpd.triggered.connect(self.gendrawpd)
        self.actionAbout.triggered.connect(self.about_dialog.exec)
        self.actionImport_project.triggered.connect(self.import_from_prj)
        self.actionShow_areas.triggered.connect(self.check_prj_areas)
        self.actionShow_topology.triggered.connect(self.show_topology)
        self.pushApplySettings.clicked.connect(lambda: self.apply_setting(5))
        self.pushResetSettings.clicked.connect(self.reset_limits)
        self.pushFromAxes.clicked.connect(lambda: self.apply_setting(2))
        self.tabMain.currentChanged.connect(lambda: self.apply_setting(4))
        self.pushReadScript.clicked.connect(self.read_scriptfile)
        self.pushSaveScript.clicked.connect(self.save_scriptfile)
        self.actionReload.triggered.connect(self.reinitialize)
        self.pushGuessUni.clicked.connect(self.unisel_guesses)
        self.pushGuessInv.clicked.connect(self.invsel_guesses)
        self.pushInvAuto.clicked.connect(self.auto_inv_calc)
        self.pushUniSearch.clicked.connect(self.uni_explore)
        self.pushManual.toggled.connect(self.add_userdefined)
        self.pushManual.setCheckable(True)
        self.pushInvRemove.clicked.connect(self.remove_inv)
        self.pushUniRemove.clicked.connect(self.remove_uni)
        self.tabOutput.tabBarDoubleClicked.connect(self.show_output)
        self.splitter_bottom.setSizes((400, 100))
        self.pushDogmin.toggled.connect(self.do_dogmin)
        self.pushDogmin.setCheckable(True)
        #self.pushDogmin_select.clicked.connect(self.dogmin_select_phases)
        self.pushGuessDogmin.clicked.connect(self.dogmin_set_guesses)
        self.pushDogminRemove.clicked.connect(self.remove_dogmin)
        self.phaseview.doubleClicked.connect(self.show_out)
        self.uniview.doubleClicked.connect(self.show_uni)
        self.uniview.clicked.connect(self.uni_activated)
        self.uniview.customContextMenuRequested[QtCore.QPoint].connect(self.univiewRightClicked)
        self.invview.doubleClicked.connect(self.show_inv)
        self.invview.clicked.connect(self.inv_activated)
        self.invview.customContextMenuRequested[QtCore.QPoint].connect(self.invviewRightClicked)
        self.dogview.doubleClicked.connect(self.set_dogmin_phases)
        # additional keyboard shortcuts
        self.scHome = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+H"), self)
        self.scHome.activated.connect(self.toolbar.home)
        self.showAreas = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+A"), self)
        self.showAreas.activated.connect(self.check_prj_areas)

    def reinitialize(self):
        if self.ready:
            # collect info
            phases = []
            for i in range(self.phasemodel.rowCount()):
                item = self.phasemodel.item(i)
                if item.checkState() == QtCore.Qt.Checked:
                    phases.append(item.text())
            out = []
            for i in range(self.outmodel.rowCount()):
                item = self.outmodel.item(i)
                if item.checkState() == QtCore.Qt.Checked:
                    out.append(item.text())
            # reread script file
            tc = TCAPI(self.tc.workdir)
            if tc.OK:
                self.tc = tc
                # select phases
                for i in range(self.phasemodel.rowCount()):
                    item = self.phasemodel.item(i)
                    if item.text() in phases:
                        item.setCheckState(QtCore.Qt.Checked)
                # select out
                for i in range(self.outmodel.rowCount()):
                    item = self.outmodel.item(i)
                    if item.text() in out:
                        item.setCheckState(QtCore.Qt.Checked)
                # update excess changes
                self.ps.excess = self.tc.excess
                self.invview.resizeColumnsToContents()
                self.uniview.resizeColumnsToContents()
                # settings
                self.refresh_gui()
                self.bulk = self.tc.bulk
                self.statusBar().showMessage('Project re-initialized from scriptfile.')
                self.changed = True
            else:
                qb = QtWidgets.QMessageBox
                qb.critical(self, 'Initialization error', tc.status, qb.Abort)
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def populate_recent(self):
        self.menuOpen_recent.clear()
        for f in self.recent:
            self.menuOpen_recent.addAction(Path(f).name, lambda f=f: self.openProject(False, projfile=f))

    def refresh_gui(self):
        # update settings tab
        self.apply_setting(4)
        # read scriptfile
        self.read_scriptfile()
        # update plot
        self.figure.clear()
        self.plot()
        # disconnect signals
        try:
            self.phasemodel.itemChanged.disconnect(self.phase_changed)
        except Exception:
            pass
        self.logText.setPlainText('Working directory:{}\n\n'.format(self.tc.workdir) + self.tc.tcout)
        self.phasemodel.clear()
        self.outmodel.clear()
        for p in self.tc.phases:
            if p not in self.ps.excess:
                item = QtGui.QStandardItem(p)
                item.setCheckable(True)
                item.setSizeHint(QtCore.QSize(40, 20))
                self.phasemodel.appendRow(item)
        # connect signal
        self.phasemodel.itemChanged.connect(self.phase_changed)
        self.textOutput.clear()
        self.textFullOutput.clear()
        self.builder_refresh_gui()
        self.unihigh = None
        self.invhigh = None
        self.outhigh = None
        self.presenthigh = None
        self.statusBar().showMessage('Ready')

    def import_from_prj(self):
        if self.ready:
            qd = QtWidgets.QFileDialog
            projfile = qd.getOpenFileName(self, 'Import from project', str(self.tc.workdir),
                                          self.builder_file_selector)[0]
            if Path(projfile).exists():
                QtWidgets.QApplication.processEvents()
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
                with gzip.open(projfile, 'rb') as stream:
                    data = pickle.load(stream)
                # do import
                self.initViewModels()
                # select phases
                for i in range(self.phasemodel.rowCount()):
                    item = self.phasemodel.item(i)
                    if item.text() in data['selphases']:
                        item.setCheckState(QtCore.Qt.Checked)
                # select out
                for i in range(self.outmodel.rowCount()):
                    item = self.outmodel.item(i)
                    if item.text() in data['out']:
                        item.setCheckState(QtCore.Qt.Checked)
                # Import
                id_lookup = {0:0}
                for row in data['invlist']:
                    inv = InvPoint(phases=row[2]['phases'].union(self.ps.excess),
                                   out=row[2]['out'],
                                   x=row[2]['T'],
                                   y=row[2]['p'],
                                   cmd=row[2].get('cmd', ''),
                                   results=row[2].get('results', [dict(data=None, ptguess=None)]),
                                   manual=True,
                                   output='Imported invariant point.')
                    isnew, id_inv = self.ps.getidinv(inv)
                    id_lookup[row[0]] = id_inv
                    if isnew:
                        self.invmodel.appendRow(id_inv, inv)
                self.invview.resizeColumnsToContents()
                for row in data['unilist']:
                    uni = UniLine(phases=row[4]['phases'].union(self.ps.excess),
                                  out=row[4]['out'],
                                  x=row[4]['T'],
                                  y=row[4]['p'],
                                  cmd=row[4].get('cmd', ''),
                                  results=row[4].get('results', [dict(data=None, ptguess=None)]),
                                  manual=True,
                                  output='Imported univariant line.',
                                  begin=id_lookup[row[2]],
                                  end=id_lookup[row[3]])
                    isnew, id_uni = self.ps.getiduni(uni)
                    if isnew:
                        self.unimodel.appendRow(id_uni, uni)
                self.uniview.resizeColumnsToContents()
                # # try to recalc
                progress = QtWidgets.QProgressDialog("Recalculate inv points", "Cancel",
                                                     0, len(self.ps.invpoints), self)
                progress.setWindowModality(QtCore.Qt.WindowModal)
                progress.setMinimumDuration(0)
                old_guesses = self.tc.update_scriptfile(get_old_guesses=True)
                for ix, inv in enumerate(self.ps.invpoints.values()):
                    progress.setValue(ix)
                    if inv.cmd and inv.output == 'Imported invariant point.':
                        if inv.ptguess():
                            self.tc.update_scriptfile(guesses=inv.ptguess())
                        tcout = self.tc.runtc(inv.cmd)
                        status, variance, pts, res, output = self.tc.parse_logfile()
                        if status == 'ok':
                            self.ps.invpoints[inv.id].variance = variance
                            self.ps.invpoints[inv.id].x = pts[1]
                            self.ps.invpoints[inv.id].y = pts[0]
                            self.ps.invpoints[inv.id].output = output
                            self.ps.invpoints[inv.id].results = res
                            self.ps.invpoints[inv.id].manual = False
                    if progress.wasCanceled():
                        break
                progress.setValue(len(self.ps.invpoints))
                progress.deleteLater()
                self.invview.resizeColumnsToContents()
                progress = QtWidgets.QProgressDialog("Recalculate uni lines", "Cancel",
                                                     0, len(self.ps.unilines), self)
                progress.setWindowModality(QtCore.Qt.WindowModal)
                progress.setMinimumDuration(0)
                for ix, uni in enumerate(self.ps.unilines.values()):
                    progress.setValue(ix)
                    if uni.cmd and uni.output == 'Imported univariant line.':
                        if uni.ptguess():
                            self.tc.update_scriptfile(guesses=uni.ptguess())
                        tcout = self.tc.runtc(uni.cmd)
                        status, variance, pts, res, output = self.tc.parse_logfile()
                        if status == 'ok' and len(res) > 1:
                            self.ps.unilines[uni.id].variance = variance
                            self.ps.unilines[uni.id]._x = pts[1]
                            self.ps.unilines[uni.id]._y = pts[0]
                            self.ps.unilines[uni.id].output = output
                            self.ps.unilines[uni.id].results = res
                            self.ps.unilines[uni.id].manual = False
                            self.ps.trim_uni(uni.id)
                    if progress.wasCanceled():
                        break
                progress.setValue(len(self.ps.unilines))
                progress.deleteLater()
                self.uniview.resizeColumnsToContents()
                self.tc.update_scriptfile(guesses=old_guesses)
                # all done
                self.changed = True
                self.app_settings(write=True)
                # read scriptfile
                self.read_scriptfile()
                # update settings tab
                self.apply_setting(4)
                # update plot
                self.figure.clear()
                self.plot()
                self.statusBar().showMessage('Project Imported.')
                QtWidgets.QApplication.restoreOverrideCursor()
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def saveProject(self):
        """Open working directory and initialize project
        """
        if self.ready:
            if self.project is None:
                filename = QtWidgets.QFileDialog.getSaveFileName(self, 'Save current project', str(self.tc.workdir), self.builder_file_selector)[0]
                if filename:
                    if not filename.lower().endswith(self.builder_extension):
                        filename = filename + self.builder_extension
                    self.project = filename
                    self.do_save()
            else:
                self.do_save()
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def saveProjectAs(self):
        """Open working directory and initialize project
        """
        if self.ready:
            filename = QtWidgets.QFileDialog.getSaveFileName(self, 'Save current project as', str(self.tc.workdir), self.builder_file_selector)[0]
            if filename:
                if not filename.lower().endswith(self.builder_extension):
                    filename = filename + self.builder_extension
                self.project = filename
                self.do_save()
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def do_save(self):
        """Open working directory and initialize project
        """
        if self.project is not None:
            # do save
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            with gzip.open(self.project, 'wb') as stream:
                pickle.dump(self.data, stream)
            self.changed = False
            if self.project in self.recent:
                self.recent.pop(self.recent.index(self.project))
            self.recent.insert(0, self.project)
            if len(self.recent) > 15:
                self.recent = self.recent[:15]
            self.populate_recent()
            self.app_settings(write=True)
            self.statusBar().showMessage('Project saved.')
            QtWidgets.QApplication.restoreOverrideCursor()

    @property
    def data(self):
        # collect info
        selphases = []
        for i in range(self.phasemodel.rowCount()):
            item = self.phasemodel.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                selphases.append(item.text())
        out = []
        for i in range(self.outmodel.rowCount()):
            item = self.outmodel.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                out.append(item.text())
        # put to dict
        data = {'selphases': selphases,
                'out': out,
                'section': self.ps,
                'tcversion': self.tc.tcversion,
                'workdir': self.tc.workdir,
                'bulk': self.bulk,
                'datetime': datetime.now(),
                'version': __version__}
        return data

    @property
    def builder_file_selector(self):
        return '{} project (*{})'.format(self.builder_name, self.builder_extension)

    @property
    def changed(self):
        return self.__changed

    @changed.setter
    def changed(self, status):
        self.__changed = status
        if self.project is None:
            title = '{} - New project - {}'.format(self.builder_name, self.tc.tcversion)
        else:
            title = '{} - {} - {}'.format(self.builder_name, Path(self.project).name, self.tc.tcversion)
        if status:
            title += '*'
        self.setWindowTitle(title)

    def format_coord(self, x, y):
        prec = self.spinPrec.value()
        if hasattr(self.ax, 'areas_shown'):
            point = Point(x, y)
            phases = ''
            for key in self.ax.areas_shown:
                if self.ax.areas_shown[key].contains(point):
                    phases = ' '.join(key.difference(self.ps.excess))
                    break
            return '{} {}={:.{prec}f} {}={:.{prec}f}'.format(phases, self.ps.x_var, x, self.ps.y_var, y, prec=prec)
        else:
            return '{}={:.{prec}f} {}={:.{prec}f}'.format(self.ps.x_var, x, self.ps.y_var, y, prec=prec)

    def show_output(self, int):
        if self.ready:
            if int == 0:
                dia = OutputDialog('Modes', self.textOutput.toPlainText())
                dia.exec()
            if int == 1:
                dia = OutputDialog('TC output', self.textFullOutput.toPlainText())
                dia.exec()

    def clean_high(self):
        if self.unihigh is not None:
            try:
                self.unihigh[0].remove()
            except:
                pass
            self.unihigh = None
            self.textOutput.clear()
            self.textFullOutput.clear()
        if self.invhigh is not None:
            try:
                self.invhigh[0].remove()
            except:
                pass
            self.invhigh = None
            self.textOutput.clear()
            self.textFullOutput.clear()
        if self.outhigh is not None:
            try:
                self.outhigh[0].remove()
            except:
                pass
            self.outhigh = None
        if self.presenthigh is not None:
            try:
                self.presenthigh[0].remove()
            except:
                pass
            self.presenthigh = None
        self.canvas.draw()

    def sel_changed(self):
        self.clean_high()

    def dogmin_changed(self):
        if self.dogsel.hasSelection():
            idx = self.dogsel.selectedIndexes()
            dgm = self.ps.dogmins[self.dogmodel.data(idx[0])]
            self.textOutput.setPlainText(dgm.output)
            self.textFullOutput.setPlainText(dgm.resic)
            self.logDogmin.setPlainText(dgm.output + dgm.resic)

    def invsel_guesses(self):
        if self.invsel.hasSelection():
            idx = self.invsel.selectedIndexes()
            inv = self.ps.invpoints[self.invmodel.data(idx[0])]
            if not inv.manual:
                self.tc.update_scriptfile(guesses=inv.ptguess())
                self.read_scriptfile()
                self.statusBar().showMessage('Invariant point ptuess set.')
            else:
                self.statusBar().showMessage('Guesses cannot be set from user-defined invariant point.')

    def unisel_guesses(self):
        if self.unisel.hasSelection():
            idx = self.unisel.selectedIndexes()
            uni = self.ps.unilines[self.unimodel.data(idx[0])]
            if not uni.manual:
                lbl = [self.format_coord(x, y) for x, y in zip(uni._x, uni._y)]
                uniguess = UniGuess(lbl, self)
                respond = uniguess.exec()
                if respond == QtWidgets.QDialog.Accepted:
                    ix = uniguess.getValue()
                    self.tc.update_scriptfile(guesses=uni.ptguess(idx=ix))
                    self.read_scriptfile()
                    self.statusBar().showMessage('Univariant line ptguess set for {}'.format(self.format_coord(uni._x[ix], uni._y[ix])))
            else:
                self.statusBar().showMessage('Guesses cannot be set from user-defined univariant line.')

    def dogmin_set_guesses(self):
        if self.dogsel.hasSelection():
            idx = self.dogsel.selectedIndexes()
            dgm = self.ps.dogmins[self.dogmodel.data(idx[0])]
            self.tc.update_scriptfile(guesses=dgm.ptguess())
            self.read_scriptfile()
            self.statusBar().showMessage('Dogmin ptuess set.')

    def get_phases_out(self):
        phases = []
        for i in range(self.phasemodel.rowCount()):
                item = self.phasemodel.item(i)
                if item.checkState() == QtCore.Qt.Checked:
                    phases.append(item.text())
        out = []
        for i in range(self.outmodel.rowCount()):
            item = self.outmodel.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                out.append(item.text())
        return set(phases).union(self.ps.excess), set(out)

    def set_phaselist(self, r, show_output=True):
        for i in range(self.phasemodel.rowCount()):
            item = self.phasemodel.item(i)
            if item.text() in r.phases:   # or item.text() in r.out:
                item.setCheckState(QtCore.Qt.Checked)
            else:
                item.setCheckState(QtCore.Qt.Unchecked)
        # select out
        for i in range(self.outmodel.rowCount()):
            item = self.outmodel.item(i)
            if item.text() in r.out:
                item.setCheckState(QtCore.Qt.Checked)
            else:
                item.setCheckState(QtCore.Qt.Unchecked)
        if show_output:
            if not r.manual:
                txt = ''
                mlabels = sorted(list(r.phases.difference(self.ps.excess)))
                h_format = '{:>10}{:>10}' + '{:>8}' * len(mlabels)
                n_format = '{:10.4f}{:10.4f}' + '{:8.5f}' * len(mlabels)
                txt += h_format.format(self.ps.x_var, self.ps.y_var, *mlabels)
                txt += '\n'
                nln = 0
                if isinstance(r, UniLine):
                    if r.begin > 0 and not self.ps.invpoints[r.begin].manual:
                        x, y = self.ps.invpoints[r.begin]._x, self.ps.invpoints[r.begin]._y
                        res = self.ps.invpoints[r.begin].results[0]
                        row = [x, y] + [res['data'][lbl]['mode'] for lbl in mlabels]
                        txt += n_format.format(*row)
                        txt += '\n'
                        nln += 1
                    for x, y, res in zip(r._x[r.used], r._y[r.used], r.results[r.used]):
                        row = [x, y] + [res['data'][lbl]['mode'] for lbl in mlabels]
                        txt += n_format.format(*row)
                        txt += '\n'
                    if r.end > 0 and not self.ps.invpoints[r.end].manual:
                        x, y = self.ps.invpoints[r.end]._x, self.ps.invpoints[r.end]._y
                        res = self.ps.invpoints[r.end].results[0]
                        row = [x, y] + [res['data'][lbl]['mode'] for lbl in mlabels]
                        txt += n_format.format(*row)
                        txt += '\n'
                        nln += 1
                    if len(r.results[r.used]) > (5 - nln):
                        txt += h_format.format(self.ps.x_var, self.ps.y_var, *mlabels)
                else:
                    for x, y, res in zip(r.x, r.y, r.results):
                        row = [x, y] + [res['data'][lbl]['mode'] for lbl in mlabels]
                        txt += n_format.format(*row)
                        txt += '\n'
                self.textOutput.setPlainText(txt)
            else:
                self.textOutput.setPlainText(r.output)
            self.textFullOutput.setPlainText(r.output)

    def show_uni(self, index):
        uni = self.ps.unilines[self.unimodel.getRowID(index)]
        self.clean_high()
        self.set_phaselist(uni, show_output=True)
        self.unihigh = self.ax.plot(uni.x, uni.y, '-', **unihigh_kw)
        self.canvas.draw()

    def set_dogmin_phases(self, index):
        dgm = self.ps.dogmins[self.dogmodel.getRowID(index)]
        self.set_phaselist(dgm, show_output=False)

    def uni_activated(self, index):
        self.invsel.clearSelection()

    def uni_edited(self, index):
        self.ps.trim_uni(self.unimodel.getRowID(index))
        self.changed = True
        # update plot
        self.plot()

    def show_inv(self, index):
        inv = self.ps.invpoints[self.invmodel.getRowID(index)]
        self.clean_high()
        self.set_phaselist(inv, show_output=True)
        self.invhigh = self.ax.plot(inv.x, inv.y, 'o', **invhigh_kw)
        self.canvas.draw()

    def inv_activated(self, index):
        self.unisel.clearSelection()

    def show_out(self, index):
        out = self.phasemodel.itemFromIndex(index).text()
        self.clean_high()
        ox, oy = [], []
        px, py = [], []
        for uni in self.ps.unilines.values():
            not_out = True
            if out in uni.out:
                ox.append(uni.x)
                ox.append([np.nan])
                oy.append(uni.y)
                oy.append([np.nan])
                not_out = False
            for poly in polymorphs:
                if poly.issubset(uni.phases):
                    if out in poly:
                        if poly.difference({out}).issubset(uni.out):
                            ox.append(uni.x)
                            ox.append([np.nan])
                            oy.append(uni.y)
                            oy.append([np.nan])
                            not_out = False
            if not_out and (out in uni.phases):
                px.append(uni.x)
                px.append([np.nan])
                py.append(uni.y)
                py.append([np.nan])
        if ox:
            self.outhigh = self.ax.plot(np.concatenate(ox), np.concatenate(oy),
                                        '-', **outhigh_kw)
        if px:
            self.presenthigh = self.ax.plot(np.concatenate(px), np.concatenate(py),
                                            '-', **presenthigh_kw)
        self.canvas.draw()

    def invviewRightClicked(self, QPos):
        if self.invsel.hasSelection():
            idx = self.invsel.selectedIndexes()
            inv = self.ps.invpoints[self.invmodel.getRowID(idx[0])]
            all_uni = inv.all_unilines()
            show_menu = False
            menu = QtWidgets.QMenu(self.uniview)
            u1 = UniLine(phases=all_uni[0][0], out=all_uni[0][1])
            isnew, id = self.ps.getiduni(u1)
            if isnew:
                menu_item1 = menu.addAction(u1.label(excess=self.ps.excess))
                menu_item1.triggered.connect(lambda: self.set_phaselist(u1, show_output=False))
                show_menu = True
            u2 = UniLine(phases=all_uni[1][0], out=all_uni[1][1])
            isnew, id = self.ps.getiduni(u2)
            if isnew:
                menu_item2 = menu.addAction(u2.label(excess=self.ps.excess))
                menu_item2.triggered.connect(lambda: self.set_phaselist(u2, show_output=False))
                show_menu = True
            u3 = UniLine(phases=all_uni[2][0], out=all_uni[2][1])
            isnew, id = self.ps.getiduni(u3)
            if isnew:
                menu_item1 = menu.addAction(u3.label(excess=self.ps.excess))
                menu_item1.triggered.connect(lambda: self.set_phaselist(u3, show_output=False))
                show_menu = True
            u4 = UniLine(phases=all_uni[3][0], out=all_uni[3][1])
            isnew, id = self.ps.getiduni(u4)
            if isnew:
                menu_item1 = menu.addAction(u4.label(excess=self.ps.excess))
                menu_item1.triggered.connect(lambda: self.set_phaselist(u4, show_output=False))
                show_menu = True
            if show_menu:
                menu.exec(self.invview.mapToGlobal(QPos))

    def univiewRightClicked(self, QPos):
        if self.unisel.hasSelection():
            idx = self.unisel.selectedIndexes()
            id = self.unimodel.getRowID(idx[0])
            uni = self.ps.unilines[id]
            menu = QtWidgets.QMenu(self)
            menu_item1 = menu.addAction('Zoom')
            menu_item1.triggered.connect(lambda: self.zoom_to_uni(uni))
            miss = uni.begin == 0 or uni.end == 0
            if miss:
                candidates = [inv for inv in self.ps.invpoints.values() if uni.contains_inv(inv)]
                if len(candidates) == 2:
                    menu_item2 = menu.addAction('Autoconnect')
                    menu_item2.triggered.connect(lambda: self.uni_connect(id, candidates, plot=True))
            menu.exec(self.uniview.mapToGlobal(QPos))

    def uni_connect(self, id, candidates, plot=False):
        self.ps.unilines[id].begin = candidates[0].id
        self.ps.unilines[id].end = candidates[1].id
        self.ps.trim_uni(id)
        self.changed = True
        if plot:
            self.plot()

    def auto_add_uni(self, phases, out):
        uni = UniLine(phases=phases, out=out)
        isnew, id = self.ps.getiduni(uni)
        if isnew:
            self.do_calc(True, phases=uni.phases, out=uni.out)
        isnew, id = self.ps.getiduni(uni)
        if isnew:
            self.do_calc(False, phases=uni.phases, out=uni.out)

    def auto_inv_calc(self):
        if self.invsel.hasSelection():
            idx = self.invsel.selectedIndexes()
            inv = self.ps.invpoints[self.invmodel.getRowID(idx[0])]
            self.statusBar().showMessage('Running auto univariant lines calculations...')
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            self.tc.update_scriptfile(guesses=inv.ptguess())
            for phases, out in inv.all_unilines():
                self.auto_add_uni(phases, out)

            self.read_scriptfile()
            self.clean_high()
            QtWidgets.QApplication.restoreOverrideCursor()
            self.statusBar().showMessage('Auto calculations done.')

    def zoom_to_uni(self, uni):
        self.canvas.toolbar.push_current()
        dT = max((uni.x.max() - uni.x.min()) / 10, self.ps.x_var_res)
        dp = max((uni.y.max() - uni.y.min()) / 10, self.ps.y_var_res)
        self.ax.set_xlim([uni.x.min() - dT, uni.x.max() + dT])
        self.ax.set_ylim([uni.y.min() - dp, uni.y.max() + dp])
        self.canvas.toolbar.push_current()
        self.canvas.draw()

    def remove_inv(self):
        if self.invsel.hasSelection():
            idx = self.invsel.selectedIndexes()
            inv_id = self.invmodel.data(idx[0])
            todel = True
            # Check ability to delete
            for uni in self.ps.unilines.values():
                if uni.begin == inv_id or uni.end == inv_id:
                    if uni.manual:
                        todel = False
            if todel:
                msg = '{}\nAre you sure?'.format(self.invmodel.data(idx[1]))
                qb = QtWidgets.QMessageBox
                reply = qb.question(self, 'Remove invariant point',
                                    msg, qb.Yes, qb.No)
                if reply == qb.Yes:

                    # Check unilines begins and ends
                    for uni in self.ps.unilines.values():
                        if uni.begin == inv_id:
                            uni.begin = 0
                            self.ps.trim_uni(uni.id)
                        if uni.end == inv_id:
                            uni.end = 0
                            self.ps.trim_uni(uni.id)
                    self.invmodel.removeRow(idx[0])
                    self.changed = True
                    self.plot()
                    self.statusBar().showMessage('Invariant point removed')
            else:
                self.statusBar().showMessage('Cannot delete invariant point, which define user-defined univariant line.')

    def remove_uni(self):
        if self.unisel.hasSelection():
            idx = self.unisel.selectedIndexes()
            msg = '{}\nAre you sure?'.format(self.unimodel.data(idx[1]))
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Remove univariant line',
                                msg, qb.Yes, qb.No)
            if reply == qb.Yes:
                self.unimodel.removeRow(idx[0])
                self.changed = True
                self.plot()
                self.statusBar().showMessage('Univariant line removed')

    def remove_dogmin(self):
        if self.dogsel.hasSelection():
            idx = self.dogsel.selectedIndexes()
            msg = '{}\nAre you sure?'.format(self.dogmodel.data(idx[1]))
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Remove dogmin result',
                                msg, qb.Yes, qb.No)
            if reply == qb.Yes:
                self.dogmodel.removeRow(idx[0])
                self.changed = True
                self.plot()
                self.statusBar().showMessage('Dogmin result removed')

    def add_userdefined(self, checked=True):
        if self.ready:
            phases, out = self.get_phases_out()
            if len(out) == 1:
                if checked:
                    uni = UniLine(phases=phases, out=out, x=np.array([]), y=np.array([]),
                                  manual=True, output='User-defined univariant line.')
                    isnew, id_uni = self.ps.getiduni(uni)
                    uni.id = id_uni
                    candidates = [inv for inv in self.ps.invpoints.values() if uni.contains_inv(inv)]
                    if len(candidates) == 2:
                        if isnew:
                            self.unimodel.appendRow(id_uni, uni)
                            self.uni_connect(id_uni, candidates)
                            self.changed = True
                            # self.unisel.select(idx, QtCore.QItemSelectionModel.ClearAndSelect | QtCore.QItemSelectionModel.Rows)
                            idx = self.unimodel.getIndexID(id_uni)
                            self.uniview.selectRow(idx.row())
                            self.uniview.scrollToBottom()
                            self.statusBar().showMessage('User-defined univariant line added.')
                        else:
                            self.ps.unilines[id_uni] = uni
                            self.uni_connect(id_uni, candidates)
                            idx = self.unimodel.getIndexID(id_uni)
                            self.uniview.selectRow(idx.row())
                            self.statusBar().showMessage('Existing univariant line changed to user-defined one.')
                        self.uniview.resizeColumnsToContents()
                        self.changed = True
                        self.plot()
                        self.show_uni(idx)
                    else:
                        self.statusBar().showMessage('No invariant points calculated for selected univariant line.')
                    self.pushManual.setChecked(False)
            elif len(out) == 2:
                if checked:
                    phases, out = self.get_phases_out()
                    inv = InvPoint(phases=phases, out=out, manual=True,
                                   output='User-defined invariant point.')
                    unis = [uni for uni in self.ps.unilines.values() if uni.contains_inv(inv)]
                    done = False
                    if len(unis) > 1:
                        xx, yy = [], []
                        for uni1, uni2 in itertools.combinations(unis, 2):
                            x, y = intersection(uni1, uni2, ratio=self.ps.ratio, extra=0.2, N=100)
                            if len(x) > 0:
                                xx.append(x[0])
                                yy.append(y[0])
                        if len(xx) > 0:
                            x = np.atleast_1d(np.mean(xx))
                            y = np.atleast_1d(np.mean(yy))
                            msg = 'Found intersection of {} unilines.\n Do you want to use it?'.format(len(unis))
                            qb = QtWidgets.QMessageBox
                            reply = qb.question(self, 'Add manual invariant point',
                                                msg, qb.Yes, qb.No)
                            if reply == qb.Yes:
                                isnew, id_inv = self.ps.getidinv(inv)
                                inv.id = id_inv
                                inv.x, inv.y = x, y
                                if isnew:
                                    self.invmodel.appendRow(id_inv, inv)
                                    idx = self.invmodel.getIndexID(id_inv)
                                    self.invview.selectRow(idx.row())
                                    self.invview.scrollToBottom()
                                    if self.checkAutoconnectInv.isChecked():
                                        for uni in self.ps.unilines.values():
                                            if uni.contains_inv(inv):
                                                candidates = [inv]
                                                for other_inv in self.ps.invpoints.values():
                                                    if other_inv.id != id_inv:
                                                        if uni.contains_inv(other_inv):
                                                            candidates.append(other_inv)
                                                if len(candidates) == 2:
                                                    self.uni_connect(uni.id, candidates)
                                                    self.uniview.resizeColumnsToContents()
                                else:
                                    self.ps.invpoints[id_inv] = inv
                                    for uni in self.ps.unilines.values():
                                        if uni.begin == id_inv or uni.end == id_inv:
                                            self.ps.trim_uni(uni.id)
                                self.invview.resizeColumnsToContents()
                                self.changed = True
                                self.plot()
                                idx = self.invmodel.getIndexID(id_inv)
                                self.show_inv(idx)
                                self.statusBar().showMessage('User-defined invariant point added.')
                                self.pushManual.setChecked(False)
                                done = True
                    if not done:
                        # cancle zoom and pan action on toolbar
                        if self.toolbar._active == "PAN":
                            self.toolbar.pan()
                        elif self.toolbar._active == "ZOOM":
                            self.toolbar.zoom()
                        self.cid = Cursor(self.ax, useblit=False, color='red', linewidth=1)
                        self.cid.connect_event('button_press_event', self.clicker)
                        self.tabMain.setCurrentIndex(0)
                        self.statusBar().showMessage('Click on canvas to add invariant point.')
                else:
                    if self.cid is not None:
                        self.canvas.mpl_disconnect(self.cid)
                        self.statusBar().showMessage('')
                        self.cid.disconnect_events()
                        self.cid = None
            else:
                self.statusBar().showMessage('Select exactly one out phase for univariant line or two phases for invariant point.')
                self.pushManual.setChecked(False)
        else:
            self.statusBar().showMessage('Project is not yet initialized.')
            self.pushManual.setChecked(False)

    def clicker(self, event):
        self.cid.onmove(event)
        if event.inaxes is not None:
            self.cid.clear(event)
            phases, out = self.get_phases_out()
            inv = InvPoint(phases=phases, out=out, manual=True,
                           output='User-defined invariant point.')
            isnew, id_inv = self.ps.getidinv(inv)
            addinv = AddInv(self.ps, inv, parent=self)
            addinv.set_from_event(event)
            respond = addinv.exec()
            if respond == QtWidgets.QDialog.Accepted:
                inv.id = id_inv
                inv.x, inv.y = addinv.getValues()
                if isnew:
                    self.invmodel.appendRow(id_inv, inv)
                    idx = self.invmodel.getIndexID(id_inv)
                    self.invview.selectRow(idx.row())
                    self.invview.scrollToBottom()
                    if self.checkAutoconnectInv.isChecked():
                        for uni in self.ps.unilines.values():
                            if uni.contains_inv(inv):
                                candidates = [inv]
                                for other_inv in self.ps.invpoints.values():
                                    if other_inv.id != id_inv:
                                        if uni.contains_inv(other_inv):
                                            candidates.append(other_inv)
                                if len(candidates) == 2:
                                    self.uni_connect(uni.id, candidates)
                                    self.uniview.resizeColumnsToContents()
                else:
                    self.ps.invpoints[id_inv] = inv
                    for uni in self.ps.unilines.values():
                        if uni.begin == id_inv or uni.end == id_inv:
                            self.ps.trim_uni(uni.id)
                self.invview.resizeColumnsToContents()
                self.changed = True
                self.plot()
                idx = self.invmodel.getIndexID(id_inv)
                self.show_inv(idx)
                self.statusBar().showMessage('User-defined invariant point added.')
            self.pushManual.setChecked(False)

    def read_scriptfile(self):
        if self.ready:
            with self.tc.scriptfile.open('r', encoding=self.tc.TCenc) as f:
                self.outScript.setPlainText(f.read())
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def save_scriptfile(self):
        if self.ready:
            with self.tc.scriptfile.open('w', encoding=self.tc.TCenc) as f:
                f.write(self.outScript.toPlainText())
            self.reinitialize()
            self.apply_setting(1)
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def closeEvent(self, event):
        """Catch exit of app.
        """
        if self.changed:
            quit_msg = 'Project have been changed. Save ?'
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Message', quit_msg,
                                qb.Cancel | qb.Discard | qb.Save, qb.Save)

            if reply == qb.Save:
                self.do_save()
                if self.project is not None:
                    self.app_settings(write=True)
                    event.accept()
                else:
                    event.ignore()
            elif reply == qb.Discard:
                event.accept()
            else:
                event.ignore()

    def check_validity(self, *args, **kwargs):
        sender = self.sender()
        validator = sender.validator()
        state = validator.validate(sender.text(), 0)[0]
        if state == QtGui.QValidator.Acceptable:
            color = '#c4df9b'  # green
        elif state == QtGui.QValidator.Intermediate:
            color = '#fff79a'  # yellow
        else:
            color = '#f6989d'  # red
        sender.setStyleSheet('QLineEdit { background-color: %s }' % color)

    def apply_setting(self, bitopt=0):
        """Apply settings
        0 bit from text to app and plot (1)
        1 bit from axes to text         (2)
        2 bit from app to text          (4)
        3 bit from default to text      (8)
        """
        # app settings
        if (1 << 0) & bitopt:
            self.app_settings(write=True)
        if (1 << 2) & bitopt:
            self.app_settings()
        # proj settings
        if self.ready:
            fmt = lambda x: '{:.{prec}f}'.format(x, prec=self.spinPrec.value())
            if (1 << 0) & bitopt:
                if (float(self.tminEdit.text()), float(self.tmaxEdit.text())) != self.ps.xrange:
                    self.ps.xrange = (float(self.tminEdit.text()),
                                       float(self.tmaxEdit.text()))
                    self.changed = True
                if (float(self.pminEdit.text()), float(self.pmaxEdit.text())) != self.ps.yrange:
                    self.ps.yrange = (float(self.pminEdit.text()),
                                       float(self.pmaxEdit.text()))
                    self.changed = True
                self.ax.set_xlim(self.ps.xrange)
                self.ax.set_ylim(self.ps.yrange)
                # clear navigation toolbar history
                self.toolbar.update()
                self.statusBar().showMessage('Settings applied.')
                self.figure.clear()
                self.plot()
            if (1 << 1) & bitopt:
                self.tminEdit.setText(fmt(self.ax.get_xlim()[0]))
                self.tmaxEdit.setText(fmt(self.ax.get_xlim()[1]))
                self.pminEdit.setText(fmt(self.ax.get_ylim()[0]))
                self.pmaxEdit.setText(fmt(self.ax.get_ylim()[1]))
            if (1 << 2) & bitopt:
                self.tminEdit.setText(fmt(self.ps.xrange[0]))
                self.tmaxEdit.setText(fmt(self.ps.xrange[1]))
                self.pminEdit.setText(fmt(self.ps.yrange[0]))
                self.pmaxEdit.setText(fmt(self.ps.yrange[1]))
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def phase_changed(self, item):
        """Manage phases in outmodel based on selection in phase model.
        """
        if item.checkState():
            outitem = item.clone()
            outitem.setCheckState(QtCore.Qt.Unchecked)
            self.outmodel.appendRow(outitem)
            self.outmodel.sort(0, QtCore.Qt.AscendingOrder)
        else:
            for it in self.outmodel.findItems(item.text()):
                self.outmodel.removeRow(it.row())

    def do_dogmin(self, checked=True):
        if self.ready:
            if checked:
                phases, out = self.get_phases_out()
                which = phases.difference(self.ps.excess)
                if which:
                    # cancle zoom and pan action on toolbar
                    if self.toolbar._active == "PAN":
                        self.toolbar.pan()
                    elif self.toolbar._active == "ZOOM":
                        self.toolbar.zoom()
                    self.cid = Cursor(self.ax, useblit=False, color='red', linewidth=1)
                    self.cid.connect_event('button_press_event', self.dogminer)
                    self.tabMain.setCurrentIndex(0)
                    self.statusBar().showMessage('Click on canvas to run dogmin at this point.')
                    self.pushManual.toggled.disconnect()
                    self.pushManual.setCheckable(False)
                else:
                    self.statusBar().showMessage('You need to select phases to consider for dogmin.')
            else:
                self.tc.update_scriptfile(dogmin='no')
                self.read_scriptfile()
                QtWidgets.QApplication.restoreOverrideCursor()
                self.statusBar().showMessage('')
                self.pushManual.toggled.connect(self.add_userdefined)
                self.pushManual.setCheckable(True)
                self.cid.disconnect_events()
                self.cid = None
        else:
            self.statusBar().showMessage('Project is not yet initialized.')
            self.pushDogmin.setChecked(False)

    def dogmin_select_phases(self):
        if self.ready:
            dgtxt = self.logDogmin.toPlainText()
            try:
                phases = set(dgtxt.split('phases: ')[1].split(' (')[0].split())
                tmp = InvPoint(phases=phases, out=set(), output='User-defined')
                self.set_phaselist(tmp, show_output=False)
            except:
                self.statusBar().showMessage('You need to run dogmin first.')
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def dogmin_set_guesses(self):
        if self.ready:
            dgtxt = self.logDogmin.toPlainText()
            try:
                block = [ln for ln in dgtxt.splitlines() if ln != '']
                xyz = [ix for ix, ln in enumerate(block) if ln.startswith('xyzguess')]
                gixs = [ix for ix, ln in enumerate(block) if ln.startswith('ptguess')][0] - 1
                gixe = xyz[-1] + 2
                ptguess = block[gixs:gixe]
                self.tc.update_scriptfile(guesses=ptguess)
                self.read_scriptfile()
                self.statusBar().showMessage('Dogmin ptuess set.')
            except:
                self.statusBar().showMessage('You need to run dogmin first.')
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def plot(self):
        if self.ready:
            lalfa = self.spinAlpha.value() / 100
            fsize = self.spinFontsize.value()
            unilabel_kw = dict(ha='center', va='center', size=fsize,
                               bbox=dict(boxstyle="round,pad=0.2", fc='cyan', alpha=lalfa, pad=2))
            invlabel_kw = dict(ha='center', va='center', size=fsize,
                               bbox=dict(boxstyle="round,pad=0.2", fc='yellow', alpha=lalfa, pad=2))
            doglabel_kw = dict(ha='center', va='center', size=fsize,
                               bbox=dict(boxstyle="round,pad=0.2", fc='sandybrown', alpha=lalfa, pad=2))
            axs = self.figure.get_axes()
            if axs:
                self.ax = axs[0]
                cur = (self.ax.get_xlim(), self.ax.get_ylim())
            else:
                cur = None
                self.ax = self.figure.add_subplot(111)
            self.ax.cla()
            self.ax.format_coord = self.format_coord
            for uni in self.ps.unilines.values():
                self.ax.plot(uni.x, uni.y, 'k')
                if self.checkLabelUni.isChecked():
                    xl, yl = uni.get_label_point()
                    self.ax.annotate(s=uni.annotation(self.checkLabelUniText.isChecked()), xy=(xl, yl), **unilabel_kw)
            for inv in self.ps.invpoints.values():
                if self.checkLabelInv.isChecked():
                    self.ax.annotate(s=inv.annotation(self.checkLabelInvText.isChecked()), xy=(inv.x, inv.y), **invlabel_kw)
                else:
                    if self.checkDotInv.isChecked():
                        self.ax.plot(inv.x, inv.y, 'k.')
            if self.checkLabelDog.isChecked():
                for dgm in self.ps.dogmins.values():
                    self.ax.annotate(s=dgm.annotation(self.checkLabelDogText.isChecked(), self.ps.excess), xy=(dgm.x, dgm.y), **doglabel_kw)
            self.ax.set_xlabel(self.ps.x_var_label)
            self.ax.set_ylabel(self.ps.y_var_label)
            self.ax.set_title(self.plot_title)
            if cur is None:
                self.ax.set_xlim(self.ps.xrange)
                self.ax.set_ylim(self.ps.yrange)
            else:
                self.ax.set_xlim(cur[0])
                self.ax.set_ylim(cur[1])
            if self.unihigh is not None and self.unisel.hasSelection():
                idx = self.unisel.selectedIndexes()
                uni = self.ps.unilines[self.unimodel.getRowID(idx[0])]
                self.unihigh = self.ax.plot(uni.x, uni.y, '-', **unihigh_kw)
            if self.invhigh is not None and self.invsel.hasSelection():
                idx = self.invsel.selectedIndexes()
                inv = self.ps.invpoints[self.invmodel.getRowID(idx[0])]
                self.invhigh = self.ax.plot(inv.x, inv.y, 'o', **invhigh_kw)
            self.canvas.draw()

    def check_prj_areas(self):
        if self.ready:
            if not hasattr(self.ax, 'areas_shown'):
                QtWidgets.QApplication.processEvents()
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
                shapes, shape_edges, bad_shapes, ignored_shapes, log = self.ps.create_shapes()
                if log:
                    self.textOutput.setPlainText('\n'.join(log))
                if shapes:
                    vari = [-len(key) for key in shapes]
                    poc = max(vari) - min(vari) + 1
                    pscolors = cm.get_cmap('cool')(np.linspace(0, 1, poc))
                    # Set alpha
                    pscolors[:, -1] = 0.6 # alpha
                    pscmap = ListedColormap(pscolors)
                    norm = BoundaryNorm(np.arange(min(vari) - 0.5, max(vari) + 1.5), poc, clip=True)
                    for key in shapes:
                        self.ax.add_patch(PolygonPatch(shapes[key], fc=pscmap(norm(-len(key))), ec='none'))
                    self.ax.areas_shown = shapes
                    self.canvas.draw()
                else:
                    self.statusBar().showMessage('No areas created.')
                QtWidgets.QApplication.restoreOverrideCursor()
            else:
                self.textOutput.clear()
                self.figure.clear()
                self.plot()
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def show_topology(self):
        if self.ready:
            if NX_OK:
                dia = TopologyGraph(self.ps)
                dia.exec_()
            else:
                self.statusBar().showMessage('Topology graph needs networkx to be installed')
        else:
            self.statusBar().showMessage('Project is not yet initialized.')


class PSBuilder(BuildersBase, Ui_PSBuilder):
    """Main class for psbuilder
    """
    def __init__(self, parent=None):
        self.builder_name = 'PSBuilder'
        self.builder_extension = '.psb'
        self.ps = PTsection()
        super(PSBuilder, self).__init__(parent)

    def builder_ui_settings(self):
        # CONNECT SIGNALS
        self.pushCalcTatP.clicked.connect(lambda: self.do_calc(True))
        self.pushCalcPatT.clicked.connect(lambda: self.do_calc(False))
        self.actionImport_drfile.triggered.connect(self.import_drfile)
        # additional keyboard shortcuts
        self.scCalcTatP = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+T"), self)
        self.scCalcTatP.activated.connect(lambda: self.do_calc(True))
        self.scCalcPatT = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+P"), self)
        self.scCalcPatT.activated.connect(lambda: self.do_calc(False))

    def app_settings(self, write=False):
        # Applicatiom settings
        builder_settings = QtCore.QSettings('LX', 'psbuilder')
        if write:
            builder_settings.setValue("steps", self.spinSteps.value())
            builder_settings.setValue("precision", self.spinPrec.value())
            builder_settings.setValue("extend_range", self.spinOver.value())
            builder_settings.setValue("dogmin_level", self.spinDoglevel.value())
            builder_settings.setValue("label_uni", self.checkLabelUni.checkState())
            builder_settings.setValue("label_uni_text", self.checkLabelUniText.checkState())
            builder_settings.setValue("label_inv", self.checkLabelInv.checkState())
            builder_settings.setValue("label_inv_text", self.checkLabelInvText.checkState())
            builder_settings.setValue("label_dog", self.checkLabelDog.checkState())
            builder_settings.setValue("label_dog_text", self.checkLabelDogText.checkState())
            builder_settings.setValue("dot_inv", self.checkDotInv.checkState())
            builder_settings.setValue("label_alpha", self.spinAlpha.value())
            builder_settings.setValue("label_fontsize", self.spinFontsize.value())
            builder_settings.setValue("autoconnectuni", self.checkAutoconnectUni.checkState())
            builder_settings.setValue("autoconnectinv", self.checkAutoconnectInv.checkState())
            builder_settings.setValue("use_inv_guess", self.checkUseInvGuess.checkState())
            builder_settings.setValue("overwrite", self.checkOverwrite.checkState())
            builder_settings.beginWriteArray("recent")
            for ix, f in enumerate(self.recent):
                builder_settings.setArrayIndex(ix)
                builder_settings.setValue("projfile", f)
            builder_settings.endArray()
        else:
            self.spinSteps.setValue(builder_settings.value("steps", 50, type=int))
            self.spinPrec.setValue(builder_settings.value("precision", 1, type=int))
            self.spinOver.setValue(builder_settings.value("extend_range", 5, type=int))
            self.spinDoglevel.setValue(builder_settings.value("dogmin_level", 1, type=int))
            self.checkLabelUni.setCheckState(builder_settings.value("label_uni", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.checkLabelUniText.setCheckState(builder_settings.value("label_uni_text", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.checkLabelInv.setCheckState(builder_settings.value("label_inv", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.checkLabelInvText.setCheckState(builder_settings.value("label_inv_text", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.checkLabelDog.setCheckState(builder_settings.value("label_dog", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.checkLabelDogText.setCheckState(builder_settings.value("label_dog_text", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.checkDotInv.setCheckState(builder_settings.value("dot_inv", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.spinAlpha.setValue(builder_settings.value("label_alpha", 50, type=int))
            self.spinFontsize.setValue(builder_settings.value("label_fontsize", 8, type=int))
            self.checkAutoconnectUni.setCheckState(builder_settings.value("autoconnectuni", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.checkAutoconnectInv.setCheckState(builder_settings.value("autoconnectinv", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.checkUseInvGuess.setCheckState(builder_settings.value("use_inv_guess", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.checkOverwrite.setCheckState(builder_settings.value("overwrite", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.recent = []
            n = builder_settings.beginReadArray("recent")
            for ix in range(n):
                builder_settings.setArrayIndex(ix)
                self.recent.append(builder_settings.value("projfile", type=str))
            builder_settings.endArray()

    def builder_refresh_gui(self):
        pass

    def initProject(self, workdir=False):
        """Open working directory and initialize project
        """
        if self.changed:
            quit_msg = 'Project have been changed. Save ?'
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Message', quit_msg,
                                qb.Discard | qb.Save, qb.Save)

            if reply == qb.Save:
                self.do_save()
        qd = QtWidgets.QFileDialog
        if not workdir:
            workdir = qd.getExistingDirectory(self, "Select Directory",
                                              os.path.expanduser('~'),
                                              qd.ShowDirsOnly)
        if workdir:
            tc = TCAPI(workdir)
            if tc.OK:
                self.tc = tc
                self.ps = PTsection(trange=self.tc.trange,
                                    prange=self.tc.prange,
                                    excess=self.tc.excess)
                self.bulk = self.tc.bulk
                self.ready = True
                self.initViewModels()
                self.project = None
                self.changed = False
                self.refresh_gui()
                self.statusBar().showMessage('Project initialized successfully.')
            else:
                qb = QtWidgets.QMessageBox
                qb.critical(self, 'Initialization error', tc.status, qb.Abort)

    def openProject(self, checked, projfile=None):
        """Open working directory and initialize project
        """
        if self.changed:
            quit_msg = 'Project have been changed. Save ?'
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Message', quit_msg,
                                qb.Discard | qb.Save,
                                qb.Save)

            if reply == qb.Save:
                self.do_save()
        if projfile is None:
            if self.ready:
                openin = str(self.tc.workdir)
            else:
                openin = os.path.expanduser('~')
            qd = QtWidgets.QFileDialog
            projfile = qd.getOpenFileName(self, 'Open project', openin,
                                          self.builder_file_selector)[0]
        if Path(projfile).is_file():
            with gzip.open(projfile, 'rb') as stream:
                data = pickle.load(stream)
            ##### NEW FORMAT ####
            if 'section' in data: # NEW
                workdir = data.get('workdir', Path(projfile).resolve().parent).resolve()
                if workdir != Path(projfile).resolve().parent:
                    move_msg = 'Project have been moved. Change working directory ?'
                    qb = QtWidgets.QMessageBox
                    reply = qb.question(self, 'Warning', move_msg,
                                        qb.Yes | qb.No,
                                        qb.No)

                    if reply == qb.Yes:
                        workdir = Path(projfile).resolve().parent
                QtWidgets.QApplication.processEvents()
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
                tc = TCAPI(workdir)
                if tc.OK:
                    self.tc = tc
                    self.ps = PTsection(trange=data['section'].xrange,
                                        prange=data['section'].yrange,
                                        excess=data['section'].excess)
                    self.initViewModels()
                    # select phases
                    for i in range(self.phasemodel.rowCount()):
                        item = self.phasemodel.item(i)
                        if item.text() in data['selphases']:
                            item.setCheckState(QtCore.Qt.Checked)
                    # select out
                    for i in range(self.outmodel.rowCount()):
                        item = self.outmodel.item(i)
                        if item.text() in data['out']:
                            item.setCheckState(QtCore.Qt.Checked)
                    # views
                    for id, inv in data['section'].invpoints.items():
                        self.invmodel.appendRow(id, inv)
                    self.invview.resizeColumnsToContents()
                    for id, uni in data['section'].unilines.items():
                        self.unimodel.appendRow(id, uni)
                    self.uniview.resizeColumnsToContents()
                    if hasattr(data['section'], 'dogmins'):
                        for id, dgm in data['section'].dogmins.items():
                            self.dogmodel.appendRow(id, dgm)
                        self.dogview.resizeColumnsToContents()
                    self.ready = True
                    self.project = projfile
                    self.changed = False
                    if projfile in self.recent:
                        self.recent.pop(self.recent.index(projfile))
                    self.recent.insert(0, projfile)
                    if len(self.recent) > 15:
                        self.recent = self.recent[:15]
                    self.populate_recent()
                    self.app_settings(write=True)
                    self.refresh_gui()
                    if 'bulk' in data:
                        self.bulk = data['bulk']
                        self.tc.update_scriptfile(bulk=data['bulk'])
                        self.read_scriptfile()
                    else:
                        self.bulk = self.tc.bulk
                    self.statusBar().showMessage('Project loaded.')
                else:
                    qb = QtWidgets.QMessageBox
                    qb.critical(self, 'Error during openning', tc.status, qb.Abort)
            ##### VERY OLD FORMAT ####
            elif data.get('version', '1.0.0') < '2.1.0':
                qb = QtWidgets.QMessageBox
                qb.critical(self, 'Old version',
                            'This project is created in older version.\nUse import from project.',
                            qb.Abort)
            ##### OLD FORMAT ####
            elif data.get('version', '1.0.0') < '2.3.0':
                workdir = data.get('workdir', Path(projfile).resolve().parent).resolve()
                if workdir != Path(projfile).resolve().parent:
                    move_msg = 'Project have been moved. Change working directory ?'
                    qb = QtWidgets.QMessageBox
                    reply = qb.question(self, 'Warning', move_msg,
                                        qb.Yes | qb.No,
                                        qb.No)

                    if reply == qb.Yes:
                        workdir = Path(projfile).resolve().parent
                QtWidgets.QApplication.processEvents()
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
                tc = TCAPI(workdir)
                if tc.OK:
                    self.tc = tc
                    self.ps = PTsection(trange=data['trange'],
                                        prange=data['prange'],
                                        excess=self.tc.excess)
                    self.initViewModels()
                    # select phases
                    for i in range(self.phasemodel.rowCount()):
                        item = self.phasemodel.item(i)
                        if item.text() in data['selphases']:
                            item.setCheckState(QtCore.Qt.Checked)
                    # select out
                    for i in range(self.outmodel.rowCount()):
                        item = self.outmodel.item(i)
                        if item.text() in data['out']:
                            item.setCheckState(QtCore.Qt.Checked)
                    # views
                    for row in data['invlist']:
                        if row[2]['manual']:
                            inv = InvPoint(id=row[0],
                                           phases=row[2]['phases'],
                                           out=row[2]['out'],
                                           x=row[2]['T'],
                                           y=row[2]['p'],
                                           manual=True)
                        else:
                            inv = InvPoint(id=row[0],
                                           phases=row[2]['phases'],
                                           out=row[2]['out'],
                                           x=row[2]['T'],
                                           y=row[2]['p'],
                                           results=row[2]['results'],
                                           output=row[2]['output'])
                        self.invmodel.appendRow(row[0], inv)
                    self.invview.resizeColumnsToContents()
                    for row in data['unilist']:
                        if row[4]['manual']:
                            uni = UniLine(id=row[0],
                                          phases=row[4]['phases'],
                                          out=row[4]['out'],
                                          x=row[4]['T'],
                                          y=row[4]['p'],
                                          manual=True,
                                          begin=row[2],
                                          end=row[3])
                        else:
                            uni = UniLine(id=row[0],
                                          phases=row[4]['phases'],
                                          out=row[4]['out'],
                                          x=row[4]['T'],
                                          y=row[4]['p'],
                                          results=row[4]['results'],
                                          output=row[4]['output'],
                                          begin=row[2],
                                          end=row[3])
                        self.unimodel.appendRow(row[0], uni)
                        self.ps.trim_uni(row[0])
                    self.uniview.resizeColumnsToContents()
                    # cutting
                    #for row in self.unimodel.unilist:
                    #    self.trimuni(row)
                    # all done
                    self.ready = True
                    self.project = projfile
                    self.changed = False
                    if projfile in self.recent:
                        self.recent.pop(self.recent.index(projfile))
                    self.recent.insert(0, projfile)
                    if len(self.recent) > 15:
                        self.recent = self.recent[:15]
                    self.populate_recent()
                    self.app_settings(write=True)
                    self.refresh_gui()
                    self.statusBar().showMessage('Project loaded.')
                else:
                    qb = QtWidgets.QMessageBox
                    qb.critical(self, 'Error during openning', tc.status, qb.Abort)
            else:
                qb = QtWidgets.QMessageBox
                qb.critical(self, 'Error during openning', 'Unknown format of the project file', qb.Abort)
            QtWidgets.QApplication.restoreOverrideCursor()
        else:
            if projfile in self.recent:
                self.recent.pop(self.recent.index(projfile))
                self.app_settings(write=True)
                self.populate_recent()

    def import_drfile(self):  # FIXME:
        if self.ready:
            qd = QtWidgets.QFileDialog
            tpfile = qd.getOpenFileName(self, 'Open drawpd file', str(self.tc.workdir),
                                        'Drawpd files (*.txt);;All files (*.*)')[0]
            if tpfile:
                tp = []
                tpok = True
                with open(tpfile, 'r', encoding=self.tc.TCenc) as tfile:
                    for line in tfile:
                        n = line.split('%')[0].strip()
                        if n != '':
                            if '-' in n:
                                if n.startswith('i') or n.startswith('u'):
                                    tp.append(n.split(' ', 1)[1].strip())
                if tpok and tp:
                    for r in tp:
                        po = r.split('-')
                        out = set(po[1].split())
                        phases = set(po[0].split()).union(out).union(self.ps.excess)
                        self.do_calc(True, phases=phases, out=out)
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    @property
    def plot_title(self):
        ex = list(self.ps.excess)
        ex.insert(0, '')
        return self.tc.axname + ' +'.join(ex)

    def reset_limits(self):
        if self.ready:
            fmt = lambda x: '{:.{prec}f}'.format(x, prec=self.spinPrec.value())
            self.tminEdit.setText(fmt(self.tc.trange[0]))
            self.tmaxEdit.setText(fmt(self.tc.trange[1]))
            self.pminEdit.setText(fmt(self.tc.prange[0]))
            self.pmaxEdit.setText(fmt(self.tc.prange[1]))

    def uni_explore(self):
        if self.unisel.hasSelection():
            idx = self.unisel.selectedIndexes()
            uni = self.ps.unilines[self.unimodel.data(idx[0])]
            phases = uni.phases
            out = uni.out
            self.statusBar().showMessage('Searching for invariant points...')
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            # set guesses temporarily when asked
            if uni.connected == 1 and self.checkUseInvGuess.isChecked():
                inv_id = sorted([uni.begin, uni.end])[1]
                old_guesses = self.tc.update_scriptfile(guesses=self.ps.invpoints[inv_id].ptguess(), get_old_guesses=True)
            # Try out from phases
            extend = self.spinOver.value()
            trange = self.ax.get_xlim()
            ts = extend * (trange[1] - trange[0]) / 100
            trange = (max(trange[0] - ts, 11), trange[1] + ts)
            prange = self.ax.get_ylim()
            ps = extend * (prange[1] - prange[0]) / 100
            prange = (max(prange[0] - ps, 0.01), prange[1] + ps)
            cand = []
            for ophase in phases.difference(out).difference(self.ps.excess):
                nout = out.union(set([ophase]))
                self.tc.calc_pt(phases, nout, prange = prange, trange=trange)
                status, variance, pts, res, output = self.tc.parse_logfile()
                if status == 'ok':
                    inv = InvPoint(phases=phases, out=nout, variance=variance,
                                   y=pts[0], x=pts[1], output=output, results=res)
                    isnew, id = self.ps.getidinv(inv)
                    if isnew:
                        exists, inv_id = '', ''
                    else:
                        exists, inv_id = '*', str(id)
                    cand.append((inv._x, inv._y, exists, ' '.join(inv.out), inv_id))

            for ophase in set(self.tc.phases).difference(self.ps.excess).difference(phases):
                nphases = phases.union(set([ophase]))
                nout = out.union(set([ophase]))
                self.tc.calc_pt(nphases, nout, prange = prange, trange=trange)
                status, variance, pts, res, output = self.tc.parse_logfile()
                if status == 'ok':
                    inv = InvPoint(phases=nphases, out=nout, variance=variance,
                                   y=pts[0], x=pts[1], output=output, results=res)
                    isnew, id = self.ps.getidinv(inv)
                    if isnew:
                        exists, inv_id = '', ''
                    else:
                        exists, inv_id = '*', str(id)
                    cand.append((inv._x, inv._y, exists, ' '.join(inv.out), inv_id))

            # set original ptguesses when asked
            if uni.connected == 1 and self.checkUseInvGuess.isChecked():
                self.tc.update_scriptfile(guesses=old_guesses)
            QtWidgets.QApplication.restoreOverrideCursor()
            if cand:
                txt = '         {}         {} E     Out   Inv\n'.format(self.ps.x_var, self.ps.y_var)
                n_format = '{:10.4f}{:10.4f}{:>2}{:>8}{:>6}\n'
                for cc in sorted(cand, reverse=True):
                    txt += n_format.format(*cc)

                self.textOutput.setPlainText(txt)
                self.statusBar().showMessage('Searching done. Found {} invariant points.'.format(len(cand)))
            else:
                self.statusBar().showMessage('No invariant points found.')

    def dogminer(self, event):
        self.cid.onmove(event)
        if event.inaxes is not None:
            self.cid.clear(event)
            phases, out = self.get_phases_out()
            which = phases.difference(self.ps.excess)
            variance = self.spinVariance.value()
            doglevel = self.spinDoglevel.value()
            prec = self.spinPrec.value()
            self.statusBar().showMessage('Running dogmin with max variance of equilibria at {}...'.format(variance))
            self.tc.update_scriptfile(dogmin='yes {}'.format(doglevel), which=which,
                                       T='{:.{prec}f}'.format(event.xdata, prec=prec),
                                       p='{:.{prec}f}'.format(event.ydata, prec=prec))
            #self.read_scriptfile()
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            tcout = self.tc.dogmin(variance)
            self.logText.setPlainText('Working directory:{}\n\n'.format(self.tc.workdir) + tcout)
            output, resic = self.tc.parse_dogmin()
            if output is not None:
                dgm = Dogmin(output=output, resic=resic, x=event.xdata, y=event.ydata)
                if dgm.phases:
                    id_dog = 0
                    for key in self.ps.dogmins:
                        id_dog = max(id_dog, key)
                    id_dog += 1
                    self.dogmodel.appendRow(id_dog, dgm)
                    self.dogview.resizeColumnsToContents()
                    self.changed = True
                    idx = self.dogmodel.getIndexID(id_dog)
                    self.dogview.selectRow(idx.row())
                    self.dogview.scrollToBottom()
                    self.plot()
                    self.statusBar().showMessage('Dogmin finished.')
                else:
                    self.statusBar().showMessage('Dogmin failed.')
            else:
                self.statusBar().showMessage('Dogmin failed.')
            self.pushDogmin.setChecked(False)

    def do_calc(self, calcT, phases={}, out={}):
        if self.ready:
            if phases == {} and out == {}:
                phases, out = self.get_phases_out()
            self.statusBar().showMessage('Running THERMOCALC...')
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            ###########
            extend = self.spinOver.value()
            trange = self.ax.get_xlim()
            ts = extend * (trange[1] - trange[0]) / 100
            trange = (max(trange[0] - ts, 11), trange[1] + ts)
            prange = self.ax.get_ylim()
            ps = extend * (prange[1] - prange[0]) / 100
            prange = (max(prange[0] - ps, 0.01), prange[1] + ps)
            steps = self.spinSteps.value()

            if len(out) == 1:
                uni_tmp = UniLine(phases=phases, out=out)
                isnew, id_uni = self.ps.getiduni(uni_tmp)
                if calcT:
                    tcout, ans = self.tc.calc_t(uni_tmp.phases, uni_tmp.out, prange = prange, trange=trange, steps=steps)
                else:
                    tcout, ans = self.tc.calc_p(uni_tmp.phases, uni_tmp.out, prange = prange, trange=trange, steps=steps)
                self.logText.setPlainText('Working directory:{}\n\n'.format(self.tc.workdir) + tcout)
                status, variance, pts, res, output = self.tc.parse_logfile()
                if status == 'bombed':
                    self.statusBar().showMessage('Bombed.')
                elif status == 'nir':
                    self.statusBar().showMessage('Nothing in range.')
                elif len(res) < 2:
                    self.statusBar().showMessage('Only one point calculated. Change range.')
                else:
                    uni = UniLine(id=id_uni, phases=uni_tmp.phases, out=uni_tmp.out, cmd=ans,
                                  variance=variance, y=pts[0], x=pts[1], output=output, results=res)
                    if self.checkAutoconnectUni.isChecked():
                        candidates = [inv for inv in self.ps.invpoints.values() if uni.contains_inv(inv)]
                    if isnew:
                        self.unimodel.appendRow(id_uni, uni)
                        self.uniview.resizeColumnsToContents()
                        self.changed = True
                        # self.unisel.select(idx, QtCore.QItemSelectionModel.ClearAndSelect | QtCore.QItemSelectionModel.Rows)
                        idx = self.unimodel.getIndexID(id_uni)
                        self.uniview.selectRow(idx.row())
                        self.uniview.scrollToBottom()
                        if self.checkAutoconnectUni.isChecked():
                            if len(candidates) == 2:
                                self.uni_connect(id_uni, candidates)
                        self.plot()
                        self.show_uni(idx)
                        self.statusBar().showMessage('New univariant line calculated.')
                    else:
                        if not self.checkOverwrite.isChecked():
                            uni.begin = self.ps.unilines[id_uni].begin
                            uni.end = self.ps.unilines[id_uni].end
                            self.ps.unilines[id_uni] = uni
                            self.ps.trim_uni(id_uni)
                            if self.checkAutoconnectUni.isChecked():
                                if len(candidates) == 2:
                                    self.uni_connect(id_uni, candidates)
                            self.changed = True
                            self.uniview.resizeColumnsToContents()
                            idx = self.unimodel.getIndexID(id_uni)
                            self.uniview.selectRow(idx.row())
                            self.plot()
                            self.show_uni(idx)
                            self.statusBar().showMessage('Univariant line {} re-calculated.'.format(id_uni))
                        else:
                            self.statusBar().showMessage('Univariant line already exists.')
            elif len(out) == 2:
                inv_tmp = InvPoint(phases=phases, out=out)
                isnew, id_inv = self.ps.getidinv(inv_tmp)
                tcout, ans = self.tc.calc_pt(inv_tmp.phases, inv_tmp.out, prange = prange, trange=trange)
                self.logText.setPlainText('Working directory:{}\n\n'.format(self.tc.workdir) + tcout)
                status, variance, pts, res, output = self.tc.parse_logfile()
                if status == 'bombed':
                    self.statusBar().showMessage('Bombed.')
                elif status == 'nir':
                    self.statusBar().showMessage('Nothing in range.')
                else:
                    inv = InvPoint(id=id_inv, phases=inv_tmp.phases, out=inv_tmp.out, cmd=ans,
                                   variance=variance, y=pts[0], x=pts[1], output=output, results=res)
                    if isnew:
                        self.invmodel.appendRow(id_inv, inv)
                        self.invview.resizeColumnsToContents()
                        self.changed = True
                        idx = self.invmodel.getIndexID(id_inv)
                        self.invview.selectRow(idx.row())
                        self.invview.scrollToBottom()
                        if self.checkAutoconnectInv.isChecked():
                            for uni in self.ps.unilines.values():
                                if uni.contains_inv(inv):
                                    candidates = [inv]
                                    for other_inv in self.ps.invpoints.values():
                                        if other_inv.id != id_inv:
                                            if uni.contains_inv(other_inv):
                                                candidates.append(other_inv)
                                    if len(candidates) == 2:
                                        self.uni_connect(uni.id, candidates)
                                        self.uniview.resizeColumnsToContents()
                        self.plot()
                        self.show_inv(idx)
                        self.statusBar().showMessage('New invariant point calculated.')
                    else:
                        if not self.checkOverwrite.isChecked():
                            self.ps.invpoints[id_inv] = inv
                            for uni in self.ps.unilines.values():
                                if uni.begin == id_inv or uni.end == id_inv:
                                    self.ps.trim_uni(uni.id)
                            self.changed = True
                            self.invview.resizeColumnsToContents()
                            idx = self.invmodel.getIndexID(id_inv)
                            self.plot()
                            self.show_inv(idx)
                            self.statusBar().showMessage('Invariant point {} re-calculated.'.format(id_inv))
                        else:
                            self.statusBar().showMessage('Invariant point already exists.')
            else:
                self.statusBar().showMessage('{} zero mode phases selected. Select one or two!'.format(len(out)))
            #########
            QtWidgets.QApplication.restoreOverrideCursor()
        else:
            self.statusBar().showMessage('Project is not yet initialized.')


class TXBuilder(BuildersBase, Ui_TXBuilder):
    """Main class for txbuilder
    """
    def __init__(self, parent=None):
        self.builder_name = 'TXBuilder'
        self.builder_extension = '.txb'
        self.ps = TXsection()
        super(TXBuilder, self).__init__(parent)

    def builder_ui_settings(self):
        # CONNECT SIGNALS
        self.pushCalc.clicked.connect(self.do_calc)
        # additional keyboard shortcuts
        self.scCalc = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+T"), self)
        self.scCalc.activated.connect(self.do_calc)

    def app_settings(self, write=False):
        # Applicatiom settings
        builder_settings = QtCore.QSettings('LX', 'txbuilder')
        if write:
            builder_settings.setValue("precision", self.spinPrec.value())
            builder_settings.setValue("extend_range", self.spinOver.value())
            builder_settings.setValue("prange", self.rangeSpin.value())
            builder_settings.setValue("label_uni", self.checkLabelUni.checkState())
            builder_settings.setValue("dogmin_level", self.spinDoglevel.value())
            builder_settings.setValue("label_uni_text", self.checkLabelUniText.checkState())
            builder_settings.setValue("label_inv", self.checkLabelInv.checkState())
            builder_settings.setValue("label_inv_text", self.checkLabelInvText.checkState())
            builder_settings.setValue("label_dog", self.checkLabelDog.checkState())
            builder_settings.setValue("label_dog_text", self.checkLabelDogText.checkState())
            builder_settings.setValue("dot_inv", self.checkDotInv.checkState())
            builder_settings.setValue("label_alpha", self.spinAlpha.value())
            builder_settings.setValue("label_fontsize", self.spinFontsize.value())
            builder_settings.setValue("autoconnectuni", self.checkAutoconnectUni.checkState())
            builder_settings.setValue("autoconnectinv", self.checkAutoconnectInv.checkState())
            builder_settings.setValue("use_inv_guess", self.checkUseInvGuess.checkState())
            builder_settings.setValue("overwrite", self.checkOverwrite.checkState())
            builder_settings.beginWriteArray("recent")
            for ix, f in enumerate(self.recent):
                builder_settings.setArrayIndex(ix)
                builder_settings.setValue("projfile", f)
            builder_settings.endArray()
        else:
            self.spinPrec.setValue(builder_settings.value("precision", 1, type=int))
            self.spinOver.setValue(builder_settings.value("extend_range", 5, type=int))
            self.rangeSpin.setValue(builder_settings.value("prange", 1, type=float))
            self.checkLabelUni.setCheckState(builder_settings.value("label_uni", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.spinDoglevel.setValue(builder_settings.value("dogmin_level", 1, type=int))
            self.checkLabelUniText.setCheckState(builder_settings.value("label_uni_text", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.checkLabelInv.setCheckState(builder_settings.value("label_inv", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.checkLabelInvText.setCheckState(builder_settings.value("label_inv_text", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.checkLabelDog.setCheckState(builder_settings.value("label_dog", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.checkLabelDogText.setCheckState(builder_settings.value("label_dog_text", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.checkDotInv.setCheckState(builder_settings.value("dot_inv", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.spinAlpha.setValue(builder_settings.value("label_alpha", 50, type=int))
            self.spinFontsize.setValue(builder_settings.value("label_fontsize", 8, type=int))
            self.checkAutoconnectUni.setCheckState(builder_settings.value("autoconnectuni", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.checkAutoconnectInv.setCheckState(builder_settings.value("autoconnectinv", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.checkUseInvGuess.setCheckState(builder_settings.value("use_inv_guess", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.checkOverwrite.setCheckState(builder_settings.value("overwrite", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.recent = []
            n = builder_settings.beginReadArray("recent")
            for ix in range(n):
                builder_settings.setArrayIndex(ix)
                self.recent.append(builder_settings.value("projfile", type=str))
            builder_settings.endArray()

    def builder_refresh_gui(self):
        self.spinSteps.setValue(self.tc.ptx_steps)

    def initProject(self, workdir=False):
        """Open working directory and initialize project
        """
        if self.changed:
            quit_msg = 'Project have been changed. Save ?'
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Message', quit_msg,
                                qb.Discard | qb.Save, qb.Save)

            if reply == qb.Save:
                self.do_save()
        qd = QtWidgets.QFileDialog
        if not workdir:
            workdir = qd.getExistingDirectory(self, "Select Directory",
                                              os.path.expanduser('~'),
                                              qd.ShowDirsOnly)
        if workdir:
            tc = TCAPI(workdir)
            if tc.OK:
                self.tc = tc
                self.ps = TXsection(trange=self.tc.trange,
                                    excess=self.tc.excess)
                self.bulk = self.tc.bulk
                self.ready = True
                self.initViewModels()
                self.project = None
                self.changed = False
                self.refresh_gui()
                self.statusBar().showMessage('Project initialized successfully.')
            else:
                qb = QtWidgets.QMessageBox
                qb.critical(self, 'Initialization error', tc.status, qb.Abort)

    def openProject(self, checked, projfile=None):
        """Open working directory and initialize project
        """
        if self.changed:
            quit_msg = 'Project have been changed. Save ?'
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Message', quit_msg,
                                qb.Discard | qb.Save,
                                qb.Save)

            if reply == qb.Save:
                self.do_save()
        if projfile is None:
            if self.ready:
                openin = str(self.tc.workdir)
            else:
                openin = os.path.expanduser('~')
            qd = QtWidgets.QFileDialog
            projfile = qd.getOpenFileName(self, 'Open project', openin,
                                          self.builder_file_selector)[0]
        if Path(projfile).is_file():
            with gzip.open(projfile, 'rb') as stream:
                data = pickle.load(stream)
            if 'section' in data:
                workdir = data.get('workdir', Path(projfile).resolve().parent).resolve()
                if workdir != Path(projfile).resolve().parent:
                    move_msg = 'Project have been moved. Change working directory ?'
                    qb = QtWidgets.QMessageBox
                    reply = qb.question(self, 'Warning', move_msg,
                                        qb.Yes | qb.No,
                                        qb.No)

                    if reply == qb.Yes:
                        workdir = Path(projfile).resolve().parent
                QtWidgets.QApplication.processEvents()
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
                tc = TCAPI(workdir)
                if tc.OK:
                    self.tc = tc
                    self.ps = TXsection(trange=data['section'].xrange,
                                        excess=data['section'].excess)
                    self.initViewModels()
                    # select phases
                    for i in range(self.phasemodel.rowCount()):
                        item = self.phasemodel.item(i)
                        if item.text() in data['selphases']:
                            item.setCheckState(QtCore.Qt.Checked)
                    # select out
                    for i in range(self.outmodel.rowCount()):
                        item = self.outmodel.item(i)
                        if item.text() in data['out']:
                            item.setCheckState(QtCore.Qt.Checked)
                    # views
                    for id, inv in data['section'].invpoints.items():
                        self.invmodel.appendRow(id, inv)
                    self.invview.resizeColumnsToContents()
                    for id, uni in data['section'].unilines.items():
                        self.unimodel.appendRow(id, uni)
                    self.uniview.resizeColumnsToContents()
                    if hasattr(data['section'], 'dogmins'):
                        for id, dgm in data['section'].dogmins.items():
                            self.dogmodel.appendRow(id, dgm)
                        self.dogview.resizeColumnsToContents()
                    self.ready = True
                    self.project = projfile
                    self.changed = False
                    if projfile in self.recent:
                        self.recent.pop(self.recent.index(projfile))
                    self.recent.insert(0, projfile)
                    if len(self.recent) > 15:
                        self.recent = self.recent[:15]
                    self.populate_recent()
                    self.app_settings(write=True)
                    self.refresh_gui()
                    if 'bulk' in data:
                        self.bulk = data['bulk']
                        self.tc.update_scriptfile(bulk=data['bulk'],
                                                  xsteps=self.spinSteps.value())
                        self.read_scriptfile()
                    else:
                        self.bulk = self.tc.bulk
                    self.statusBar().showMessage('Project loaded.')
                else:
                    qb = QtWidgets.QMessageBox
                    qb.critical(self, 'Error during openning', tc.status, qb.Abort)
            else:
                qb = QtWidgets.QMessageBox
                qb.critical(self, 'Error during openning', 'Unknown format of the project file', qb.Abort)
            QtWidgets.QApplication.restoreOverrideCursor()
        else:
            if projfile in self.recent:
                self.recent.pop(self.recent.index(projfile))
                self.app_settings(write=True)
                self.populate_recent()

    @property
    def plot_title(self):
        ex = list(self.ps.excess)
        ex.insert(0, '')
        return self.tc.axname + ' +'.join(ex) + ' (at {:g} kbar)'.format(np.mean(self.tc.prange))

    def reset_limits(self):
        if self.ready:
            fmt = lambda x: '{:.{prec}f}'.format(x, prec=self.spinPrec.value())
            self.tminEdit.setText(fmt(self.tc.trange[0]))
            self.tmaxEdit.setText(fmt(self.tc.trange[1]))
            self.pminEdit.setText(fmt(0))
            self.pmaxEdit.setText(fmt(1))

    def uni_explore(self):
        if self.unisel.hasSelection():
            idx = self.unisel.selectedIndexes()
            uni = self.ps.unilines[self.unimodel.data(idx[0])]
            phases = uni.phases
            out = uni.out
            self.statusBar().showMessage('Searching for invariant points...')
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            # set guesses temporarily when asked
            if uni.connected == 1 and self.checkUseInvGuess.isChecked():
                inv_id = sorted([uni.begin, uni.end])[1]
                old_guesses = self.tc.update_scriptfile(guesses=self.ps.invpoints[inv_id].ptguess(), get_old_guesses=True)
            # Try out from phases
            extend = self.spinOver.value()
            trange = self.ax.get_xlim()
            ts = extend * (trange[1] - trange[0]) / 100
            trange = (max(trange[0] - ts, 11), trange[1] + ts)
            prange = (max(self.tc.prange[0] - self.rangeSpin.value() / 2, 0.01),
                      self.tc.prange[1] + self.rangeSpin.value() / 2)
            crange = self.ax.get_ylim()
            cs = extend * (crange[1] - crange[0]) / 100
            crange = (crange[0] - cs, crange[1] + cs)
            # change bulk
            bulk = self.tc.interpolate_bulk(crange)
            self.tc.update_scriptfile(bulk=bulk, xsteps=self.spinSteps.value(), xvals=crange)

            out_section = []
            cand = []
            for ophase in phases.difference(out).difference(self.ps.excess):
                nout = out.union(set([ophase]))
                self.tc.calc_tx(phases, nout, prange = prange, trange=trange)
                status, variance, pts, ptcoords, res, output = self.tc.parse_logfile(tx=True)
                inv = InvPoint(phases=phases, out=nout)
                isnew, id = self.ps.getidinv(inv)
                if status == 'ok':
                    if isnew:
                        exists, inv_id = '', ''
                    else:
                        exists, inv_id = '*', str(id)
                    if len(res) > 1:
                        # rescale pts from zoomed composition
                        pts[0] = crange[0] + pts[0] * (crange[1] - crange[0])
                        pm = (self.tc.prange[0] + self.tc.prange[1]) / 2
                        splt = interp1d(ptcoords[0], ptcoords[1], bounds_error=False, fill_value=np.nan)
                        splx = interp1d(ptcoords[0], pts[0], bounds_error=False, fill_value=np.nan)
                        Xm = splt([pm])
                        Ym = splx([pm])
                        if not np.isnan(Xm[0]):
                            cand.append((Xm[0], Ym[0], exists, ' '.join(inv.out), inv_id))
                        else:
                            ix = abs(ptcoords[0] - pm).argmin()
                            out_section.append((ptcoords[1][ix], ptcoords[0][ix], exists, ' '.join(inv.out), inv_id))
                    else:
                        out_section.append((ptcoords[1][0], ptcoords[0][0], exists, ' '.join(inv.out), inv_id))

            for ophase in set(self.tc.phases).difference(self.ps.excess).difference(phases):
                nphases = phases.union(set([ophase]))
                nout = out.union(set([ophase]))
                self.tc.calc_tx(nphases, nout, prange = prange, trange=trange)
                status, variance, pts, ptcoords, res, output = self.tc.parse_logfile(tx=True)
                inv = InvPoint(phases=nphases, out=nout)
                isnew, id = self.ps.getidinv(inv)
                if status == 'ok':
                    if isnew:
                        exists, inv_id = '', ''
                    else:
                        exists, inv_id = '*', str(id)
                    if len(res) > 1:
                        # rescale pts from zoomed composition
                        pts[0] = crange[0] + pts[0] * (crange[1] - crange[0])
                        pm = (self.tc.prange[0] + self.tc.prange[1]) / 2
                        splt = interp1d(ptcoords[0], ptcoords[1], bounds_error=False, fill_value=np.nan)
                        splx = interp1d(ptcoords[0], pts[0], bounds_error=False, fill_value=np.nan)
                        Xm = splt([pm])
                        Ym = splx([pm])
                        if not np.isnan(Xm[0]):
                            cand.append((Xm[0], Ym[0], exists, ' '.join(inv.out), inv_id))
                        else:
                            ix = abs(ptcoords[0] - pm).argmin()
                            out_section.append((ptcoords[1][ix], ptcoords[0][ix], exists, ' '.join(inv.out), inv_id))
                    else:
                        out_section.append((ptcoords[1][0], ptcoords[0][0], exists, ' '.join(inv.out), inv_id))

            # set original ptguesses when asked
            if uni.connected == 1 and self.checkUseInvGuess.isChecked():
                self.tc.update_scriptfile(guesses=old_guesses)
            # restore bulk
            self.tc.update_scriptfile(bulk=self.bulk, xsteps=self.spinSteps.value())
            QtWidgets.QApplication.restoreOverrideCursor()
            txt = ''
            n_format = '{:10.4f}{:10.4f}{:>2}{:>8}{:>6}\n'
            if cand:
                txt += '         {}         {} E     Out   Inv\n'.format(self.ps.x_var, self.ps.y_var)
                for cc in sorted(cand, reverse=True):
                    txt += n_format.format(*cc)

                self.textOutput.setPlainText(txt)
                self.statusBar().showMessage('Searching done. Found {} invariant points.'.format(len(cand)))
            elif out_section:
                txt += 'Solutions with single point (need increase number of steps)\n'
                txt += '         T         p E     Out   Inv\n'.format(self.ps.x_var, self.ps.y_var)
                for cc in out_section:
                    txt += n_format.format(*cc)

                self.textOutput.setPlainText(txt)
                self.statusBar().showMessage('Searching done. Found {} invariant points and {} out of section.'.format(len(cand), len(out_section)))
            else:
                self.statusBar().showMessage('No invariant points found.')

    def dogminer(self, event):
        self.cid.onmove(event)
        if event.inaxes is not None:
            self.cid.clear(event)
            phases, out = self.get_phases_out()
            which = phases.difference(self.ps.excess)
            variance = self.spinVariance.value()
            doglevel = self.spinDoglevel.value()
            prec = self.spinPrec.value()
            # change bulk
            bulk = self.tc.interpolate_bulk(event.ydata)
            self.statusBar().showMessage('Running dogmin with max variance of equilibria at {}...'.format(variance))
            pm = (self.tc.prange[0] + self.tc.prange[1]) / 2
            self.tc.update_scriptfile(bulk=bulk,
                                      dogmin='yes {}'.format(doglevel), which=which,
                                      T='{:.{prec}f}'.format(event.xdata, prec=prec),
                                      p='{:.{prec}f}'.format(pm, prec=prec))
            #self.read_scriptfile()
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            tcout = self.tc.dogmin(variance)
            self.logText.setPlainText('Working directory:{}\n\n'.format(self.tc.workdir) + tcout)
            output, resic = self.tc.parse_dogmin()
            if output is not None:
                dgm = Dogmin(output=output, resic=resic, x=event.xdata, y=event.ydata)
                if dgm.phases:
                    id_dog = 0
                    for key in self.ps.dogmins:
                        id_dog = max(id_dog, key)
                    id_dog += 1
                    self.dogmodel.appendRow(id_dog, dgm)
                    self.dogview.resizeColumnsToContents()
                    self.changed = True
                    idx = self.dogmodel.getIndexID(id_dog)
                    self.dogview.selectRow(idx.row())
                    self.dogview.scrollToBottom()
                    self.plot()
                    self.statusBar().showMessage('Dogmin finished.')
                else:
                    self.statusBar().showMessage('Dogmin failed.')
            else:
                self.statusBar().showMessage('Dogmin failed.')
            # restore bulk
            self.tc.update_scriptfile(bulk=self.bulk, xsteps=self.spinSteps.value())
            self.pushDogmin.setChecked(False)

    def do_calc(self, calcT, phases={}, out={}):
        if self.ready:
            if phases == {} and out == {}:
                phases, out = self.get_phases_out()
            self.statusBar().showMessage('Running THERMOCALC...')
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            ###########
            extend = self.spinOver.value()
            trange = self.ax.get_xlim()
            ts = extend * (trange[1] - trange[0]) / 100
            trange = (max(trange[0] - ts, 11), trange[1] + ts)
            prange = (max(self.tc.prange[0] - self.rangeSpin.value() / 2, 0.01),
                      self.tc.prange[1] + self.rangeSpin.value() / 2)
            crange = self.ax.get_ylim()
            cs = extend * (crange[1] - crange[0]) / 100
            crange = (crange[0] - cs, crange[1] + cs)
            # change bulk
            bulk = self.tc.interpolate_bulk(crange)
            self.tc.update_scriptfile(bulk=bulk, xsteps=self.spinSteps.value(), xvals=crange)

            if len(out) == 1:
                uni_tmp = UniLine(phases=phases, out=out)
                isnew, id_uni = self.ps.getiduni(uni_tmp)
                tcout, ans = self.tc.calc_tx(uni_tmp.phases, uni_tmp.out, trange=trange)
                self.logText.setPlainText('Working directory:{}\n\n'.format(self.tc.workdir) + tcout)
                status, variance, pts, ptcoords, res, output = self.tc.parse_logfile(tx=True)
                if status == 'bombed':
                    self.statusBar().showMessage('Bombed.')
                elif status == 'nir':
                    self.statusBar().showMessage('Nothing in range.')
                elif len(res) < 2:
                    self.statusBar().showMessage('Only one point calculated. Change range.')
                else:
                    # rescale pts from zoomed composition
                    pts[0] = crange[0] + pts[0] * (crange[1] - crange[0])
                    uni = UniLine(id=id_uni, phases=uni_tmp.phases, out=uni_tmp.out, cmd=ans,
                                  variance=variance, y=pts[0], x=pts[1], output=output, results=res)
                    if self.checkAutoconnectUni.isChecked():
                        candidates = [inv for inv in self.ps.invpoints.values() if uni.contains_inv(inv)]
                    if isnew:
                        self.unimodel.appendRow(id_uni, uni)
                        self.uniview.resizeColumnsToContents()
                        self.changed = True
                        # self.unisel.select(idx, QtCore.QItemSelectionModel.ClearAndSelect | QtCore.QItemSelectionModel.Rows)
                        idx = self.unimodel.getIndexID(id_uni)
                        self.uniview.selectRow(idx.row())
                        self.uniview.scrollToBottom()
                        if self.checkAutoconnectUni.isChecked():
                            if len(candidates) == 2:
                                self.uni_connect(id_uni, candidates)
                        self.plot()
                        self.show_uni(idx)
                        self.statusBar().showMessage('New univariant line calculated.')
                    else:
                        if not self.checkOverwrite.isChecked():
                            uni.begin = self.ps.unilines[id_uni].begin
                            uni.end = self.ps.unilines[id_uni].end
                            self.ps.unilines[id_uni] = uni
                            self.ps.trim_uni(id_uni)
                            if self.checkAutoconnectUni.isChecked():
                                if len(candidates) == 2:
                                    self.uni_connect(id_uni, candidates)
                            self.changed = True
                            self.uniview.resizeColumnsToContents()
                            idx = self.unimodel.getIndexID(id_uni)
                            self.uniview.selectRow(idx.row())
                            self.plot()
                            self.show_uni(idx)
                            self.statusBar().showMessage('Univariant line {} re-calculated.'.format(id_uni))
                        else:
                            self.statusBar().showMessage('Univariant line already exists.')
            elif len(out) == 2:
                inv_tmp = InvPoint(phases=phases, out=out)
                isnew, id_inv = self.ps.getidinv(inv_tmp)
                tcout, ans = self.tc.calc_tx(inv_tmp.phases, inv_tmp.out, prange = prange, trange=trange)
                self.logText.setPlainText('Working directory:{}\n\n'.format(self.tc.workdir) + tcout)
                status, variance, pts, ptcoords, res, output = self.tc.parse_logfile(tx=True)
                if status == 'bombed':
                    self.statusBar().showMessage('Bombed.')
                elif status == 'nir':
                    self.statusBar().showMessage('Nothing in range.')
                elif len(res) < 2:
                    self.statusBar().showMessage('Only one point calculated. Change steps.')
                else:
                    # rescale pts from zoomed composition
                    pts[0] = crange[0] + pts[0] * (crange[1] - crange[0])
                    pm = (self.tc.prange[0] + self.tc.prange[1]) / 2
                    splt = interp1d(ptcoords[0], ptcoords[1], bounds_error=False, fill_value=np.nan)
                    splx = interp1d(ptcoords[0], pts[0], bounds_error=False, fill_value=np.nan)
                    Xm = splt([pm])
                    Ym = splx([pm])
                    if np.isnan(Xm[0]):
                        status = 'nir'
                        self.statusBar().showMessage('Nothing in range, but exists out ouf section in p range {:.2f} - {:.2f}.'.format(min(ptcoords[0]), max(ptcoords[0])))
                    else:
                        ix = np.argmin((ptcoords[1] - Xm)**2)
                        inv = InvPoint(id=id_inv, phases=inv_tmp.phases, out=inv_tmp.out, cmd=ans,
                                       variance=variance, y=Ym, x=Xm, output=output, results=res[ix:ix + 1])
                        if isnew:
                            self.invmodel.appendRow(id_inv, inv)
                            self.invview.resizeColumnsToContents()
                            self.changed = True
                            idx = self.invmodel.getIndexID(id_inv)
                            self.invview.selectRow(idx.row())
                            self.invview.scrollToBottom()
                            if self.checkAutoconnectInv.isChecked():
                                for uni in self.ps.unilines.values():
                                    if uni.contains_inv(inv):
                                        candidates = [inv]
                                        for other_inv in self.ps.invpoints.values():
                                            if other_inv.id != id_inv:
                                                if uni.contains_inv(other_inv):
                                                    candidates.append(other_inv)
                                        if len(candidates) == 2:
                                            self.uni_connect(uni.id, candidates)
                                            self.uniview.resizeColumnsToContents()
                            self.plot()
                            self.show_inv(idx)
                            self.statusBar().showMessage('New invariant point calculated.')
                        else:
                            if not self.checkOverwrite.isChecked():
                                self.ps.invpoints[id_inv] = inv
                                for uni in self.ps.unilines.values():
                                    if uni.begin == id_inv or uni.end == id_inv:
                                        self.ps.trim_uni(uni.id)
                                self.changed = True
                                self.invview.resizeColumnsToContents()
                                idx = self.invmodel.getIndexID(id_inv)
                                self.plot()
                                self.show_inv(idx)
                                self.statusBar().showMessage('Invariant point {} re-calculated.'.format(id_inv))
                            else:
                                self.statusBar().showMessage('Invariant point already exists.')
            else:
                self.statusBar().showMessage('{} zero mode phases selected. Select one or two!'.format(len(out)))
            #########
            # restore bulk
            self.tc.update_scriptfile(bulk=self.bulk, xsteps=self.spinSteps.value())
            QtWidgets.QApplication.restoreOverrideCursor()
        else:
            self.statusBar().showMessage('Project is not yet initialized.')


class PXBuilder(BuildersBase, Ui_PXBuilder):
    """Main class for pxbuilder
    """
    def __init__(self, parent=None):
        self.builder_name = 'PXBuilder'
        self.builder_extension = '.pxb'
        self.ps = PXsection()
        super(PXBuilder, self).__init__(parent)

    def builder_ui_settings(self):
        # CONNECT SIGNALS
        self.pushCalc.clicked.connect(self.do_calc)
        # additional keyboard shortcuts
        self.scCalc = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+T"), self)
        self.scCalc.activated.connect(self.do_calc)

    def app_settings(self, write=False):
        # Applicatiom settings
        builder_settings = QtCore.QSettings('LX', 'pxbuilder')
        if write:
            builder_settings.setValue("precision", self.spinPrec.value())
            builder_settings.setValue("extend_range", self.spinOver.value())
            builder_settings.setValue("trange", self.rangeSpin.value())
            builder_settings.setValue("label_uni", self.checkLabelUni.checkState())
            builder_settings.setValue("dogmin_level", self.spinDoglevel.value())
            builder_settings.setValue("label_uni_text", self.checkLabelUniText.checkState())
            builder_settings.setValue("label_inv", self.checkLabelInv.checkState())
            builder_settings.setValue("label_inv_text", self.checkLabelInvText.checkState())
            builder_settings.setValue("label_dog", self.checkLabelDog.checkState())
            builder_settings.setValue("label_dog_text", self.checkLabelDogText.checkState())
            builder_settings.setValue("dot_inv", self.checkDotInv.checkState())
            builder_settings.setValue("label_alpha", self.spinAlpha.value())
            builder_settings.setValue("label_fontsize", self.spinFontsize.value())
            builder_settings.setValue("autoconnectuni", self.checkAutoconnectUni.checkState())
            builder_settings.setValue("autoconnectinv", self.checkAutoconnectInv.checkState())
            builder_settings.setValue("use_inv_guess", self.checkUseInvGuess.checkState())
            builder_settings.setValue("overwrite", self.checkOverwrite.checkState())
            builder_settings.beginWriteArray("recent")
            for ix, f in enumerate(self.recent):
                builder_settings.setArrayIndex(ix)
                builder_settings.setValue("projfile", f)
            builder_settings.endArray()
        else:
            self.spinPrec.setValue(builder_settings.value("precision", 1, type=int))
            self.spinOver.setValue(builder_settings.value("extend_range", 5, type=int))
            self.rangeSpin.setValue(builder_settings.value("trange", 50, type=int))
            self.checkLabelUni.setCheckState(builder_settings.value("label_uni", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.spinDoglevel.setValue(builder_settings.value("dogmin_level", 1, type=int))
            self.checkLabelUniText.setCheckState(builder_settings.value("label_uni_text", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.checkLabelInv.setCheckState(builder_settings.value("label_inv", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.checkLabelInvText.setCheckState(builder_settings.value("label_inv_text", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.checkLabelDog.setCheckState(builder_settings.value("label_dog", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.checkLabelDogText.setCheckState(builder_settings.value("label_dog_text", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.checkDotInv.setCheckState(builder_settings.value("dot_inv", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.spinAlpha.setValue(builder_settings.value("label_alpha", 50, type=int))
            self.spinFontsize.setValue(builder_settings.value("label_fontsize", 8, type=int))
            self.checkAutoconnectUni.setCheckState(builder_settings.value("autoconnectuni", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.checkAutoconnectInv.setCheckState(builder_settings.value("autoconnectinv", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.checkUseInvGuess.setCheckState(builder_settings.value("use_inv_guess", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.checkOverwrite.setCheckState(builder_settings.value("overwrite", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.recent = []
            n = builder_settings.beginReadArray("recent")
            for ix in range(n):
                builder_settings.setArrayIndex(ix)
                self.recent.append(builder_settings.value("projfile", type=str))
            builder_settings.endArray()

    def builder_refresh_gui(self):
        self.spinSteps.setValue(self.tc.ptx_steps)

    def initProject(self, workdir=False):
        """Open working directory and initialize project
        """
        if self.changed:
            quit_msg = 'Project have been changed. Save ?'
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Message', quit_msg,
                                qb.Discard | qb.Save, qb.Save)

            if reply == qb.Save:
                self.do_save()
        qd = QtWidgets.QFileDialog
        if not workdir:
            workdir = qd.getExistingDirectory(self, "Select Directory",
                                              os.path.expanduser('~'),
                                              qd.ShowDirsOnly)
        if workdir:
            tc = TCAPI(workdir)
            if tc.OK:
                self.tc = tc
                self.ps = PXsection(prange=self.tc.prange,
                                    excess=self.tc.excess)
                self.bulk = self.tc.bulk
                self.ready = True
                self.initViewModels()
                self.project = None
                self.changed = False
                self.refresh_gui()
                self.statusBar().showMessage('Project initialized successfully.')
            else:
                qb = QtWidgets.QMessageBox
                qb.critical(self, 'Initialization error', tc.status, qb.Abort)

    def openProject(self, checked, projfile=None):
        """Open working directory and initialize project
        """
        if self.changed:
            quit_msg = 'Project have been changed. Save ?'
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Message', quit_msg,
                                qb.Discard | qb.Save,
                                qb.Save)

            if reply == qb.Save:
                self.do_save()
        if projfile is None:
            if self.ready:
                openin = str(self.tc.workdir)
            else:
                openin = os.path.expanduser('~')
            qd = QtWidgets.QFileDialog
            projfile = qd.getOpenFileName(self, 'Open project', openin,
                                          self.builder_file_selector)[0]
        if Path(projfile).is_file():
            with gzip.open(projfile, 'rb') as stream:
                data = pickle.load(stream)
            if 'section' in data:
                workdir = data.get('workdir', Path(projfile).resolve().parent).resolve()
                if workdir != Path(projfile).resolve().parent:
                    move_msg = 'Project have been moved. Change working directory ?'
                    qb = QtWidgets.QMessageBox
                    reply = qb.question(self, 'Warning', move_msg,
                                        qb.Yes | qb.No,
                                        qb.No)

                    if reply == qb.Yes:
                        workdir = Path(projfile).resolve().parent
                QtWidgets.QApplication.processEvents()
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
                tc = TCAPI(workdir)
                if tc.OK:
                    self.tc = tc
                    self.ps = PXsection(prange=data['section'].yrange,
                                        excess=data['section'].excess)
                    self.initViewModels()
                    # select phases
                    for i in range(self.phasemodel.rowCount()):
                        item = self.phasemodel.item(i)
                        if item.text() in data['selphases']:
                            item.setCheckState(QtCore.Qt.Checked)
                    # select out
                    for i in range(self.outmodel.rowCount()):
                        item = self.outmodel.item(i)
                        if item.text() in data['out']:
                            item.setCheckState(QtCore.Qt.Checked)
                    # views
                    for id, inv in data['section'].invpoints.items():
                        self.invmodel.appendRow(id, inv)
                    self.invview.resizeColumnsToContents()
                    for id, uni in data['section'].unilines.items():
                        self.unimodel.appendRow(id, uni)
                    self.uniview.resizeColumnsToContents()
                    if hasattr(data['section'], 'dogmins'):
                        for id, dgm in data['section'].dogmins.items():
                            self.dogmodel.appendRow(id, dgm)
                        self.dogview.resizeColumnsToContents()
                    self.ready = True
                    self.project = projfile
                    self.changed = False
                    if projfile in self.recent:
                        self.recent.pop(self.recent.index(projfile))
                    self.recent.insert(0, projfile)
                    if len(self.recent) > 15:
                        self.recent = self.recent[:15]
                    self.populate_recent()
                    self.app_settings(write=True)
                    self.refresh_gui()
                    if 'bulk' in data:
                        self.bulk = data['bulk']
                        self.tc.update_scriptfile(bulk=data['bulk'],
                                                  xsteps=self.spinSteps.value())
                        self.read_scriptfile()
                    else:
                        self.bulk = self.tc.bulk
                    self.statusBar().showMessage('Project loaded.')
                else:
                    qb = QtWidgets.QMessageBox
                    qb.critical(self, 'Error during openning', tc.status, qb.Abort)
            else:
                qb = QtWidgets.QMessageBox
                qb.critical(self, 'Error during openning', 'Unknown format of the project file', qb.Abort)
            QtWidgets.QApplication.restoreOverrideCursor()
        else:
            if projfile in self.recent:
                self.recent.pop(self.recent.index(projfile))
                self.app_settings(write=True)
                self.populate_recent()

    @property
    def plot_title(self):
        ex = list(self.ps.excess)
        ex.insert(0, '')
        return self.tc.axname + ' +'.join(ex) + ' (at {:g}°C)'.format(np.mean(self.tc.trange))

    def reset_limits(self):
        if self.ready:
            fmt = lambda x: '{:.{prec}f}'.format(x, prec=self.spinPrec.value())
            self.tminEdit.setText(fmt(0))
            self.tmaxEdit.setText(fmt(1))
            self.pminEdit.setText(fmt(self.tc.prange[0]))
            self.pmaxEdit.setText(fmt(self.tc.prange[1]))

    def uni_explore(self): ## TODO:
        if self.unisel.hasSelection():
            idx = self.unisel.selectedIndexes()
            uni = self.ps.unilines[self.unimodel.data(idx[0])]
            phases = uni.phases
            out = uni.out
            self.statusBar().showMessage('Searching for invariant points...')
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            # set guesses temporarily when asked
            if uni.connected == 1 and self.checkUseInvGuess.isChecked():
                inv_id = sorted([uni.begin, uni.end])[1]
                old_guesses = self.tc.update_scriptfile(guesses=self.ps.invpoints[inv_id].ptguess(), get_old_guesses=True)
            # Try out from phases
            extend = self.spinOver.value()
            trange = (max(self.tc.trange[0] - self.rangeSpin.value() / 2, 11),
                      self.tc.trange[1] + self.rangeSpin.value() / 2)
            prange = self.ax.get_ylim()
            ps = extend * (prange[1] - prange[0]) / 100
            prange = (max(prange[0] - ps, 0.01), prange[1] + ps)
            crange = self.ax.get_xlim()
            cs = extend * (crange[1] - crange[0]) / 100
            crange = (crange[0] - cs, crange[1] + cs)
            # change bulk
            bulk = self.tc.interpolate_bulk(crange)
            self.tc.update_scriptfile(bulk=bulk, xsteps=self.spinSteps.value(), xvals=crange)

            out_section = []
            cand = []
            for ophase in phases.difference(out).difference(self.ps.excess):
                nout = out.union(set([ophase]))
                self.tc.calc_px(phases, nout, prange = prange, trange=trange)
                status, variance, pts, ptcoords, res, output = self.tc.parse_logfile(tx=True)
                inv = InvPoint(phases=phases, out=nout)
                isnew, id = self.ps.getidinv(inv)
                if status == 'ok':
                    if isnew:
                        exists, inv_id = '', ''
                    else:
                        exists, inv_id = '*', str(id)
                    if len(res) > 1:
                        # rescale pts from zoomed composition
                        pts[1] = crange[0] + pts[1] * (crange[1] - crange[0])
                        tm = (self.tc.trange[0] + self.tc.trange[1]) / 2
                        splt = interp1d(ptcoords[1], ptcoords[0], bounds_error=False, fill_value=np.nan)
                        splx = interp1d(ptcoords[1], pts[1], bounds_error=False, fill_value=np.nan)
                        Ym = splt([tm])
                        Xm = splx([tm])
                        if not np.isnan(Ym[0]):
                            cand.append((Xm[0], Ym[0], exists, ' '.join(inv.out), inv_id))
                        else:
                            ix = abs(ptcoords[1] - tm).argmin()
                            out_section.append((ptcoords[1][ix], ptcoords[0][ix], exists, ' '.join(inv.out), inv_id))
                    else:
                        out_section.append((ptcoords[1][0], ptcoords[0][0], exists, ' '.join(inv.out), inv_id))

            for ophase in set(self.tc.phases).difference(self.ps.excess).difference(phases):
                nphases = phases.union(set([ophase]))
                nout = out.union(set([ophase]))
                self.tc.calc_px(nphases, nout, prange = prange, trange=trange)
                status, variance, pts, ptcoords, res, output = self.tc.parse_logfile(px=True)
                inv = InvPoint(phases=nphases, out=nout)
                isnew, id = self.ps.getidinv(inv)
                if status == 'ok':
                    if isnew:
                        exists, inv_id = '', ''
                    else:
                        exists, inv_id = '*', str(id)
                    if len(res) > 1:
                        # rescale pts from zoomed composition
                        pts[1] = crange[0] + pts[1] * (crange[1] - crange[0])
                        tm = (self.tc.trange[0] + self.tc.trange[1]) / 2
                        splt = interp1d(ptcoords[1], ptcoords[0], bounds_error=False, fill_value=np.nan)
                        splx = interp1d(ptcoords[1], pts[1], bounds_error=False, fill_value=np.nan)
                        Ym = splt([tm])
                        Xm = splx([tm])
                        if not np.isnan(Ym[0]):
                            cand.append((Xm[0], Ym[0], exists, ' '.join(inv.out), inv_id))
                        else:
                            ix = abs(ptcoords[1] - tm).argmin()
                            out_section.append((ptcoords[1][ix], ptcoords[0][ix], exists, ' '.join(inv.out), inv_id))
                    else:
                        out_section.append((ptcoords[1][0], ptcoords[0][0], exists, ' '.join(inv.out), inv_id))

            # set original ptguesses when asked
            if uni.connected == 1 and self.checkUseInvGuess.isChecked():
                self.tc.update_scriptfile(guesses=old_guesses)
            # restore bulk
            self.tc.update_scriptfile(bulk=self.bulk, xsteps=self.spinSteps.value())
            QtWidgets.QApplication.restoreOverrideCursor()
            txt = ''
            n_format = '{:10.4f}{:10.4f}{:>2}{:>8}{:>6}\n'
            if cand:
                txt += '         {}         {} E     Out   Inv\n'.format(self.ps.x_var, self.ps.y_var)
                for cc in sorted(cand, reverse=True):
                    txt += n_format.format(*cc)

                self.textOutput.setPlainText(txt)
                self.statusBar().showMessage('Searching done. Found {} invariant points.'.format(len(cand)))
            elif out_section:
                txt += 'Solutions with single point (need increase number of steps)\n'
                txt += '         T         p E     Out   Inv\n'.format(self.ps.x_var, self.ps.y_var)
                for cc in out_section:
                    txt += n_format.format(*cc)

                self.textOutput.setPlainText(txt)
                self.statusBar().showMessage('Searching done. Found {} invariant points and {} out of section.'.format(len(cand), len(out_section)))
            else:
                self.statusBar().showMessage('No invariant points found.')

    def dogminer(self, event):
        self.cid.onmove(event)
        if event.inaxes is not None:
            self.cid.clear(event)
            phases, out = self.get_phases_out()
            which = phases.difference(self.ps.excess)
            variance = self.spinVariance.value()
            doglevel = self.spinDoglevel.value()
            prec = self.spinPrec.value()
            # change bulk
            bulk = self.tc.interpolate_bulk(event.xdata)
            self.statusBar().showMessage('Running dogmin with max variance of equilibria at {}...'.format(variance))
            tm = (self.tc.trange[0] + self.tc.trange[1]) / 2
            self.tc.update_scriptfile(bulk=bulk,
                                      dogmin='yes {}'.format(doglevel), which=which,
                                      T='{:.{prec}f}'.format(tm, prec=prec),
                                      p='{:.{prec}f}'.format(event.ydata, prec=prec))
            #self.read_scriptfile()
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            tcout = self.tc.dogmin(variance)
            self.logText.setPlainText('Working directory:{}\n\n'.format(self.tc.workdir) + tcout)
            output, resic = self.tc.parse_dogmin()
            if output is not None:
                dgm = Dogmin(output=output, resic=resic, x=event.xdata, y=event.ydata)
                if dgm.phases:
                    id_dog = 0
                    for key in self.ps.dogmins:
                        id_dog = max(id_dog, key)
                    id_dog += 1
                    self.dogmodel.appendRow(id_dog, dgm)
                    self.dogview.resizeColumnsToContents()
                    self.changed = True
                    idx = self.dogmodel.getIndexID(id_dog)
                    self.dogview.selectRow(idx.row())
                    self.dogview.scrollToBottom()
                    self.plot()
                    self.statusBar().showMessage('Dogmin finished.')
                else:
                    self.statusBar().showMessage('Dogmin failed.')
            else:
                self.statusBar().showMessage('Dogmin failed.')
            # restore bulk
            self.tc.update_scriptfile(bulk=self.bulk, xsteps=self.spinSteps.value())
            self.pushDogmin.setChecked(False)

    def do_calc(self, calcT, phases={}, out={}):
        if self.ready:
            if phases == {} and out == {}:
                phases, out = self.get_phases_out()
            self.statusBar().showMessage('Running THERMOCALC...')
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            ###########
            extend = self.spinOver.value()
            trange = (max(self.tc.trange[0] - self.rangeSpin.value() / 2, 11),
                      self.tc.trange[1] + self.rangeSpin.value() / 2)
            prange = self.ax.get_ylim()
            ps = extend * (prange[1] - prange[0]) / 100
            prange = (max(prange[0] - ps, 0.01), prange[1] + ps)
            crange = self.ax.get_xlim()
            cs = extend * (crange[1] - crange[0]) / 100
            crange = (crange[0] - cs, crange[1] + cs)
            # change bulk
            bulk = self.tc.interpolate_bulk(crange)
            self.tc.update_scriptfile(bulk=bulk, xsteps=self.spinSteps.value(), xvals=crange)

            if len(out) == 1:
                uni_tmp = UniLine(phases=phases, out=out)
                isnew, id_uni = self.ps.getiduni(uni_tmp)
                tcout, ans = self.tc.calc_px(uni_tmp.phases, uni_tmp.out, prange=prange)
                self.logText.setPlainText('Working directory:{}\n\n'.format(self.tc.workdir) + tcout)
                status, variance, pts, ptcoords, res, output = self.tc.parse_logfile(px=True)
                if status == 'bombed':
                    self.statusBar().showMessage('Bombed.')
                elif status == 'nir':
                    self.statusBar().showMessage('Nothing in range.')
                elif len(res) < 2:
                    self.statusBar().showMessage('Only one point calculated. Change range.')
                else:
                    # rescale pts from zoomed composition
                    pts[1] = crange[0] + pts[1] * (crange[1] - crange[0])
                    uni = UniLine(id=id_uni, phases=uni_tmp.phases, out=uni_tmp.out, cmd=ans,
                                  variance=variance, y=pts[0], x=pts[1], output=output, results=res)
                    if self.checkAutoconnectUni.isChecked():
                        candidates = [inv for inv in self.ps.invpoints.values() if uni.contains_inv(inv)]
                    if isnew:
                        self.unimodel.appendRow(id_uni, uni)
                        self.uniview.resizeColumnsToContents()
                        self.changed = True
                        # self.unisel.select(idx, QtCore.QItemSelectionModel.ClearAndSelect | QtCore.QItemSelectionModel.Rows)
                        idx = self.unimodel.getIndexID(id_uni)
                        self.uniview.selectRow(idx.row())
                        self.uniview.scrollToBottom()
                        if self.checkAutoconnectUni.isChecked():
                            if len(candidates) == 2:
                                self.uni_connect(id_uni, candidates)
                        self.plot()
                        self.show_uni(idx)
                        self.statusBar().showMessage('New univariant line calculated.')
                    else:
                        if not self.checkOverwrite.isChecked():
                            uni.begin = self.ps.unilines[id_uni].begin
                            uni.end = self.ps.unilines[id_uni].end
                            self.ps.unilines[id_uni] = uni
                            self.ps.trim_uni(id_uni)
                            if self.checkAutoconnectUni.isChecked():
                                if len(candidates) == 2:
                                    self.uni_connect(id_uni, candidates)
                            self.changed = True
                            self.uniview.resizeColumnsToContents()
                            idx = self.unimodel.getIndexID(id_uni)
                            self.uniview.selectRow(idx.row())
                            self.plot()
                            self.show_uni(idx)
                            self.statusBar().showMessage('Univariant line {} re-calculated.'.format(id_uni))
                        else:
                            self.statusBar().showMessage('Univariant line already exists.')
            elif len(out) == 2:
                inv_tmp = InvPoint(phases=phases, out=out)
                isnew, id_inv = self.ps.getidinv(inv_tmp)
                tcout, ans = self.tc.calc_px(inv_tmp.phases, inv_tmp.out, prange = prange, trange=trange)
                self.logText.setPlainText('Working directory:{}\n\n'.format(self.tc.workdir) + tcout)
                status, variance, pts, ptcoords, res, output = self.tc.parse_logfile(px=True)
                if status == 'bombed':
                    self.statusBar().showMessage('Bombed.')
                elif status == 'nir':
                    self.statusBar().showMessage('Nothing in range.')
                elif len(res) < 2:
                    self.statusBar().showMessage('Only one point calculated. Change steps.')
                else:
                    # rescale pts from zoomed composition
                    pts[1] = crange[0] + pts[1] * (crange[1] - crange[0])
                    tm = (self.tc.trange[0] + self.tc.trange[1]) / 2
                    splp = interp1d(ptcoords[1], ptcoords[0], bounds_error=False, fill_value=np.nan)
                    splx = interp1d(ptcoords[1], pts[1], bounds_error=False, fill_value=np.nan)
                    Ym = splp([tm])
                    Xm = splx([tm])
                    if np.isnan(Ym[0]):
                        status = 'nir'
                        self.statusBar().showMessage('Nothing in range, but exists out ouf section in p range {:.2f} - {:.2f}.'.format(min(ptcoords[0]), max(ptcoords[0])))
                    else:
                        ix = np.argmin((ptcoords[0] - Ym)**2)
                        inv = InvPoint(id=id_inv, phases=inv_tmp.phases, out=inv_tmp.out, cmd=ans,
                                       variance=variance, y=Ym, x=Xm, output=output, results=res[ix:ix + 1])
                        if isnew:
                            self.invmodel.appendRow(id_inv, inv)
                            self.invview.resizeColumnsToContents()
                            self.changed = True
                            idx = self.invmodel.getIndexID(id_inv)
                            self.invview.selectRow(idx.row())
                            self.invview.scrollToBottom()
                            if self.checkAutoconnectInv.isChecked():
                                for uni in self.ps.unilines.values():
                                    if uni.contains_inv(inv):
                                        candidates = [inv]
                                        for other_inv in self.ps.invpoints.values():
                                            if other_inv.id != id_inv:
                                                if uni.contains_inv(other_inv):
                                                    candidates.append(other_inv)
                                        if len(candidates) == 2:
                                            self.uni_connect(uni.id, candidates)
                                            self.uniview.resizeColumnsToContents()
                            self.plot()
                            self.show_inv(idx)
                            self.statusBar().showMessage('New invariant point calculated.')
                        else:
                            if not self.checkOverwrite.isChecked():
                                self.ps.invpoints[id_inv] = inv
                                for uni in self.ps.unilines.values():
                                    if uni.begin == id_inv or uni.end == id_inv:
                                        self.ps.trim_uni(uni.id)
                                self.changed = True
                                self.invview.resizeColumnsToContents()
                                idx = self.invmodel.getIndexID(id_inv)
                                self.plot()
                                self.show_inv(idx)
                                self.statusBar().showMessage('Invariant point {} re-calculated.'.format(id_inv))
                            else:
                                self.statusBar().showMessage('Invariant point already exists.')
            else:
                self.statusBar().showMessage('{} zero mode phases selected. Select one or two!'.format(len(out)))
            #########
            # restore bulk
            self.tc.update_scriptfile(bulk=self.bulk, xsteps=self.spinSteps.value())
            QtWidgets.QApplication.restoreOverrideCursor()
        else:
            self.statusBar().showMessage('Project is not yet initialized.')


class InvModel(QtCore.QAbstractTableModel):
    def __init__(self, ps, parent, *args):
        super(InvModel, self).__init__(parent, *args)
        self.ps = ps
        self.invlist = []
        self.header = ['ID', 'Label']

    def rowCount(self, parent=None):
        return len(self.invlist)

    def columnCount(self, parent=None):
        return len(self.header)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        inv = self.ps.invpoints[self.invlist[index.row()]]
        # elif role == QtCore.Qt.ForegroundRole:
        #     if self.invlist[index.row()][self.header.index('Data')]['manual']:
        #         brush = QtGui.QBrush()
        #         brush.setColor(QtGui.QColor('red'))
        #         return brush
        if role == QtCore.Qt.FontRole:
            if inv.manual:
                font = QtGui.QFont()
                font.setItalic(True)
                return font
        elif role != QtCore.Qt.DisplayRole:
            return None
        else:
            if index.column() == 0:
                return self.invlist[index.row()]
            else:
                return inv.label(excess=self.ps.excess)

    def appendRow(self, id, inv):
        """ Append model row. """
        self.beginInsertRows(QtCore.QModelIndex(),
                             len(self.invlist), len(self.invlist))
        self.invlist.append(id)
        self.ps.add_inv(id, inv)
        self.endInsertRows()

    def removeRow(self, index):
        """ Remove model row. """
        self.beginRemoveRows(QtCore.QModelIndex(), index.row(), index.row())
        id = self.invlist[index.row()]
        del self.invlist[index.row()]
        del self.ps.invpoints[id]
        self.endRemoveRows()

    def headerData(self, col, orientation, role=QtCore.Qt.DisplayRole):
        if orientation == QtCore.Qt.Horizontal & role == QtCore.Qt.DisplayRole:
            return self.header[col]
        return None

    def getRowID(self, index):
        return self.invlist[index.row()]

    def getIndexID(self, id):
        return self.index(self.invlist.index(id), 0, QtCore.QModelIndex())


class UniModel(QtCore.QAbstractTableModel):
    def __init__(self, ps, parent, *args):
        super(UniModel, self).__init__(parent, *args)
        self.ps = ps
        self.unilist = []
        self.header = ['ID', 'Label', 'Begin', 'End']

    def rowCount(self, parent=None):
        return len(self.unilist)

    def columnCount(self, parent=None):
        return len(self.header)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        uni = self.ps.unilines[self.unilist[index.row()]]
        # elif role == QtCore.Qt.ForegroundRole:
        #     if self.unilist[index.row()][self.header.index('Data')]['manual']:
        #         brush = QtGui.QBrush()
        #         brush.setColor(QtGui.QColor('red'))
        #         return brush
        if role == QtCore.Qt.FontRole:
            if uni.manual:
                font = QtGui.QFont()
                font.setItalic(True)
                return font
            elif uni.begin == 0 and uni.end == 0:
                font = QtGui.QFont()
                font.setBold(True)
                return font
        elif role != QtCore.Qt.DisplayRole:
            return None
        else:
            if index.column() == 0:
                return self.unilist[index.row()]
            if index.column() == 2:
                return uni.begin
            if index.column() == 3:
                return uni.end
            else:
                return uni.label(excess=self.ps.excess)

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        # DO change and emit plot
        if role == QtCore.Qt.EditRole:
            uni = self.ps.unilines[self.unilist[index.row()]]
            if index.column() == 2:
                uni.begin = value
            if index.column() == 3:
                uni.end = value
            self.dataChanged.emit(index, index)
        return False

    def appendRow(self, id, uni):
        """ Append model row. """
        self.beginInsertRows(QtCore.QModelIndex(),
                             len(self.unilist), len(self.unilist))
        self.unilist.append(id)
        self.ps.add_uni(id, uni)
        self.endInsertRows()

    def removeRow(self, index):
        """ Remove model row. """
        self.beginRemoveRows(QtCore.QModelIndex(), index.row(), index.row())
        id = self.unilist[index.row()]
        del self.unilist[index.row()]
        del self.ps.unilines[id]
        self.endRemoveRows()

    def headerData(self, col, orientation, role=QtCore.Qt.DisplayRole):
        if orientation == QtCore.Qt.Horizontal & role == QtCore.Qt.DisplayRole:
            return self.header[col]
        return None

    def flags(self, index):
        if index.column() > 1:
            return QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        else:
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def getRowID(self, index):
        return self.unilist[index.row()]

    def getIndexID(self, id):
        return self.index(self.unilist.index(id), 0, QtCore.QModelIndex())


class ComboDelegate(QtWidgets.QItemDelegate):
    """
    A delegate that places a fully functioning QtWidgets.QComboBox in every
    cell of the column to which it's applied
    """
    def __init__(self, ps, invmodel, parent):
        super(ComboDelegate, self).__init__(parent)
        self.ps = ps
        self.invmodel = invmodel

    def createEditor(self, parent, option, index):
        #r = index.model().getData(index, 'Data')
        uni = self.ps.unilines[index.model().getRowID(index)]
        if index.column() == 2:
            other = uni.end
        else:
            other = uni.begin
        combomodel = QtGui.QStandardItemModel()
        if not uni.manual:
            item = QtGui.QStandardItem('0')
            item.setData(0, 1)
            combomodel.appendRow(item)
        # filter possible candidates
        for inv in self.ps.invpoints.values():
            if inv.id != other and uni.contains_inv(inv):
                item = QtGui.QStandardItem(inv.annotation())
                item.setData(inv.id, 1)
                combomodel.appendRow(item)
        combo = QtWidgets.QComboBox(parent)
        combo.setModel(combomodel)
        return combo

    def setEditorData(self, editor, index):
        editor.setCurrentText(str(index.model().data(index)))
        # auto open combobox
        #editor.showPopup()

    def setModelData(self, editor, model, index):
        new = editor.currentData(1)
        model.setData(index, int(new))


class DogminModel(QtCore.QAbstractTableModel):
    def __init__(self, ps, parent, *args):
        super(DogminModel, self).__init__(parent, *args)
        self.ps = ps
        self.doglist = []
        self.header = ['ID', 'Label']

    def rowCount(self, parent=None):
        return len(self.doglist)

    def columnCount(self, parent=None):
        return len(self.header)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        dgm = self.ps.dogmins[self.doglist[index.row()]]
        # elif role == QtCore.Qt.ForegroundRole:
        #     if self.invlist[index.row()][self.header.index('Data')]['manual']:
        #         brush = QtGui.QBrush()
        #         brush.setColor(QtGui.QColor('red'))
        #         return brush
        #if role == QtCore.Qt.FontRole:
        #    if inv.manual:
        #        font = QtGui.QFont()
        #        font.setItalic(True)
        #        return font
        if role != QtCore.Qt.DisplayRole:
            return None
        else:
            if index.column() == 0:
                return self.doglist[index.row()]
            else:
                return dgm.label(excess=self.ps.excess)

    def appendRow(self, id, dgm):
        """ Append model row. """
        self.beginInsertRows(QtCore.QModelIndex(),
                             len(self.doglist), len(self.doglist))
        self.doglist.append(id)
        self.ps.add_dogmin(id, dgm)
        self.endInsertRows()

    def removeRow(self, index):
        """ Remove model row. """
        self.beginRemoveRows(QtCore.QModelIndex(), index.row(), index.row())
        id = self.doglist[index.row()]
        del self.doglist[index.row()]
        del self.ps.dogmins[id]
        self.endRemoveRows()

    def headerData(self, col, orientation, role=QtCore.Qt.DisplayRole):
        if orientation == QtCore.Qt.Horizontal & role == QtCore.Qt.DisplayRole:
            return self.header[col]
        return None

    def getRowID(self, index):
        return self.doglist[index.row()]

    def getIndexID(self, id):
        return self.index(self.doglist.index(id), 0, QtCore.QModelIndex())


class AddInv(QtWidgets.QDialog, Ui_AddInv):
    """Add inv dialog class
    """
    def __init__(self, ps, inv, parent=None):
        super(AddInv, self).__init__(parent)
        self.setupUi(self)
        self.labelEdit.setText(inv.label(ps.excess))
        # labels
        self.x_label.setText(ps.x_var)
        self.y_label.setText(ps.y_var)
        # validator
        validator = QtGui.QDoubleValidator()
        validator.setLocale(QtCore.QLocale.c())
        self.xEdit.setValidator(validator)
        self.xEdit.textChanged.connect(self.check_validity)
        self.xEdit.textChanged.emit(self.xEdit.text())
        self.yEdit.setValidator(validator)
        self.yEdit.textChanged.connect(self.check_validity)
        self.yEdit.textChanged.emit(self.yEdit.text())

    def check_validity(self, *args, **kwargs):
        sender = self.sender()
        validator = sender.validator()
        state = validator.validate(sender.text(), 0)[0]
        if state == QtGui.QValidator.Acceptable:
            color = '#c4df9b'  # green
        elif state == QtGui.QValidator.Intermediate:
            color = '#fff79a'  # yellow
        else:
            color = '#f6989d'  # red
        sender.setStyleSheet('QLineEdit { background-color: %s }' % color)

    def set_from_event(self, event):
        self.xEdit.setText(str(event.xdata))
        self.yEdit.setText(str(event.ydata))

    def getValues(self):
        return np.array([float(self.xEdit.text())]), np.array([float(self.yEdit.text())])


class AddUni(QtWidgets.QDialog, Ui_AddUni):
    """Add uni dialog class
    """
    def __init__(self, label, items, selected=None, parent=None):
        super(AddUni, self).__init__(parent)
        self.setupUi(self)
        self.labelEdit.setText(label)
        self.combomodel = QtGui.QStandardItemModel()
        for item in items:
            it = QtGui.QStandardItem(str(item))
            it.setData(item, 1)
            self.combomodel.appendRow(it)
        self.comboBegin.setModel(self.combomodel)
        self.comboEnd.setModel(self.combomodel)
        if selected:
            if selected[0] in items:
                self.comboBegin.setCurrentIndex(items.index(selected[0]))
            if selected[1] in items:
                self.comboEnd.setCurrentIndex(items.index(selected[1]))

    def getValues(self):
        b = self.comboBegin.currentData(1)
        e = self.comboEnd.currentData(1)
        return b, e


class UniGuess(QtWidgets.QDialog, Ui_UniGuess):
    """Choose uni pt dialog class
    """
    def __init__(self, values, parent=None):
        super(UniGuess, self).__init__(parent)
        self.setupUi(self)
        self.comboPoint.addItems(values)

    def getValue(self):
        return self.comboPoint.currentIndex()


class AboutDialog(QtWidgets.QDialog):
    """About dialog
    """
    def __init__(self, builder, version, parent=None):
        """Display a dialog that shows application information."""
        super(AboutDialog, self).__init__(parent)

        self.setWindowTitle('About')
        self.resize(300, 100)

        title = QtWidgets.QLabel('{} {}'.format(builder, version))
        title.setAlignment(QtCore.Qt.AlignCenter)
        myFont = QtGui.QFont()
        myFont.setBold(True)
        title.setFont(myFont)

        suptitle = QtWidgets.QLabel('THERMOCALC front-end for constructing pseudosections')
        suptitle.setAlignment(QtCore.Qt.AlignCenter)

        author = QtWidgets.QLabel('Ondrej Lexa')
        author.setAlignment(QtCore.Qt.AlignCenter)

        swinfo = QtWidgets.QLabel('Python:{} Qt:{} PyQt:{}'.format(sys.version.split()[0], QT_VERSION_STR, PYQT_VERSION_STR))
        swinfo.setAlignment(QtCore.Qt.AlignCenter)

        github = QtWidgets.QLabel('GitHub: <a href="https://github.com/ondrolexa/pypsbuilder">https://github.com/ondrolexa/pypsbuilder</a>')
        github.setAlignment(QtCore.Qt.AlignCenter)
        github.setOpenExternalLinks(True)

        self.layout = QtWidgets.QVBoxLayout()
        self.layout.setAlignment(QtCore.Qt.AlignVCenter)

        self.layout.addWidget(title)
        self.layout.addWidget(suptitle)
        self.layout.addWidget(author)
        self.layout.addWidget(swinfo)
        self.layout.addWidget(github)

        self.setLayout(self.layout)


class OutputDialog(QtWidgets.QDialog):
    """Output dialog
    """
    def __init__(self, title, txt, parent=None):
        """Display a dialog that shows application information."""
        super(OutputDialog, self).__init__(parent)

        self.setWindowTitle(title)
        self.resize(800, 600)

        self.plainText = QtWidgets.QPlainTextEdit(self)
        self.plainText.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.plainText.setReadOnly(True)
        f = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.plainText.setFont(f)
        self.layout = QtWidgets.QVBoxLayout()
        self.layout.setAlignment(QtCore.Qt.AlignVCenter)
        self.layout.addWidget(self.plainText)
        self.setLayout(self.layout)
        self.plainText.setPlainText(txt)


class TopologyGraph(QtWidgets.QDialog):
    def __init__(self, ps, parent=None):
        super(TopologyGraph, self).__init__(parent)
        self.setWindowTitle('Topology graph')
        window_icon = resource_filename('pypsbuilder', 'images/pypsbuilder.png')
        self.setWindowIcon(QtGui.QIcon(window_icon))
        self.setWindowFlags(QtCore.Qt.WindowMinMaxButtonsHint | QtCore.Qt.WindowCloseButtonHint)
        self.figure = Figure(facecolor='white')
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setParent(self)
        self.canvas.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.toolbar = NavigationToolbar(self.canvas, self)
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.canvas)
        layout.addWidget(self.toolbar)
        self.setLayout(layout)

        import networkx as nx

        self.figure.clear()
        ax = self.figure.add_subplot(111)

        G = nx.Graph()
        pos = {}
        labels = {}
        for inv in ps.invpoints.values():
            G.add_node(inv.id)
            pos[inv.id] = inv._x, inv._y
            labels[inv.id] = inv.annotation()

        edges = {}
        for uni in ps.unilines.values():
            if uni.begin != 0 and uni.end != 0:
                out = frozenset(uni.out)
                G.add_edge(uni.begin, uni.end, out=list(out)[0])
                if out in edges:
                    edges[out].append((uni.begin, uni.end))
                else:
                    edges[out] = [(uni.begin, uni.end)]

        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore",category=FutureWarning)
            npos = nx.kamada_kawai_layout(G, pos=nx.planar_layout(G))
        #npos = nx.planar_layout(G)
        #npos = nx.kamada_kawai_layout(G, pos=pos)
        widths = Normalize(vmin=0, vmax=len(edges))
        color = cm.get_cmap('tab20', len(edges))
        for ix, out in enumerate(edges):
            nx.draw_networkx_edges(G, npos, ax=ax, edgelist=edges[out],
                                   width=2 + 6*widths(ix), alpha=0.5, edge_color=len(edges[out]) * [color(ix)], label=list(out)[0])

        nx.draw_networkx_nodes(G, npos, ax=ax, node_color='k')
        nx.draw_networkx_labels(G, npos, labels, ax=ax, font_size=12, font_weight='bold', font_color='w')

        # Shrink current axis by 20%
        self.figure.tight_layout()
        box = ax.get_position()
        ax.set_position([box.x0, box.y0, box.width * 0.85, box.height])

        # Put a legend to the right of the current axis
        ax.legend(loc='center left', bbox_to_anchor=(1, 0.5))
        # refresh canvas
        self.canvas.draw()

def intersection(uni1, uni2, ratio=1, extra=0.2, N=100):
    """
    INTERSECTIONS Intersections of two unilines.
       Computes the (x,y) locations where two unilines intersect.

    Based on: Sukhbinder
    https://github.com/sukhbinder/intersection
    """
    def _rect_inter_inner(x1, x2):
        n1 = x1.shape[0] - 1
        n2 = x2.shape[0] - 1
        X1 = np.c_[x1[:-1], x1[1:]]
        X2 = np.c_[x2[:-1], x2[1:]]
        S1 = np.tile(X1.min(axis=1), (n2, 1)).T
        S2 = np.tile(X2.max(axis=1), (n1, 1))
        S3 = np.tile(X1.max(axis=1), (n2, 1)).T
        S4 = np.tile(X2.min(axis=1), (n1, 1))
        return S1, S2, S3, S4

    def _rectangle_intersection_(x1, y1 ,x2, y2):
        S1, S2, S3, S4 = _rect_inter_inner(x1, x2)
        S5, S6, S7, S8 = _rect_inter_inner(y1, y2)

        C1 = np.less_equal(S1, S2)
        C2 = np.greater_equal(S3, S4)
        C3 = np.less_equal(S5, S6)
        C4 = np.greater_equal(S7, S8)

        ii, jj = np.nonzero(C1 & C2 & C3 & C4)
        return ii, jj

    # Linear length along the line:
    d1 = np.cumsum(np.sqrt(np.diff(uni1._x)**2 + np.diff(ratio*uni1._y)**2))
    d1 = np.insert(d1, 0, 0)/d1[-1]
    d2 = np.cumsum(np.sqrt(np.diff(uni2._x)**2 + np.diff(ratio*uni2._y)**2))
    d2 = np.insert(d2, 0, 0)/d2[-1]
    try:
        s1x = interp1d(d1, uni1._x, kind='quadratic', fill_value='extrapolate')
        s1y = interp1d(d1, ratio*uni1._y, kind='quadratic', fill_value='extrapolate')
        s2x = interp1d(d2, uni2._x, kind='quadratic', fill_value='extrapolate')
        s2y = interp1d(d2, ratio*uni2._y, kind='quadratic', fill_value='extrapolate')
    except ValueError:
        s1x = interp1d(d1, uni1._x, fill_value='extrapolate')
        s1y = interp1d(d1, ratio*uni1._y, fill_value='extrapolate')
        s2x = interp1d(d2, uni2._x, fill_value='extrapolate')
        s2y = interp1d(d2, ratio*uni2._y, fill_value='extrapolate')
    p = np.linspace(-extra, 1 + extra, N)
    x1, y1 = s1x(p), s1y(p)
    x2, y2 = s2x(p), s2y(p)

    ii,jj=_rectangle_intersection_(x1, y1, x2, y2)
    n=len(ii)

    dxy1 = np.diff(np.c_[x1, y1], axis=0)
    dxy2 = np.diff(np.c_[x2, y2], axis=0)

    T = np.zeros((4, n))
    AA = np.zeros((4, 4, n))
    AA[0:2, 2, :] = -1
    AA[2:4, 3, :] = -1
    AA[0::2, 0, :] = dxy1[ii, :].T
    AA[1::2, 1, :] = dxy2[jj, :].T

    BB = np.zeros((4, n))
    BB[0, :] = -x1[ii].ravel()
    BB[1, :] = -x2[jj].ravel()
    BB[2, :] = -y1[ii].ravel()
    BB[3, :] = -y2[jj].ravel()

    for i in range(n):
        try:
            T[:, i] = np.linalg.solve(AA[:, :, i], BB[:, i])
        except:
            T[:, i] = np.NaN


    in_range= (T[0, :] >= 0) & (T[1, :] >= 0) & (T[0, :] <= 1) & (T[1, :] <= 1)

    xy0 = T[2:, in_range]
    xy0 = xy0.T
    return xy0[:, 0], xy0[:, 1] / ratio

def psbuilder():
    application = QtWidgets.QApplication(sys.argv)
    window = PSBuilder()
    desktop = QtWidgets.QDesktopWidget().availableGeometry()
    width = (desktop.width() - window.width()) / 2
    height = (desktop.height() - window.height()) / 2
    window.show()
    window.move(width, height)
    sys.exit(application.exec_())

def txbuilder():
    application = QtWidgets.QApplication(sys.argv)
    window = TXBuilder()
    desktop = QtWidgets.QDesktopWidget().availableGeometry()
    width = (desktop.width() - window.width()) / 2
    height = (desktop.height() - window.height()) / 2
    window.show()
    window.move(width, height)
    sys.exit(application.exec_())

def pxbuilder():
    application = QtWidgets.QApplication(sys.argv)
    window = PXBuilder()
    desktop = QtWidgets.QDesktopWidget().availableGeometry()
    width = (desktop.width() - window.width()) / 2
    height = (desktop.height() - window.height()) / 2
    window.show()
    window.move(width, height)
    sys.exit(application.exec_())
