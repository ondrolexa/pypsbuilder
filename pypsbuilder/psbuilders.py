"""Visual pseudosection builder for THERMOCALC."""
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
    NavigationToolbar2QT as NavigationToolbar,
)

# from matplotlib.widgets import Cursor
from matplotlib import cm
from matplotlib.colors import ListedColormap, BoundaryNorm, Normalize
from shapely.geometry import Point, LineString, Polygon
from scipy.interpolate import interp1d

try:
    import networkx as nx

    NX_OK = True
except ImportError:
    NX_OK = False

from .ui_ptbuilder import Ui_PTBuilder
from .ui_txbuilder import Ui_TXBuilder
from .ui_pxbuilder import Ui_PXBuilder
from .ui_addinv import Ui_AddInv
from .ui_adduni import Ui_AddUni
from .ui_uniguess import Ui_UniGuess
from .psclasses import (
    InvPoint,
    UniLine,
    polymorphs,
    PTsection,
    TXsection,
    PXsection,
    Dogmin,
    TCResult,
    TCResultSet,
    PolygonPatch,
)
from .tcapi import get_tcapi
from . import __version__

# Make sure that we are using QT5
matplotlib.use('Qt5Agg')

matplotlib.rcParams['xtick.direction'] = 'out'
matplotlib.rcParams['ytick.direction'] = 'out'

unihigh_kw = dict(lw=3, alpha=1, marker='o', ms=4, color='red', zorder=10)
invhigh_kw = dict(alpha=1, ms=8, color='red', zorder=10)
outhigh_kw = dict(lw=3, alpha=1, marker=None, ms=4, color='red', zorder=10)
presenthigh_kw = dict(lw=9, alpha=0.6, marker=None, ms=4, color='grey', zorder=-10)


def fmt(x):
    """Format number."""
    return '{:g}'.format(x)


app_icons = dict(PTBuilder='images/ptbuilder.png', TXBuilder='images/txbuilder.png', PXBuilder='images/pxbuilder.png')


class BuildersBase(QtWidgets.QMainWindow):
    """Main base class for pseudosection builders."""

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
        self.did = None

        # Create figure
        self.figure = Figure(facecolor='white')
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setParent(self.tabPlot)
        self.canvas.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.mplvl.addWidget(self.canvas)
        self.toolbar = NavigationToolbar(self.canvas, self.tabPlot, coordinates=True)
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
        self.statusBar().showMessage('{} version {} (c) Ondrej Lexa 2021'.format(self.builder_name, __version__))

    def initViewModels(self):
        # INVVIEW
        self.invmodel = InvModel(self.ps, self.invview)
        self.invview.setModel(self.invmodel)
        # enable sorting
        self.invview.setSortingEnabled(False)
        # select rows
        self.invview.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.invview.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.invview.horizontalHeader().setMinimumSectionSize(40)
        self.invview.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.invview.horizontalHeader().hide()
        self.invsel = self.invview.selectionModel()
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
        self.uniview.setEditTriggers(
            QtWidgets.QAbstractItemView.CurrentChanged | QtWidgets.QAbstractItemView.SelectedClicked
        )
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
        self.actionAbout.triggered.connect(self.about_dialog.exec)
        self.actionImport_project.triggered.connect(self.import_from_prj)
        self.actionCleanup.triggered.connect(self.cleanup_storage)
        self.actionFixphase.triggered.connect(self.fix_phasenames)
        self.actionShow_areas.triggered.connect(self.check_prj_areas)
        self.actionShow_topology.triggered.connect(self.show_topology)
        self.actionParse_working_directory.triggered.connect(lambda: self.do_calc(True, run_tc=False))
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
        self.pushMerge.setCheckable(True)
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
            tc, ok = get_tcapi(self.tc.workdir)
            if ok:
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
                qb.critical(self, 'Initialization error', tc, qb.Abort)
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
        if self.cid is not None:
            self.canvas.mpl_disconnect(self.cid)
            self.cid = None
            self.pushManual.setChecked(False)
        if self.did is not None:
            self.canvas.mpl_disconnect(self.did)
            self.did = None
            self.pushDogmin.setChecked(False)
        self.logText.setPlainText('Working directory:{}\n\n'.format(self.tc.workdir) + self.tc.tcout)
        self.phasemodel.clear()
        self.outmodel.clear()
        self.logDogmin.clear()
        for p in sorted(self.tc.phases - self.ps.excess):
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
        self.tabMain.setCurrentIndex(0)
        self.statusBar().showMessage('Ready')

    def import_from_old(self):  # FIXME:
        if self.ready:
            qd = QtWidgets.QFileDialog
            projfile = qd.getOpenFileName(
                self, 'Import from project', str(self.tc.workdir), 'PSBuilder 1.X project (*.psb)'
            )[0]
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
                id_lookup = {0: 0}
                for row in data['invlist']:
                    inv = InvPoint(
                        phases=row[2]['phases'].union(self.ps.excess),
                        out=row[2]['out'],
                        x=row[2]['T'],
                        y=row[2]['p'],
                        cmd=row[2].get('cmd', ''),
                        results=row[2].get('results', [dict(data=None, ptguess=None)]),
                        manual=True,
                        output='Imported invariant point.',
                    )
                    isnew, id_inv = self.ps.getidinv(inv)
                    id_lookup[row[0]] = id_inv
                    if isnew:
                        self.invmodel.appendRow(id_inv, inv)
                self.invview.resizeColumnsToContents()
                for row in data['unilist']:
                    uni = UniLine(
                        phases=row[4]['phases'].union(self.ps.excess),
                        out=row[4]['out'],
                        x=row[4]['T'],
                        y=row[4]['p'],
                        cmd=row[4].get('cmd', ''),
                        results=row[4].get('results', [dict(data=None, ptguess=None)]),
                        manual=True,
                        output='Imported univariant line.',
                        begin=id_lookup[row[2]],
                        end=id_lookup[row[3]],
                    )
                    isnew, id_uni = self.ps.getiduni(uni)
                    if isnew:
                        self.unimodel.appendRow(id_uni, uni)
                self.uniview.resizeColumnsToContents()
                # # try to recalc
                progress = QtWidgets.QProgressDialog(
                    "Recalculate inv points", "Cancel", 0, len(self.ps.invpoints), self
                )
                progress.setWindowModality(QtCore.Qt.WindowModal)
                progress.setMinimumDuration(0)
                old_guesses = self.tc.update_scriptfile(get_old_guesses=True)
                for ix, inv in enumerate(self.ps.invpoints.values()):
                    progress.setValue(ix)
                    if inv.cmd and inv.output == 'Imported invariant point.':
                        if inv.ptguess():
                            self.tc.update_scriptfile(guesses=inv.ptguess())
                        self.tc.runtc(inv.cmd)
                        status, res, output = self.tc.parse_logfile()
                        if status == 'ok':
                            self.ps.invpoints[inv.id].variance = res.variance
                            self.ps.invpoints[inv.id].x = res.x
                            self.ps.invpoints[inv.id].y = res.y
                            self.ps.invpoints[inv.id].output = output
                            self.ps.invpoints[inv.id].results = res
                            self.ps.invpoints[inv.id].manual = False
                    if progress.wasCanceled():
                        break
                progress.setValue(len(self.ps.invpoints))
                progress.deleteLater()
                self.invview.resizeColumnsToContents()
                progress = QtWidgets.QProgressDialog("Recalculate uni lines", "Cancel", 0, len(self.ps.unilines), self)
                progress.setWindowModality(QtCore.Qt.WindowModal)
                progress.setMinimumDuration(0)
                for ix, uni in enumerate(self.ps.unilines.values()):
                    progress.setValue(ix)
                    if uni.cmd and uni.output == 'Imported univariant line.':
                        if uni.ptguess():
                            self.tc.update_scriptfile(guesses=uni.ptguess())
                        self.tc.runtc(uni.cmd)
                        status, res, output = self.tc.parse_logfile()
                        if status == 'ok':
                            if len(res) > 1:
                                self.ps.unilines[uni.id].variance = res.variance
                                self.ps.unilines[uni.id]._x = res.x
                                self.ps.unilines[uni.id]._y = res.y
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

    def import_from_prj(self):
        if self.ready:
            qd = QtWidgets.QFileDialog
            projfile = qd.getOpenFileName(
                self, 'Import from project', str(self.tc.workdir), self.builder_file_selector
            )[0]
            if Path(projfile).is_file():
                with gzip.open(projfile, 'rb') as stream:
                    data = pickle.load(stream)
                if 'section' in data:  # NEW
                    workdir = Path(data.get('workdir', Path(projfile).resolve().parent)).resolve()
                    if workdir == self.tc.workdir:
                        bnd, area = self.ps.range_shapes
                        # views
                        id_lookup = {0: 0}
                        for id, inv in data['section'].invpoints.items():
                            if area.intersects(inv.shape()):
                                isnew, id_inv = self.ps.getidinv(inv)
                                if isnew:
                                    id_lookup[id] = id_inv
                                    inv.id = id_inv
                                    self.invmodel.appendRow(id_inv, inv)
                        self.invview.resizeColumnsToContents()
                        for id, uni in data['section'].unilines.items():
                            if area.intersects(uni.shape()):
                                isnew, id_uni = self.ps.getiduni(uni)
                                if isnew:
                                    uni.id = id_uni
                                    uni.begin = id_lookup.get(uni.begin, 0)
                                    uni.end = id_lookup.get(uni.end, 0)
                                    self.unimodel.appendRow(id_uni, uni)
                                    self.ps.trim_uni(id_uni)
                        self.uniview.resizeColumnsToContents()
                        # if hasattr(data['section'], 'dogmins'):
                        #    for id, dgm in data['section'].dogmins.items():
                        #        self.dogmodel.appendRow(id, dgm)
                        #    self.dogview.resizeColumnsToContents()
                        self.changed = True
                        self.refresh_gui()
                        self.statusBar().showMessage('Data imported.')
                    else:
                        qb = QtWidgets.QMessageBox
                        qb.critical(
                            self,
                            'Workdir error',
                            'You can import only from projects with same working directory',
                            qb.Abort,
                        )
                else:
                    qb = QtWidgets.QMessageBox
                    qb.critical(self, 'Error during openning', 'Unknown format of the project file', qb.Abort)

    def cleanup_storage(self):
        if self.ready:
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Remove redundant calculations', 'Are you sure?', qb.Yes, qb.No)
            if reply == qb.Yes:
                self.ps.cleanup_data()
                self.changed = True
                self.refresh_gui()
                self.statusBar().showMessage('Unilines cleaned.')
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def fix_phasenames(self):
        if self.ready:
            used_phases = set()
            for inv in self.ps.invpoints.values():
                used_phases.update(inv.phases)
            for uni in self.ps.unilines.values():
                used_phases.update(uni.phases)
            for old_phase in used_phases.difference(set(self.tc.phases)):
                text, ok = QtWidgets.QInputDialog.getText(
                    self, 'Replace {} with'.format(old_phase), 'Enter new name (- to remove):'
                )
                try:
                    if ok:
                        new_phase = str(text).strip()
                        if new_phase == '-':
                            for inv in self.ps.invpoints.values():
                                if old_phase in inv.out:
                                    qb = QtWidgets.QMessageBox
                                    qb.critical(
                                        self,
                                        '{} is used as zeromode phase and cannot be deleted.',
                                        self.tc.status,
                                        qb.Abort,
                                    )
                                    raise ValueError()
                                if old_phase in inv.phases:
                                    inv.phases.remove(old_phase)
                                    if not inv.manual:
                                        if old_phase in inv.results.phases:
                                            for res in inv.results.results:
                                                del res.data[old_phase]
                            for uni in self.ps.unilines.values():
                                if old_phase in uni.out:
                                    qb = QtWidgets.QMessageBox
                                    qb.critical(
                                        self,
                                        '{} is used as zeromode phase and cannot be deleted.',
                                        self.tc.status,
                                        qb.Abort,
                                    )
                                    raise ValueError()
                                if old_phase in uni.phases:
                                    uni.phases.remove(old_phase)
                                    if not uni.manual:
                                        if old_phase in uni.results.phases:
                                            for res in uni.results.results:
                                                del res.data[old_phase]
                        else:
                            for inv in self.ps.invpoints.values():
                                if old_phase in inv.phases:
                                    inv.phases.remove(old_phase)
                                    inv.phases.add(new_phase)
                                    if not inv.manual:
                                        if old_phase in inv.results.phases:
                                            inv.results.rename_phase(old_phase, new_phase)
                                if old_phase in inv.out:
                                    inv.out.remove(old_phase)
                                    inv.out.add(new_phase)
                            for uni in self.ps.unilines.values():
                                if old_phase in uni.phases:
                                    uni.phases.remove(old_phase)
                                    uni.phases.add(new_phase)
                                    if not uni.manual:
                                        if old_phase in uni.results.phases:
                                            uni.results.rename_phase(old_phase, new_phase)
                                if old_phase in uni.out:
                                    uni.out.remove(old_phase)
                                    uni.out.add(new_phase)
                        self.changed = True
                except ValueError:
                    pass

            self.refresh_gui()
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def saveProject(self):
        """Save active project to project file"""
        if self.ready:
            if self.project is None:
                filename = QtWidgets.QFileDialog.getSaveFileName(
                    self, 'Save current project', str(self.tc.workdir), self.builder_file_selector
                )[0]
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
        """Save active project to project file with new filename"""
        if self.ready:
            filename = QtWidgets.QFileDialog.getSaveFileName(
                self, 'Save current project as', str(self.tc.workdir), self.builder_file_selector
            )[0]
            if filename:
                if not filename.lower().endswith(self.builder_extension):
                    filename = filename + self.builder_extension
                self.project = filename
                self.do_save()
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def do_save(self):
        """Open working directory and initialize project"""
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
        data = {
            'selphases': selphases,
            'out': out,
            'section': self.ps,
            'tcversion': self.tc.tcversion,
            'workdir': str(self.tc.workdir),
            'bulk': self.bulk,
            'datetime': datetime.now(),
            'version': __version__,
        }
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
            except Exception:
                pass
            self.unihigh = None
            self.textOutput.clear()
            self.textFullOutput.clear()
        if self.invhigh is not None:
            try:
                self.invhigh[0].remove()
            except Exception:
                pass
            self.invhigh = None
            self.textOutput.clear()
            self.textFullOutput.clear()
        if self.outhigh is not None:
            try:
                self.outhigh[0].remove()
            except Exception:
                pass
            self.outhigh = None
        if self.presenthigh is not None:
            try:
                self.presenthigh[0].remove()
            except Exception:
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
                lbl = ['{}={:g} {}={:g}'.format(self.ps.x_var, x, self.ps.y_var, y) for x, y in zip(uni._x, uni._y)]
                uniguess = UniGuess(lbl, self)
                respond = uniguess.exec()
                if respond == QtWidgets.QDialog.Accepted:
                    ix = uniguess.getValue()
                    self.tc.update_scriptfile(guesses=uni.ptguess(idx=ix))
                    self.read_scriptfile()
                    self.statusBar().showMessage(
                        'Univariant line ptguess set for {}'.format(self.format_coord(uni._x[ix], uni._y[ix]))
                    )
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

    def set_phaselist(self, r, show_output=True, useguess=False):
        for i in range(self.phasemodel.rowCount()):
            item = self.phasemodel.item(i)
            if item.text() in r.phases:  # or item.text() in r.out:
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
                        row = [x, y] + [res[lbl]['mode'] for lbl in mlabels]
                        txt += n_format.format(*row)
                        txt += '\n'
                        nln += 1
                    for x, y, res in zip(r._x[r.used], r._y[r.used], r.results[r.used]):
                        row = [x, y] + [res[lbl]['mode'] for lbl in mlabels]
                        txt += n_format.format(*row)
                        txt += '\n'
                    if r.end > 0 and not self.ps.invpoints[r.end].manual:
                        x, y = self.ps.invpoints[r.end]._x, self.ps.invpoints[r.end]._y
                        res = self.ps.invpoints[r.end].results[0]
                        row = [x, y] + [res[lbl]['mode'] for lbl in mlabels]
                        txt += n_format.format(*row)
                        txt += '\n'
                        nln += 1
                    if len(r.results[r.used]) > (5 - nln):
                        txt += h_format.format(self.ps.x_var, self.ps.y_var, *mlabels)
                else:
                    for x, y, res in zip(r.x, r.y, r.results):
                        row = [x, y] + [res[lbl]['mode'] for lbl in mlabels]
                        txt += n_format.format(*row)
                        txt += '\n'
                self.textOutput.setPlainText(txt)
            else:
                self.textOutput.setPlainText(r.output)
            self.textFullOutput.setPlainText(r.output)
        if useguess:
            self.invsel_guesses()

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
            self.outhigh = self.ax.plot(np.concatenate(ox), np.concatenate(oy), '-', **outhigh_kw)
        if px:
            self.presenthigh = self.ax.plot(np.concatenate(px), np.concatenate(py), '-', **presenthigh_kw)
        self.canvas.draw()

    def invviewRightClicked(self, QPos):
        if self.invsel.hasSelection():
            idx = self.invsel.selectedIndexes()
            inv_id = self.invmodel.getRowID(idx[0])
            inv = self.ps.invpoints[inv_id]
            all_uni = inv.all_unilines()
            show_menu = False
            menu = QtWidgets.QMenu(self.uniview)
            u1 = UniLine(phases=all_uni[0][0], out=all_uni[0][1])
            isnew, id = self.ps.getiduni(u1)
            if isnew:
                menu_item1 = menu.addAction(u1.label(excess=self.ps.excess))
                menu_item1.triggered.connect(
                    lambda: self.set_phaselist(u1, show_output=False, useguess=self.checkUseInvGuess.isChecked())
                )
                show_menu = True
            u2 = UniLine(phases=all_uni[1][0], out=all_uni[1][1])
            isnew, id = self.ps.getiduni(u2)
            if isnew:
                menu_item2 = menu.addAction(u2.label(excess=self.ps.excess))
                menu_item2.triggered.connect(
                    lambda: self.set_phaselist(u2, show_output=False, useguess=self.checkUseInvGuess.isChecked())
                )
                show_menu = True
            u3 = UniLine(phases=all_uni[2][0], out=all_uni[2][1])
            isnew, id = self.ps.getiduni(u3)
            if isnew:
                menu_item1 = menu.addAction(u3.label(excess=self.ps.excess))
                menu_item1.triggered.connect(
                    lambda: self.set_phaselist(u3, show_output=False, useguess=self.checkUseInvGuess.isChecked())
                )
                show_menu = True
            u4 = UniLine(phases=all_uni[3][0], out=all_uni[3][1])
            isnew, id = self.ps.getiduni(u4)
            if isnew:
                menu_item1 = menu.addAction(u4.label(excess=self.ps.excess))
                menu_item1.triggered.connect(
                    lambda: self.set_phaselist(u4, show_output=False, useguess=self.checkUseInvGuess.isChecked())
                )
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
            if self.unihigh is not None:
                menu_item3 = menu.addAction('Remove nodes')
                menu_item3.triggered.connect(lambda: self.remove_from_uni(uni))
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
        # also highlight
        self.clean_high()
        self.set_phaselist(uni, show_output=True)
        self.unihigh = self.ax.plot(uni.x, uni.y, '-', **unihigh_kw)
        self.canvas.draw()

    def remove_from_uni(self, uni):
        xrange = self.ax.get_xlim()
        yrange = self.ax.get_ylim()
        area = Polygon([(xrange[0], yrange[0]), (xrange[1], yrange[0]), (xrange[1], yrange[1]), (xrange[0], yrange[1])])
        idx = []
        for ix, x, y in zip(range(len(uni._x)), uni._x, uni._y):
            if not Point(x, y).within(area):
                idx.append(ix)
        if len(idx) > 1:
            uni._x = uni._x[idx]
            uni._y = uni._y[idx]
            uni.results = uni.results[idx]
            self.ps.trim_uni(uni.id)
            self.changed = True
            self.plot()

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
                reply = qb.question(self, 'Remove invariant point', msg, qb.Yes, qb.No)
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
                self.statusBar().showMessage(
                    'Cannot delete invariant point, which define user-defined univariant line.'
                )

    def remove_uni(self):
        if self.unisel.hasSelection():
            idx = self.unisel.selectedIndexes()
            msg = '{}\nAre you sure?'.format(self.unimodel.data(idx[1]))
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Remove univariant line', msg, qb.Yes, qb.No)
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
            reply = qb.question(self, 'Remove dogmin result', msg, qb.Yes, qb.No)
            if reply == qb.Yes:
                self.logDogmin.clear()
                self.dogmodel.removeRow(idx[0])
                self.changed = True
                self.plot()
                self.statusBar().showMessage('Dogmin result removed')

    def add_userdefined(self, checked=True):
        if self.ready:
            if self.did is not None:
                self.canvas.mpl_disconnect(self.did)
                self.did = None
                self.pushDogmin.setChecked(False)
            phases, out = self.get_phases_out()
            if len(out) == 1:
                if checked:
                    uni = UniLine(
                        phases=phases,
                        out=out,
                        x=np.array([]),
                        y=np.array([]),
                        manual=True,
                        output='User-defined univariant line.',
                    )
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
                    inv = InvPoint(phases=phases, out=out, manual=True, output='User-defined invariant point.')
                    unis = [uni for uni in self.ps.unilines.values() if uni.contains_inv(inv) and not uni.manual]
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
                            reply = qb.question(self, 'Add manual invariant point', msg, qb.Yes, qb.No)
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
                        # cancel zoom and pan action on toolbar
                        if self.toolbar.mode.name == "PAN":
                            self.toolbar.pan()
                        elif self.toolbar.mode.name == "ZOOM":
                            self.toolbar.zoom()
                        self.cid = self.canvas.mpl_connect('button_press_event', self.clicker)
                        self.tabMain.setCurrentIndex(0)
                        self.statusBar().showMessage('Click on canvas to add invariant point.')
                        QtWidgets.QApplication.processEvents()
                        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CrossCursor)
                else:
                    self.statusBar().showMessage('')
                    if self.cid is not None:
                        self.canvas.mpl_disconnect(self.cid)
                        self.cid = None
                        self.pushManual.setChecked(False)
                    QtWidgets.QApplication.restoreOverrideCursor()
            else:
                self.statusBar().showMessage(
                    'Select exactly one out phase for univariant line or two phases for invariant point.'
                )
                self.pushManual.setChecked(False)
        else:
            self.statusBar().showMessage('Project is not yet initialized.')
            self.pushManual.setChecked(False)

    def clicker(self, event):
        if event.inaxes is not None:
            phases, out = self.get_phases_out()
            inv = InvPoint(phases=phases, out=out, manual=True, output='User-defined invariant point.')
            isnew, id_inv = self.ps.getidinv(inv)
            addinv = AddInv(self.ps, inv, isnew, parent=self)
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
                    if addinv.checkKeep.isChecked():
                        self.ps.invpoints[id_inv].x = inv.x
                        self.ps.invpoints[id_inv].y = inv.y
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
        """Catch exit of app."""
        if self.changed:
            quit_msg = 'Project have been changed. Save ?'
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Message', quit_msg, qb.Cancel | qb.Discard | qb.Save, qb.Save)

            if reply == qb.Save:
                self.saveProject()
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
            if (1 << 0) & bitopt:
                if (float(self.tminEdit.text()), float(self.tmaxEdit.text())) != self.ps.xrange:
                    self.ps.xrange = (float(self.tminEdit.text()), float(self.tmaxEdit.text()))
                    self.changed = True
                if (float(self.pminEdit.text()), float(self.pmaxEdit.text())) != self.ps.yrange:
                    self.ps.yrange = (float(self.pminEdit.text()), float(self.pmaxEdit.text()))
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
        """Manage phases in outmodel based on selection in phase model."""
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
            if self.cid is not None:
                self.canvas.mpl_disconnect(self.cid)
                self.cid = None
                self.pushManual.setChecked(False)
            if checked:
                phases, out = self.get_phases_out()
                which = phases.difference(self.ps.excess)
                if which:
                    # cancel zoom and pan action on toolbar
                    if self.toolbar.mode.name == "PAN":
                        self.toolbar.pan()
                    elif self.toolbar.mode.name == "ZOOM":
                        self.toolbar.zoom()
                    self.did = self.canvas.mpl_connect('button_press_event', self.dogminer)
                    self.tabMain.setCurrentIndex(0)
                    self.statusBar().showMessage('Click on canvas to run dogmin at this point.')
                    QtWidgets.QApplication.processEvents()
                    QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CrossCursor)
                else:
                    self.statusBar().showMessage('You need to select phases to consider for dogmin.')
                    self.pushDogmin.setChecked(False)
            else:
                if self.did is not None:
                    self.canvas.mpl_disconnect(self.did)
                    self.did = None
                    self.pushDogmin.setChecked(False)
                QtWidgets.QApplication.restoreOverrideCursor()
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
            except Exception:
                self.statusBar().showMessage('You need to run dogmin first.')
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    # def dogmin_set_guesses(self):
    #     if self.ready:
    #         dgtxt = self.logDogmin.toPlainText()
    #         try:
    #             block = [ln for ln in dgtxt.splitlines() if ln != '']
    #             xyz = [ix for ix, ln in enumerate(block) if ln.startswith('xyzguess')]
    #             gixs = [ix for ix, ln in enumerate(block) if ln.startswith('ptguess')][0] - 1
    #             gixe = xyz[-1] + 2
    #             ptguess = block[gixs:gixe]
    #             self.tc.update_scriptfile(guesses=ptguess)
    #             self.read_scriptfile()
    #             self.statusBar().showMessage('Dogmin ptuess set.')
    #         except Exception:
    #             self.statusBar().showMessage('You need to run dogmin first.')
    #     else:
    #         self.statusBar().showMessage('Project is not yet initialized.')

    def plot(self):
        if self.ready:
            lalfa = self.spinAlpha.value() / 100
            fsize = self.spinFontsize.value()
            unilabel_kw = dict(
                ha='center',
                va='center',
                size=fsize,
                bbox=dict(boxstyle="round,pad=0.2", fc='lightskyblue', alpha=lalfa, pad=2),
            )
            unilabel_unc_kw = dict(
                ha='center', va='center', size=fsize, bbox=dict(boxstyle="round,pad=0.2", fc='cyan', alpha=lalfa, pad=2)
            )
            invlabel_kw = dict(
                ha='center',
                va='center',
                size=fsize,
                bbox=dict(boxstyle="round,pad=0.2", fc='yellow', alpha=lalfa, pad=2),
            )
            invlabel_unc_kw = dict(
                ha='center',
                va='center',
                size=fsize,
                bbox=dict(boxstyle="round,pad=0.2", fc='orange', alpha=lalfa, pad=2),
            )
            doglabel_kw = dict(
                ha='center',
                va='center',
                size=fsize,
                bbox=dict(boxstyle="round,pad=0.2", fc='orchid', alpha=lalfa, pad=2),
            )
            axs = self.figure.get_axes()
            if axs:
                self.ax = axs[0]
                if hasattr(self.ax, 'areas_shown'):
                    del self.ax.areas_shown
                cur = (self.ax.get_xlim(), self.ax.get_ylim())
            else:
                cur = None
                self.ax = self.figure.add_subplot(111)
            self.ax.cla()
            self.ax.format_coord = self.format_coord
            for uni in self.ps.unilines.values():
                self.ax.plot(uni.x, uni.y, 'k')
                if self.checkLabelUni.isChecked():
                    if uni.connected < 2:
                        xl, yl = uni.get_label_point()
                        self.ax.annotate(
                            uni.annotation(self.checkLabelUniText.isChecked()), (xl, yl), **unilabel_unc_kw
                        )
                    else:
                        if not self.checkHidedoneUni.isChecked():
                            xl, yl = uni.get_label_point()
                            self.ax.annotate(
                                uni.annotation(self.checkLabelUniText.isChecked()), (xl, yl), **unilabel_kw
                            )
            for inv in self.ps.invpoints.values():
                all_uni = inv.all_unilines()
                isnew1, id_uni = self.ps.getiduni(UniLine(phases=all_uni[0][0], out=all_uni[0][1]))
                if not isnew1:
                    isnew1 = not (self.ps.unilines[id_uni].begin == inv.id or self.ps.unilines[id_uni].end == inv.id)
                isnew2, id_uni = self.ps.getiduni(UniLine(phases=all_uni[1][0], out=all_uni[1][1]))
                if not isnew2:
                    isnew2 = not (self.ps.unilines[id_uni].begin == inv.id or self.ps.unilines[id_uni].end == inv.id)
                isnew3, id_uni = self.ps.getiduni(UniLine(phases=all_uni[2][0], out=all_uni[2][1]))
                if not isnew3:
                    isnew3 = not (self.ps.unilines[id_uni].begin == inv.id or self.ps.unilines[id_uni].end == inv.id)
                isnew4, id_uni = self.ps.getiduni(UniLine(phases=all_uni[3][0], out=all_uni[3][1]))
                if not isnew4:
                    isnew4 = not (self.ps.unilines[id_uni].begin == inv.id or self.ps.unilines[id_uni].end == inv.id)
                unconnected = isnew1 or isnew2 or isnew3 or isnew4
                if self.checkLabelInv.isChecked():
                    if unconnected:
                        self.ax.annotate(
                            inv.annotation(self.checkLabelInvText.isChecked()), (inv.x, inv.y), **invlabel_unc_kw
                        )
                    else:
                        if not self.checkHidedoneInv.isChecked():
                            self.ax.annotate(
                                inv.annotation(self.checkLabelInvText.isChecked()), (inv.x, inv.y), **invlabel_kw
                            )
                else:
                    if unconnected:
                        self.ax.plot(inv.x, inv.y, '.', color='orange', ms=8)
                    else:
                        self.ax.plot(inv.x, inv.y, 'k.', ms=8)
            if self.checkLabelDog.isChecked():
                for dgm in self.ps.dogmins.values():
                    self.ax.annotate(
                        dgm.annotation(self.checkLabelDogText.isChecked(), self.ps.excess),
                        (dgm.x, dgm.y),
                        **doglabel_kw
                    )
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
                shapes, _, log = self.ps.create_shapes()
                if log:
                    self.textOutput.setPlainText('\n'.join(log))
                if shapes:
                    vari = [-len(key) for key in shapes]
                    poc = max(vari) - min(vari) + 1
                    pscolors = cm.get_cmap('cool')(np.linspace(0, 1, poc))
                    # Set alpha
                    pscolors[:, -1] = 0.6  # alpha
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
                for p in reversed(self.ax.patches):
                    p.remove()
                if hasattr(self.ax, 'areas_shown'):
                    del self.ax.areas_shown
                self.figure.canvas.draw()
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


class PTBuilder(BuildersBase, Ui_PTBuilder):
    """Main class for ptbuilder"""

    def __init__(self, parent=None):
        self.builder_name = 'PTBuilder'
        self.builder_extension = '.ptb'
        self.ps = PTsection()
        super(PTBuilder, self).__init__(parent)

    def builder_ui_settings(self):
        # CONNECT SIGNALS
        self.pushCalcTatP.clicked.connect(lambda: self.do_calc(True))
        self.pushCalcPatT.clicked.connect(lambda: self.do_calc(False))
        self.actionImport_drfile.triggered.connect(self.import_drfile)
        self.actionImport_from_old.triggered.connect(self.import_from_old)
        # additional keyboard shortcuts
        self.scCalcTatP = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+T"), self)
        self.scCalcTatP.activated.connect(lambda: self.do_calc(True))
        self.scCalcPatT = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+P"), self)
        self.scCalcPatT.activated.connect(lambda: self.do_calc(False))

    def app_settings(self, write=False):
        # Applicatiom settings
        builder_settings = QtCore.QSettings('LX', 'ptbuilder')
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
            builder_settings.setValue("hide_done_inv", self.checkHidedoneInv.checkState())
            builder_settings.setValue("hide_done_uni", self.checkHidedoneUni.checkState())
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
            self.checkLabelUni.setCheckState(
                builder_settings.value("label_uni", QtCore.Qt.Checked, type=QtCore.Qt.CheckState)
            )
            self.checkLabelUniText.setCheckState(
                builder_settings.value("label_uni_text", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)
            )
            self.checkLabelInv.setCheckState(
                builder_settings.value("label_inv", QtCore.Qt.Checked, type=QtCore.Qt.CheckState)
            )
            self.checkLabelInvText.setCheckState(
                builder_settings.value("label_inv_text", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)
            )
            self.checkLabelDog.setCheckState(
                builder_settings.value("label_dog", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)
            )
            self.checkLabelDogText.setCheckState(
                builder_settings.value("label_dog_text", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)
            )
            self.checkHidedoneInv.setCheckState(
                builder_settings.value("hide_done_inv", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)
            )
            self.checkHidedoneUni.setCheckState(
                builder_settings.value("hide_done_uni", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)
            )
            self.spinAlpha.setValue(builder_settings.value("label_alpha", 50, type=int))
            self.spinFontsize.setValue(builder_settings.value("label_fontsize", 8, type=int))
            self.checkAutoconnectUni.setCheckState(
                builder_settings.value("autoconnectuni", QtCore.Qt.Checked, type=QtCore.Qt.CheckState)
            )
            self.checkAutoconnectInv.setCheckState(
                builder_settings.value("autoconnectinv", QtCore.Qt.Checked, type=QtCore.Qt.CheckState)
            )
            self.checkUseInvGuess.setCheckState(
                builder_settings.value("use_inv_guess", QtCore.Qt.Checked, type=QtCore.Qt.CheckState)
            )
            self.checkOverwrite.setCheckState(
                builder_settings.value("overwrite", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)
            )
            self.recent = []
            n = builder_settings.beginReadArray("recent")
            for ix in range(n):
                builder_settings.setArrayIndex(ix)
                projfile = builder_settings.value("projfile", type=str)
                if Path(projfile).is_file():
                    self.recent.append(projfile)
            builder_settings.endArray()

    def builder_refresh_gui(self):
        pass

    def initProject(self, workdir=False):
        """Open working directory and initialize project"""
        if self.changed:
            quit_msg = 'Project have been changed. Save ?'
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Message', quit_msg, qb.Discard | qb.Save, qb.Save)

            if reply == qb.Save:
                self.do_save()
        qd = QtWidgets.QFileDialog
        if not workdir:
            workdir = qd.getExistingDirectory(self, "Select Directory", os.path.expanduser('~'), qd.ShowDirsOnly)
        if workdir:
            tc, ok = get_tcapi(workdir)
            if ok:
                self.tc = tc
                self.ps = PTsection(trange=self.tc.trange, prange=self.tc.prange, excess=self.tc.excess)
                self.bulk = self.tc.bulk
                self.ready = True
                self.initViewModels()
                self.project = None
                self.changed = False
                self.refresh_gui()
                self.statusBar().showMessage('Project initialized successfully.')
            else:
                qb = QtWidgets.QMessageBox
                qb.critical(self, 'Initialization error', tc, qb.Abort)

    def openProject(self, checked, projfile=None):
        """Open working directory and initialize project"""
        if self.changed:
            quit_msg = 'Project have been changed. Save ?'
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Message', quit_msg, qb.Discard | qb.Save, qb.Save)

            if reply == qb.Save:
                self.do_save()
        if projfile is None:
            if self.ready:
                openin = str(self.tc.workdir)
            else:
                openin = os.path.expanduser('~')
            qd = QtWidgets.QFileDialog
            projfile = qd.getOpenFileName(
                self, 'Open project', openin, self.builder_file_selector + ';;PSBuilder 1.X project (*.psb)'
            )[0]
        if Path(projfile).is_file():
            with gzip.open(projfile, 'rb') as stream:
                data = pickle.load(stream)
            # NEW FORMAT
            if 'section' in data:
                active = Path(projfile).resolve().parent
                try:
                    workdir = Path(data.get('workdir', active)).resolve()
                except PermissionError:
                    workdir = active
                if workdir != active:
                    move_msg = 'Project have been moved. Change working directory ?'
                    qb = QtWidgets.QMessageBox
                    reply = qb.question(self, 'Warning', move_msg, qb.Yes | qb.No, qb.No)

                    if reply == qb.Yes:
                        workdir = active
                QtWidgets.QApplication.processEvents()
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
                tc, ok = get_tcapi(workdir)
                if ok:
                    self.tc = tc
                    self.ps = PTsection(
                        trange=data['section'].xrange, prange=data['section'].yrange, excess=data['section'].excess
                    )
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
                    used_phases = set()
                    for id, inv in data['section'].invpoints.items():
                        self.invmodel.appendRow(id, inv)
                        used_phases.update(inv.phases)
                    self.invview.resizeColumnsToContents()
                    for id, uni in data['section'].unilines.items():
                        self.unimodel.appendRow(id, uni)
                        used_phases.update(uni.phases)
                    self.uniview.resizeColumnsToContents()
                    if hasattr(data['section'], 'dogmins'):
                        if data.get('version', '1.0.0') >= '2.2.1':
                            for id, dgm in data['section'].dogmins.items():
                                if data.get('version', '1.0.0') >= '2.3.0':
                                    self.dogmodel.appendRow(id, dgm)
                                else:
                                    output = dgm._output.split(
                                        '##########################################################\n'
                                    )[-1]
                                    ndgm = Dogmin(id=dgm.id, output=output, resic=dgm.resic, x=dgm.x, y=dgm.y)
                                    self.dogmodel.appendRow(id, ndgm)
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
                        if data['bulk'] != self.tc.bulk and data['version'] >= "2.3.0":
                            qb = QtWidgets.QMessageBox
                            bulk_msg = 'The bulk coposition in project differs from one in scriptfile.\nDo you want to update your script file?'
                            reply = qb.question(self, 'Bulk changed', bulk_msg, qb.Yes | qb.No, qb.No)
                            if reply == qb.Yes:
                                self.bulk = data['bulk']
                                self.tc.update_scriptfile(bulk=data['bulk'])
                                self.read_scriptfile()
                            else:
                                self.bulk = self.tc.bulk
                        else:
                            self.bulk = self.tc.bulk
                    else:
                        self.bulk = self.tc.bulk
                    self.statusBar().showMessage('Project loaded.')
                    if not used_phases.issubset(set(self.tc.phases)):
                        qb = QtWidgets.QMessageBox
                        missing = used_phases.difference(set(self.tc.phases))
                        if len(missing) > 1:
                            qb.warning(
                                self,
                                'Missing phases',
                                'The phases {} are not defined.\nCheck your a-x file {}.'.format(
                                    ' '.join(missing), 'tc-' + self.tc.axname + '.txt'
                                ),
                                qb.Ok,
                            )
                        else:
                            qb.warning(
                                self,
                                'Missing phase',
                                'The phase {} is not defined.\nCheck your a-x file {}.'.format(
                                    ' '.join(missing), 'tc-' + self.tc.axname + '.txt'
                                ),
                                qb.Ok,
                            )
                else:
                    qb = QtWidgets.QMessageBox
                    qb.critical(self, 'Error during openning', tc, qb.Abort)
            # VERY OLD FORMAT
            elif data.get('version', '1.0.0') < '2.1.0':
                qb = QtWidgets.QMessageBox
                qb.critical(
                    self, 'Old version', 'This project is created in older version.\nUse import from project.', qb.Abort
                )
            # OLD FORMAT
            elif data.get('version', '1.0.0') < '2.3.0':
                active = Path(projfile).resolve().parent
                try:
                    workdir = Path(data.get('workdir', active)).resolve()
                except PermissionError:
                    workdir = active
                if workdir != active:
                    move_msg = 'Project have been moved. Change working directory ?'
                    qb = QtWidgets.QMessageBox
                    reply = qb.question(self, 'Warning', move_msg, qb.Yes | qb.No, qb.No)

                    if reply == qb.Yes:
                        workdir = active
                QtWidgets.QApplication.processEvents()
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
                tc, ok = get_tcapi(workdir)
                if ok:
                    self.tc = tc
                    self.ps = PTsection(trange=data['trange'], prange=data['prange'], excess=self.tc.excess)
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
                            inv = InvPoint(
                                id=row[0],
                                phases=row[2]['phases'],
                                out=row[2]['out'],
                                x=row[2]['T'],
                                y=row[2]['p'],
                                manual=True,
                            )
                        else:
                            inv = InvPoint(
                                id=row[0],
                                phases=row[2]['phases'],
                                out=row[2]['out'],
                                x=row[2]['T'],
                                y=row[2]['p'],
                                results=row[2]['results'],
                                output=row[2]['output'],
                            )
                        self.invmodel.appendRow(row[0], inv)
                    self.invview.resizeColumnsToContents()
                    for row in data['unilist']:
                        if row[4]['manual']:
                            uni = UniLine(
                                id=row[0],
                                phases=row[4]['phases'],
                                out=row[4]['out'],
                                x=row[4]['T'],
                                y=row[4]['p'],
                                manual=True,
                                begin=row[2],
                                end=row[3],
                            )
                        else:
                            uni = UniLine(
                                id=row[0],
                                phases=row[4]['phases'],
                                out=row[4]['out'],
                                x=row[4]['T'],
                                y=row[4]['p'],
                                results=row[4]['results'],
                                output=row[4]['output'],
                                begin=row[2],
                                end=row[3],
                            )
                        self.unimodel.appendRow(row[0], uni)
                        self.ps.trim_uni(row[0])
                    self.uniview.resizeColumnsToContents()
                    self.bulk = self.tc.bulk
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
                    qb.critical(self, 'Error during openning', tc, qb.Abort)
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
            tpfile = qd.getOpenFileName(
                self, 'Open drawpd file', str(self.tc.workdir), 'Drawpd files (*.txt);;All files (*.*)'
            )[0]
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
            old_guesses = None
            self.statusBar().showMessage('Searching for invariant points...')
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            # set guesses temporarily when asked
            if uni.connected == 1 and self.checkUseInvGuess.isChecked():
                inv_id = sorted([uni.begin, uni.end])[1]
                if not self.ps.invpoints[inv_id].manual:
                    old_guesses = self.tc.update_scriptfile(
                        guesses=self.ps.invpoints[inv_id].ptguess(), get_old_guesses=True
                    )
            # Try out from phases
            extend = self.spinOver.value()
            trange = self.ax.get_xlim()
            ts = extend * (trange[1] - trange[0]) / 100
            trange = (max(trange[0] - ts, self.tc.trange[0]), min(trange[1] + ts, self.tc.trange[1]))
            prange = self.ax.get_ylim()
            ps = extend * (prange[1] - prange[0]) / 100
            prange = (max(prange[0] - ps, self.tc.prange[0]), min(prange[1] + ps, self.tc.prange[1]))
            cand = []
            line = uni._shape()
            for ophase in phases.difference(out).difference(self.ps.excess):
                nout = out.union(set([ophase]))
                self.tc.calc_pt(phases, nout, prange=prange, trange=trange)
                status, res, output = self.tc.parse_logfile()
                if status == 'ok':
                    inv = InvPoint(
                        phases=phases, out=nout, variance=res.variance, y=res.y, x=res.x, output=output, results=res
                    )
                    isnew, id = self.ps.getidinv(inv)
                    if isnew:
                        exists, inv_id = '', ''
                    else:
                        exists, inv_id = '*', str(id)
                    cand.append(
                        (line.project(Point(inv._x, inv._y)), inv._x, inv._y, exists, ' '.join(inv.out), inv_id)
                    )

            for ophase in set(self.tc.phases).difference(self.ps.excess).difference(phases):
                nphases = phases.union(set([ophase]))
                nout = out.union(set([ophase]))
                self.tc.calc_pt(nphases, nout, prange=prange, trange=trange)
                status, res, output = self.tc.parse_logfile()
                if status == 'ok':
                    inv = InvPoint(
                        phases=nphases, out=nout, variance=res.variance, y=res.y, x=res.x, output=output, results=res
                    )
                    isnew, id = self.ps.getidinv(inv)
                    if isnew:
                        exists, inv_id = '', ''
                    else:
                        exists, inv_id = '*', str(id)
                    cand.append(
                        (line.project(Point(inv._x, inv._y)), inv._x, inv._y, exists, ' '.join(inv.out), inv_id)
                    )

            # set original ptguesses when needed
            if old_guesses is not None:
                self.tc.update_scriptfile(guesses=old_guesses)
            QtWidgets.QApplication.restoreOverrideCursor()
            if cand:
                txt = '         {}         {}       Out   Inv\n'.format(self.ps.x_var, self.ps.y_var)
                n_format = '{:10.4f}{:10.4f}{:>2}{:>8}{:>6}\n'
                for cc in sorted(cand, key=lambda elem: elem[0]):
                    txt += n_format.format(*cc[1:])

                self.textOutput.setPlainText(txt)
                self.statusBar().showMessage('Searching done. Found {} invariant points.'.format(len(cand)))
            else:
                self.statusBar().showMessage('No invariant points found.')

    def dogminer(self, event):
        if event.inaxes is not None:
            phases, out = self.get_phases_out()
            variance = self.spinVariance.value()
            doglevel = self.spinDoglevel.value()
            self.statusBar().showMessage('Running dogmin with max variance of equilibria at {}...'.format(variance))
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            tcout = self.tc.dogmin(phases, event.ydata, event.xdata, variance, doglevel=doglevel)
            self.read_scriptfile()
            QtWidgets.QApplication.restoreOverrideCursor()
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

    def do_calc(self, calcT, phases={}, out={}, run_tc=True):
        if self.ready:
            if run_tc:
                if phases == {} and out == {}:
                    phases, out = self.get_phases_out()
                self.statusBar().showMessage('Running THERMOCALC...')
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            ###########
            extend = self.spinOver.value()
            trange = self.ax.get_xlim()
            ts = extend * (trange[1] - trange[0]) / 100
            trange = (max(trange[0] - ts, self.tc.trange[0]), min(trange[1] + ts, self.tc.trange[1]))
            prange = self.ax.get_ylim()
            ps = extend * (prange[1] - prange[0]) / 100
            prange = (max(prange[0] - ps, self.tc.prange[0]), min(prange[1] + ps, self.tc.prange[1]))
            steps = self.spinSteps.value()
            if not run_tc:
                status, res, output, (phases, out, ans) = self.tc.parse_logfile(get_phases=True)
                uni_tmp = UniLine(phases=phases, out=out)
                isnew, id_uni = self.ps.getiduni(uni_tmp)
            if len(out) == 1:
                if run_tc:
                    uni_tmp = UniLine(phases=phases, out=out)
                    isnew, id_uni = self.ps.getiduni(uni_tmp)
                    if calcT:
                        tcout, ans = self.tc.calc_t(
                            uni_tmp.phases, uni_tmp.out, prange=prange, trange=trange, steps=steps
                        )
                    else:
                        tcout, ans = self.tc.calc_p(
                            uni_tmp.phases, uni_tmp.out, prange=prange, trange=trange, steps=steps
                        )
                    self.logText.setPlainText('Working directory:{}\n\n'.format(self.tc.workdir) + tcout)
                    status, res, output = self.tc.parse_logfile()
                if status == 'bombed':
                    self.statusBar().showMessage('Bombed.')
                elif status == 'nir':
                    self.statusBar().showMessage('Nothing in range.')
                elif len(res) < 2:
                    self.statusBar().showMessage('Only one point calculated. Change range.')
                else:
                    uni = UniLine(
                        id=id_uni,
                        phases=uni_tmp.phases,
                        out=uni_tmp.out,
                        cmd=ans,
                        variance=res.variance,
                        y=res.y,
                        x=res.x,
                        output=output,
                        results=res,
                    )
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
                            if self.pushMerge.isChecked():
                                uni_old = self.ps.unilines[id_uni]
                                dt = {}
                                for p in uni_old.phases.difference(uni_old.out):
                                    dt[p] = []
                                for res in uni_old.results:
                                    for p in uni_old.phases.difference(uni_old.out):
                                        dt[p].append(res[p]['mode'])
                                N = len(uni_old.results)
                                for res, x, y in zip(uni.results, uni._x, uni._y):
                                    if x not in uni_old._x and y not in uni_old._y:
                                        idx = []
                                        for p in uni_old.phases.difference(uni_old.out):
                                            q = interp1d(dt[p], np.arange(N), fill_value='extrapolate')
                                            q_val = q(res[p]['mode'])
                                            if np.isfinite(q_val):
                                                idx.append(np.ceil(q_val))

                                        idx_clip = np.clip(np.array(idx, dtype=int), 0, N)
                                        values, counts = np.unique(idx_clip, return_counts=True)
                                        if counts.size > 0:
                                            nix = values[np.argmax(counts)]
                                            # insert data to temporary dict
                                            for p in uni_old.phases.difference(uni_old.out):
                                                dt[p].insert(nix, res[p]['mode'])
                                            # insert real data
                                            uni_old.results.insert(nix, res)
                                            uni_old._x = np.insert(uni_old._x, nix, x)
                                            uni_old._y = np.insert(uni_old._y, nix, y)
                                            N += 1
                                uni_old.output += uni.output  # Really
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
                                self.statusBar().showMessage('Univariant line {} merged.'.format(id_uni))
                            else:
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
                if run_tc:
                    inv_tmp = InvPoint(phases=phases, out=out)
                    isnew, id_inv = self.ps.getidinv(inv_tmp)
                    tcout, ans = self.tc.calc_pt(inv_tmp.phases, inv_tmp.out, prange=prange, trange=trange)
                    self.logText.setPlainText('Working directory:{}\n\n'.format(self.tc.workdir) + tcout)
                    status, res, output = self.tc.parse_logfile()
                if status == 'bombed':
                    self.statusBar().showMessage('Bombed.')
                elif status == 'nir':
                    self.statusBar().showMessage('Nothing in range.')
                else:
                    inv = InvPoint(
                        id=id_inv,
                        phases=inv_tmp.phases,
                        out=inv_tmp.out,
                        cmd=ans,
                        variance=res.variance,
                        y=res.y,
                        x=res.x,
                        output=output,
                        results=res,
                    )
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
            self.read_scriptfile()
            QtWidgets.QApplication.restoreOverrideCursor()
        else:
            self.statusBar().showMessage('Project is not yet initialized.')
        self.pushMerge.setChecked(False)


class TXBuilder(BuildersBase, Ui_TXBuilder):
    """Main class for txbuilder"""

    def __init__(self, parent=None):
        self.builder_name = 'TXBuilder'
        self.builder_extension = '.txb'
        self.ps = TXsection()
        super(TXBuilder, self).__init__(parent)

    def builder_ui_settings(self):
        # CONNECT SIGNALS
        self.pushCalc.clicked.connect(self.do_calc)
        self.actionImport_from_PT.triggered.connect(self.import_from_pt)
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
            builder_settings.setValue("hide_done_inv", self.checkHidedoneInv.checkState())
            builder_settings.setValue("hide_done_uni", self.checkHidedoneUni.checkState())
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
            self.rangeSpin.setValue(builder_settings.value("prange", 0, type=float))
            self.checkLabelUni.setCheckState(
                builder_settings.value("label_uni", QtCore.Qt.Checked, type=QtCore.Qt.CheckState)
            )
            self.spinDoglevel.setValue(builder_settings.value("dogmin_level", 1, type=int))
            self.checkLabelUniText.setCheckState(
                builder_settings.value("label_uni_text", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)
            )
            self.checkLabelInv.setCheckState(
                builder_settings.value("label_inv", QtCore.Qt.Checked, type=QtCore.Qt.CheckState)
            )
            self.checkLabelInvText.setCheckState(
                builder_settings.value("label_inv_text", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)
            )
            self.checkLabelDog.setCheckState(
                builder_settings.value("label_dog", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)
            )
            self.checkLabelDogText.setCheckState(
                builder_settings.value("label_dog_text", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)
            )
            self.checkHidedoneInv.setCheckState(
                builder_settings.value("hide_done_inv", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)
            )
            self.checkHidedoneUni.setCheckState(
                builder_settings.value("hide_done_uni", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)
            )
            self.spinAlpha.setValue(builder_settings.value("label_alpha", 50, type=int))
            self.spinFontsize.setValue(builder_settings.value("label_fontsize", 8, type=int))
            self.checkAutoconnectUni.setCheckState(
                builder_settings.value("autoconnectuni", QtCore.Qt.Checked, type=QtCore.Qt.CheckState)
            )
            self.checkAutoconnectInv.setCheckState(
                builder_settings.value("autoconnectinv", QtCore.Qt.Checked, type=QtCore.Qt.CheckState)
            )
            self.checkUseInvGuess.setCheckState(
                builder_settings.value("use_inv_guess", QtCore.Qt.Checked, type=QtCore.Qt.CheckState)
            )
            self.checkOverwrite.setCheckState(
                builder_settings.value("overwrite", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)
            )
            self.recent = []
            n = builder_settings.beginReadArray("recent")
            for ix in range(n):
                builder_settings.setArrayIndex(ix)
                projfile = builder_settings.value("projfile", type=str)
                if Path(projfile).is_file():
                    self.recent.append(projfile)
            builder_settings.endArray()

    def builder_refresh_gui(self):
        self.spinSteps.setValue(self.tc.ptx_steps)

    def initProject(self, workdir=False):
        """Open working directory and initialize project"""
        if self.changed:
            quit_msg = 'Project have been changed. Save ?'
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Message', quit_msg, qb.Discard | qb.Save, qb.Save)

            if reply == qb.Save:
                self.do_save()
        qd = QtWidgets.QFileDialog
        if not workdir:
            workdir = qd.getExistingDirectory(self, "Select Directory", os.path.expanduser('~'), qd.ShowDirsOnly)
        if workdir:
            tc, ok = get_tcapi(workdir)
            if ok:
                self.tc = tc
                self.ps = TXsection(trange=self.tc.trange, excess=self.tc.excess)
                self.bulk = self.tc.bulk
                self.ready = True
                self.initViewModels()
                self.project = None
                self.changed = False
                self.refresh_gui()
                self.statusBar().showMessage('Project initialized successfully.')
            else:
                qb = QtWidgets.QMessageBox
                qb.critical(self, 'Initialization error', tc, qb.Abort)

    def openProject(self, checked, projfile=None):
        """Open working directory and initialize project"""
        if self.changed:
            quit_msg = 'Project have been changed. Save ?'
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Message', quit_msg, qb.Discard | qb.Save, qb.Save)

            if reply == qb.Save:
                self.do_save()
        if projfile is None:
            if self.ready:
                openin = str(self.tc.workdir)
            else:
                openin = os.path.expanduser('~')
            qd = QtWidgets.QFileDialog
            projfile = qd.getOpenFileName(self, 'Open project', openin, self.builder_file_selector)[0]
        if Path(projfile).is_file():
            with gzip.open(projfile, 'rb') as stream:
                data = pickle.load(stream)
            if 'section' in data:
                active = Path(projfile).resolve().parent
                try:
                    workdir = Path(data.get('workdir', active)).resolve()
                except PermissionError:
                    workdir = active
                if workdir != active:
                    move_msg = 'Project have been moved. Change working directory ?'
                    qb = QtWidgets.QMessageBox
                    reply = qb.question(self, 'Warning', move_msg, qb.Yes | qb.No, qb.No)

                    if reply == qb.Yes:
                        workdir = active
                QtWidgets.QApplication.processEvents()
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
                tc, ok = get_tcapi(workdir)
                if ok:
                    self.tc = tc
                    self.ps = TXsection(trange=data['section'].xrange, excess=data['section'].excess)
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
                    used_phases = set()
                    for id, inv in data['section'].invpoints.items():
                        if data.get('version', '1.0.0') < '2.2.1':
                            if inv.manual:
                                inv.results = None
                            else:
                                inv.results = TCResultSet(
                                    [
                                        TCResult(
                                            inv.x, inv.y, variance=inv.variance, data=r['data'], ptguess=r['ptguess']
                                        )
                                        for r in inv.results
                                    ]
                                )
                        self.invmodel.appendRow(id, inv)
                        used_phases.update(inv.phases)
                    self.invview.resizeColumnsToContents()
                    for id, uni in data['section'].unilines.items():
                        if data.get('version', '1.0.0') < '2.2.1':
                            if uni.manual:
                                uni.results = None
                            else:
                                uni.results = TCResultSet(
                                    [
                                        TCResult(
                                            uni.x, uni.y, variance=uni.variance, data=r['data'], ptguess=r['ptguess']
                                        )
                                        for r in uni.results
                                    ]
                                )
                        self.unimodel.appendRow(id, uni)
                        used_phases.update(uni.phases)
                    self.uniview.resizeColumnsToContents()
                    if hasattr(data['section'], 'dogmins') and data.get('version', '1.0.0') >= '2.3.0':
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
                        if data['bulk'] != self.tc.bulk:
                            qb = QtWidgets.QMessageBox
                            bulk_msg = 'The bulk coposition in project differs from one in scriptfile.\nDo you want to update your script file?'
                            reply = qb.question(self, 'Bulk changed', bulk_msg, qb.Yes | qb.No, qb.No)
                            if reply == qb.Yes:
                                self.bulk = data['bulk']
                                self.tc.update_scriptfile(bulk=data['bulk'], xsteps=self.spinSteps.value())
                                self.read_scriptfile()
                            else:
                                self.bulk = self.tc.bulk
                        else:
                            self.bulk = self.tc.bulk
                    else:
                        self.bulk = self.tc.bulk
                    self.statusBar().showMessage('Project loaded.')
                    if not used_phases.issubset(set(self.tc.phases)):
                        qb = QtWidgets.QMessageBox
                        missing = used_phases.difference(set(self.tc.phases))
                        if len(missing) > 1:
                            qb.warning(
                                self,
                                'Missing phases',
                                'The phases {} are not defined.\nCheck your a-x file {}.'.format(
                                    ' '.join(missing), 'tc-' + self.tc.axname + '.txt'
                                ),
                                qb.Ok,
                            )
                        else:
                            qb.warning(
                                self,
                                'Missing phase',
                                'The phase {} is not defined.\nCheck your a-x file {}.'.format(
                                    ' '.join(missing), 'tc-' + self.tc.axname + '.txt'
                                ),
                                qb.Ok,
                            )
                else:
                    qb = QtWidgets.QMessageBox
                    qb.critical(self, 'Error during openning', tc, qb.Abort)
            else:
                qb = QtWidgets.QMessageBox
                qb.critical(self, 'Error during openning', 'Unknown format of the project file', qb.Abort)
            QtWidgets.QApplication.restoreOverrideCursor()
        else:
            if projfile in self.recent:
                self.recent.pop(self.recent.index(projfile))
                self.app_settings(write=True)
                self.populate_recent()

    def import_from_pt(self):
        if self.ready:
            qd = QtWidgets.QFileDialog
            projfile = qd.getOpenFileName(
                self, 'Import from project', str(self.tc.workdir), 'PTBuilder project (*.ptb)'
            )[0]
            if Path(projfile).is_file():
                with gzip.open(projfile, 'rb') as stream:
                    data = pickle.load(stream)
                if 'section' in data:  # NEW
                    pm = sum(self.tc.prange) / 2
                    extend = self.spinOver.value()
                    trange = self.ax.get_xlim()
                    ts = extend * (trange[1] - trange[0]) / 100
                    trange = (max(trange[0] - ts, self.tc.trange[0]), min(trange[1] + ts, self.tc.trange[1]))
                    # seek line
                    pt_line = LineString([(trange[0], pm), (trange[1], pm)])
                    crange = self.ax.get_ylim()
                    cs = extend * (crange[1] - crange[0]) / 100
                    crange = (max(crange[0] - cs, 0), min(crange[1] + cs, 1))
                    #
                    self.statusBar().showMessage('Importing from PT section...')
                    QtWidgets.QApplication.processEvents()
                    QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
                    # change bulk
                    # bulk = self.tc.interpolate_bulk(crange)
                    # self.tc.update_scriptfile(bulk=bulk, xsteps=self.spinSteps.value(), xvals=crange)
                    # only uni
                    last = None
                    for id, uni in data['section'].unilines.items():
                        if pt_line.intersects(uni.shape()):
                            isnew, id_uni = self.ps.getiduni(uni)
                            if isnew:
                                tcout, ans = self.tc.calc_tx(
                                    uni.phases,
                                    uni.out,
                                    prange=(pm, pm),
                                    trange=trange,
                                    xvals=crange,
                                    steps=self.spinSteps.value(),
                                )
                                status, res, output = self.tc.parse_logfile()
                                if status == 'ok':
                                    if len(res) > 1:
                                        # rescale pts from zoomed composition
                                        uni_ok = UniLine(
                                            id=id_uni,
                                            phases=uni.phases,
                                            out=uni.out,
                                            cmd=ans,
                                            variance=res.variance,
                                            y=res.c,
                                            x=res.x,
                                            output=output,
                                            results=res,
                                        )
                                        self.unimodel.appendRow(id_uni, uni_ok)
                                        self.changed = True
                                        last = id_uni
                    if last is not None:
                        self.uniview.resizeColumnsToContents()
                        idx = self.unimodel.getIndexID(last)
                        self.uniview.selectRow(idx.row())
                    # restore bulk
                    # self.tc.update_scriptfile(bulk=self.bulk, xsteps=self.spinSteps.value())
                    self.refresh_gui()
                    QtWidgets.QApplication.restoreOverrideCursor()
                    self.statusBar().showMessage('Data imported.')
                else:
                    qb = QtWidgets.QMessageBox
                    qb.critical(self, 'Error during openning', 'Unknown format of the project file', qb.Abort)

    @property
    def plot_title(self):
        ex = list(self.ps.excess)
        ex.insert(0, '')
        pm = sum(self.tc.prange) / 2
        return self.tc.axname + ' +'.join(ex) + ' (at {:g} kbar)'.format(pm)

    def reset_limits(self):
        if self.ready:
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
            old_guesses = None
            self.statusBar().showMessage('Searching for invariant points...')
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            # set guesses temporarily when asked
            if uni.connected == 1 and self.checkUseInvGuess.isChecked():
                inv_id = sorted([uni.begin, uni.end])[1]
                if not self.ps.invpoints[inv_id].manual:
                    old_guesses = self.tc.update_scriptfile(
                        guesses=self.ps.invpoints[inv_id].ptguess(), get_old_guesses=True
                    )
            # Try out from phases
            extend = self.spinOver.value()
            trange = self.ax.get_xlim()
            ts = extend * (trange[1] - trange[0]) / 100
            trange = (max(trange[0] - ts, self.tc.trange[0]), min(trange[1] + ts, self.tc.trange[1]))
            pm = sum(self.tc.prange) / 2
            prange = (
                max(pm - self.rangeSpin.value() / 2, self.tc.prange[0]),
                min(pm + self.rangeSpin.value() / 2, self.tc.prange[1]),
            )
            crange = self.ax.get_ylim()
            cs = extend * (crange[1] - crange[0]) / 100
            crange = (max(crange[0] - cs, 0), min(crange[1] + cs, 1))
            # change bulk
            # bulk = self.tc.interpolate_bulk(crange)
            # self.tc.update_scriptfile(bulk=bulk, xsteps=self.spinSteps.value(), xvals=crange)
            out_section = []
            cand = []
            line = uni._shape()
            for ophase in phases.difference(out).difference(self.ps.excess):
                nout = out.union(set([ophase]))
                self.tc.calc_tx(phases, nout, prange=prange, trange=trange, xvals=crange, steps=self.spinSteps.value())
                status, res, output = self.tc.parse_logfile()
                inv = InvPoint(phases=phases, out=nout)
                isnew, id = self.ps.getidinv(inv)
                if status == 'ok':
                    if isnew:
                        exists, inv_id = '', ''
                    else:
                        exists, inv_id = '*', str(id)
                    if len(res) > 1:
                        # rescale pts from zoomed composition
                        splt = interp1d(res.y, res.x, bounds_error=False, fill_value=np.nan)
                        splx = interp1d(res.y, res.c, bounds_error=False, fill_value=np.nan)
                        Xm = splt([pm])
                        Ym = splx([pm])
                        if not np.isnan(Xm[0]):
                            cand.append(
                                (line.project(Point(Xm[0], Ym[0])), Xm[0], Ym[0], exists, ' '.join(inv.out), inv_id)
                            )
                        else:
                            ix = abs(res.y - pm).argmin()
                            out_section.append((res.x[ix], res.y[ix], exists, ' '.join(inv.out), inv_id))
                    else:
                        out_section.append((res.x[0], res.y[0], exists, ' '.join(inv.out), inv_id))

            for ophase in set(self.tc.phases).difference(self.ps.excess).difference(phases):
                nphases = phases.union(set([ophase]))
                nout = out.union(set([ophase]))
                self.tc.calc_tx(nphases, nout, prange=prange, trange=trange, xvals=crange, steps=self.spinSteps.value())
                status, res, output = self.tc.parse_logfile()
                inv = InvPoint(phases=nphases, out=nout)
                isnew, id = self.ps.getidinv(inv)
                if status == 'ok':
                    if isnew:
                        exists, inv_id = '', ''
                    else:
                        exists, inv_id = '*', str(id)
                    if len(res) > 1:
                        # rescale pts from zoomed composition
                        splt = interp1d(res.y, res.x, bounds_error=False, fill_value=np.nan)
                        splx = interp1d(res.y, res.c, bounds_error=False, fill_value=np.nan)
                        Xm = splt([pm])
                        Ym = splx([pm])
                        if not np.isnan(Xm[0]):
                            cand.append(
                                (line.project(Point(Xm[0], Ym[0])), Xm[0], Ym[0], exists, ' '.join(inv.out), inv_id)
                            )
                        else:
                            ix = abs(res.y - pm).argmin()
                            out_section.append((res.x[ix], res.y[ix], exists, ' '.join(inv.out), inv_id))
                    else:
                        out_section.append((res.x[0], res.y[0], exists, ' '.join(inv.out), inv_id))

            # set original ptguesses when needed
            if old_guesses is not None:
                self.tc.update_scriptfile(guesses=old_guesses)
            # restore bulk
            # self.tc.update_scriptfile(bulk=self.bulk, xsteps=self.spinSteps.value())
            QtWidgets.QApplication.restoreOverrideCursor()
            txt = ''
            n_format = '{:10.4f}{:10.4f}{:>2}{:>8}{:>6}\n'
            if cand:
                txt += '         {}         {} E     Out   Inv\n'.format(self.ps.x_var, self.ps.y_var)
                for cc in sorted(cand, key=lambda elem: elem[0]):
                    txt += n_format.format(*cc[1:])

                self.textOutput.setPlainText(txt)
                self.statusBar().showMessage('Searching done. Found {} invariant points.'.format(len(cand)))
            elif out_section:
                txt += 'Solutions with single point (need increase number of steps)\n'
                txt += '         {}         {} E     Out   Inv\n'.format(self.ps.x_var, self.ps.y_var)
                for cc in out_section:
                    txt += n_format.format(*cc)

                self.textOutput.setPlainText(txt)
                self.statusBar().showMessage(
                    'Searching done. Found {} invariant points and {} out of section.'.format(
                        len(cand), len(out_section)
                    )
                )
            else:
                self.statusBar().showMessage('No invariant points found.')

    def dogminer(self, event):
        if event.inaxes is not None:
            phases, out = self.get_phases_out()
            variance = self.spinVariance.value()
            doglevel = self.spinDoglevel.value()
            # change bulk
            # bulk = self.tc.interpolate_bulk(event.ydata) # use onebulk
            pm = sum(self.tc.prange) / 2
            self.statusBar().showMessage('Running dogmin with max variance of equilibria at {}...'.format(variance))
            # self.read_scriptfile()
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            tcout = self.tc.dogmin(phases, pm, event.xdata, variance, doglevel=doglevel, onebulk=event.ydata)
            self.read_scriptfile()
            QtWidgets.QApplication.restoreOverrideCursor()
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

    def do_calc(self, calcT, phases={}, out={}, run_tc=True):
        if self.ready:
            if run_tc:
                if phases == {} and out == {}:
                    phases, out = self.get_phases_out()
                self.statusBar().showMessage('Running THERMOCALC...')
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            ###########
            extend = self.spinOver.value()
            trange = self.ax.get_xlim()
            ts = extend * (trange[1] - trange[0]) / 100
            trange = (max(trange[0] - ts, self.tc.trange[0]), min(trange[1] + ts, self.tc.trange[1]))
            pm = sum(self.tc.prange) / 2
            crange = self.ax.get_ylim()
            cs = extend * (crange[1] - crange[0]) / 100
            crange = (max(crange[0] - cs, 0), min(crange[1] + cs, 1))
            # change bulk
            # bulk = self.tc.interpolate_bulk(crange)
            # self.tc.update_scriptfile(bulk=self.bulk, xsteps=self.spinSteps.value())
            if not run_tc:
                status, res, output, (phases, out, ans) = self.tc.parse_logfile(get_phases=True)
                uni_tmp = UniLine(phases=phases, out=out)
                isnew, id_uni = self.ps.getiduni(uni_tmp)
            if len(out) == 1:
                if run_tc:
                    uni_tmp = UniLine(phases=phases, out=out)
                    isnew, id_uni = self.ps.getiduni(uni_tmp)
                    tcout, ans = self.tc.calc_tx(
                        uni_tmp.phases,
                        uni_tmp.out,
                        prange=(pm, pm),
                        trange=trange,
                        xvals=crange,
                        steps=self.spinSteps.value(),
                    )
                    self.logText.setPlainText('Working directory:{}\n\n'.format(self.tc.workdir) + tcout)
                    status, res, output = self.tc.parse_logfile()
                if status == 'bombed':
                    self.statusBar().showMessage('Bombed.')
                elif status == 'nir':
                    self.statusBar().showMessage('Nothing in range.')
                elif len(res) < 2:
                    self.statusBar().showMessage('Only one point calculated. Change range.')
                else:
                    # rescale pts from zoomed composition
                    uni = UniLine(
                        id=id_uni,
                        phases=uni_tmp.phases,
                        out=uni_tmp.out,
                        cmd=ans,
                        variance=res.variance,
                        y=res.c,
                        x=res.x,
                        output=output,
                        results=res,
                    )
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
                            if self.pushMerge.isChecked():
                                uni_old = self.ps.unilines[id_uni]
                                dt = {}
                                for p in uni_old.phases.difference(uni_old.out):
                                    dt[p] = []
                                for res in uni_old.results:
                                    for p in uni_old.phases.difference(uni_old.out):
                                        dt[p].append(res[p]['mode'])
                                N = len(uni_old.results)
                                for res, x, y in zip(uni.results, uni._x, uni._y):
                                    if x not in uni_old._x and y not in uni_old._y:
                                        idx = []
                                        for p in uni_old.phases.difference(uni_old.out):
                                            q = interp1d(dt[p], np.arange(N), fill_value='extrapolate')
                                            q_val = q(res[p]['mode'])
                                            if np.isfinite(q_val):
                                                idx.append(np.ceil(q_val))

                                        idx_clip = np.clip(np.array(idx, dtype=int), 0, N)
                                        values, counts = np.unique(idx_clip, return_counts=True)
                                        if counts.size > 0:
                                            nix = values[np.argmax(counts)]
                                            # insert data to temporary dict
                                            for p in uni_old.phases.difference(uni_old.out):
                                                dt[p].insert(nix, res[p]['mode'])
                                            # insert real data
                                            uni_old.results.insert(nix, res)
                                            uni_old._x = np.insert(uni_old._x, nix, x)
                                            uni_old._y = np.insert(uni_old._y, nix, y)
                                            N += 1
                                uni_old.output += uni.output
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
                                self.statusBar().showMessage('Univariant line {} merged.'.format(id_uni))
                            else:
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
                if run_tc:
                    inv_tmp = InvPoint(phases=phases, out=out)
                    isnew, id_inv = self.ps.getidinv(inv_tmp)
                    prange = (
                        max(pm - self.rangeSpin.value() / 2, self.tc.prange[0]),
                        min(pm + self.rangeSpin.value() / 2, self.tc.prange[1]),
                    )
                    tcout, ans = self.tc.calc_tx(
                        inv_tmp.phases,
                        inv_tmp.out,
                        prange=prange,
                        trange=trange,
                        xvals=crange,
                        steps=self.spinSteps.value(),
                    )
                    self.logText.setPlainText('Working directory:{}\n\n'.format(self.tc.workdir) + tcout)
                    status, res, output = self.tc.parse_logfile()
                if status == 'bombed':
                    self.statusBar().showMessage('Bombed.')
                elif status == 'nir':
                    self.statusBar().showMessage('Nothing in range.')
                elif len(res) < 2:
                    self.statusBar().showMessage('Only one point calculated. Change steps.')
                else:
                    # rescale pts from zoomed composition
                    splt = interp1d(res.y, res.x, bounds_error=False, fill_value=np.nan)
                    splx = interp1d(res.y, res.c, bounds_error=False, fill_value=np.nan)
                    Xm = splt([pm])
                    Ym = splx([pm])
                    if np.isnan(Xm[0]):
                        status = 'nir'
                        self.statusBar().showMessage(
                            'Nothing in range, but exists out ouf section in p range {:.2f} - {:.2f}.'.format(
                                min(res.y), max(res.y)
                            )
                        )
                    else:
                        ix = np.argmin((res.x - Xm) ** 2)
                        inv = InvPoint(
                            id=id_inv,
                            phases=inv_tmp.phases,
                            out=inv_tmp.out,
                            cmd=ans,
                            variance=res.variance,
                            y=Ym,
                            x=Xm,
                            output=output,
                            results=res[ix : ix + 1],
                        )
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
            # self.tc.update_scriptfile(bulk=self.bulk, xsteps=self.spinSteps.value())
            QtWidgets.QApplication.restoreOverrideCursor()
        else:
            self.statusBar().showMessage('Project is not yet initialized.')
        self.pushMerge.setChecked(False)


class PXBuilder(BuildersBase, Ui_PXBuilder):
    """Main class for pxbuilder"""

    def __init__(self, parent=None):
        self.builder_name = 'PXBuilder'
        self.builder_extension = '.pxb'
        self.ps = PXsection()
        super(PXBuilder, self).__init__(parent)

    def builder_ui_settings(self):
        # CONNECT SIGNALS
        self.pushCalc.clicked.connect(self.do_calc)
        self.actionImport_from_PT.triggered.connect(self.import_from_pt)
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
            builder_settings.setValue("hide_done_inv", self.checkHidedoneInv.checkState())
            builder_settings.setValue("hide_done_uni", self.checkHidedoneUni.checkState())
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
            self.rangeSpin.setValue(builder_settings.value("trange", 0, type=int))
            self.checkLabelUni.setCheckState(
                builder_settings.value("label_uni", QtCore.Qt.Checked, type=QtCore.Qt.CheckState)
            )
            self.spinDoglevel.setValue(builder_settings.value("dogmin_level", 1, type=int))
            self.checkLabelUniText.setCheckState(
                builder_settings.value("label_uni_text", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)
            )
            self.checkLabelInv.setCheckState(
                builder_settings.value("label_inv", QtCore.Qt.Checked, type=QtCore.Qt.CheckState)
            )
            self.checkLabelInvText.setCheckState(
                builder_settings.value("label_inv_text", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)
            )
            self.checkLabelDog.setCheckState(
                builder_settings.value("label_dog", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)
            )
            self.checkLabelDogText.setCheckState(
                builder_settings.value("label_dog_text", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)
            )
            self.checkHidedoneInv.setCheckState(
                builder_settings.value("hide_done_inv", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)
            )
            self.checkHidedoneUni.setCheckState(
                builder_settings.value("hide_done_uni", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)
            )
            self.spinAlpha.setValue(builder_settings.value("label_alpha", 50, type=int))
            self.spinFontsize.setValue(builder_settings.value("label_fontsize", 8, type=int))
            self.checkAutoconnectUni.setCheckState(
                builder_settings.value("autoconnectuni", QtCore.Qt.Checked, type=QtCore.Qt.CheckState)
            )
            self.checkAutoconnectInv.setCheckState(
                builder_settings.value("autoconnectinv", QtCore.Qt.Checked, type=QtCore.Qt.CheckState)
            )
            self.checkUseInvGuess.setCheckState(
                builder_settings.value("use_inv_guess", QtCore.Qt.Checked, type=QtCore.Qt.CheckState)
            )
            self.checkOverwrite.setCheckState(
                builder_settings.value("overwrite", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)
            )
            self.recent = []
            n = builder_settings.beginReadArray("recent")
            for ix in range(n):
                builder_settings.setArrayIndex(ix)
                projfile = builder_settings.value("projfile", type=str)
                if Path(projfile).is_file():
                    self.recent.append(projfile)
            builder_settings.endArray()

    def builder_refresh_gui(self):
        self.spinSteps.setValue(self.tc.ptx_steps)

    def initProject(self, workdir=False):
        """Open working directory and initialize project"""
        if self.changed:
            quit_msg = 'Project have been changed. Save ?'
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Message', quit_msg, qb.Discard | qb.Save, qb.Save)

            if reply == qb.Save:
                self.do_save()
        qd = QtWidgets.QFileDialog
        if not workdir:
            workdir = qd.getExistingDirectory(self, "Select Directory", os.path.expanduser('~'), qd.ShowDirsOnly)
        if workdir:
            tc, ok = get_tcapi(workdir)
            if ok:
                self.tc = tc
                self.ps = PXsection(prange=self.tc.prange, excess=self.tc.excess)
                self.bulk = self.tc.bulk
                self.ready = True
                self.initViewModels()
                self.project = None
                self.changed = False
                self.refresh_gui()
                self.statusBar().showMessage('Project initialized successfully.')
            else:
                qb = QtWidgets.QMessageBox
                qb.critical(self, 'Initialization error', tc, qb.Abort)

    def openProject(self, checked, projfile=None):
        """Open working directory and initialize project"""
        if self.changed:
            quit_msg = 'Project have been changed. Save ?'
            qb = QtWidgets.QMessageBox
            reply = qb.question(self, 'Message', quit_msg, qb.Discard | qb.Save, qb.Save)

            if reply == qb.Save:
                self.do_save()
        if projfile is None:
            if self.ready:
                openin = str(self.tc.workdir)
            else:
                openin = os.path.expanduser('~')
            qd = QtWidgets.QFileDialog
            projfile = qd.getOpenFileName(self, 'Open project', openin, self.builder_file_selector)[0]
        if Path(projfile).is_file():
            with gzip.open(projfile, 'rb') as stream:
                data = pickle.load(stream)
            if 'section' in data:
                active = Path(projfile).resolve().parent
                try:
                    workdir = Path(data.get('workdir', active)).resolve()
                except PermissionError:
                    workdir = active
                if workdir != active:
                    move_msg = 'Project have been moved. Change working directory ?'
                    qb = QtWidgets.QMessageBox
                    reply = qb.question(self, 'Warning', move_msg, qb.Yes | qb.No, qb.No)

                    if reply == qb.Yes:
                        workdir = active
                QtWidgets.QApplication.processEvents()
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
                tc, ok = get_tcapi(workdir)
                if ok:
                    self.tc = tc
                    self.ps = PXsection(prange=data['section'].yrange, excess=data['section'].excess)
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
                    used_phases = set()
                    for id, inv in data['section'].invpoints.items():
                        if data.get('version', '1.0.0') < '2.2.1':
                            if inv.manual:
                                inv.results = None
                            else:
                                inv.results = TCResultSet(
                                    [
                                        TCResult(
                                            inv.x, inv.y, variance=inv.variance, data=r['data'], ptguess=r['ptguess']
                                        )
                                        for r in inv.results
                                    ]
                                )
                        self.invmodel.appendRow(id, inv)
                        used_phases.update(inv.phases)
                    self.invview.resizeColumnsToContents()
                    for id, uni in data['section'].unilines.items():
                        if data.get('version', '1.0.0') < '2.2.1':
                            if uni.manual:
                                uni.results = None
                            else:
                                uni.results = TCResultSet(
                                    [
                                        TCResult(
                                            uni.x, uni.y, variance=uni.variance, data=r['data'], ptguess=r['ptguess']
                                        )
                                        for r in uni.results
                                    ]
                                )
                        self.unimodel.appendRow(id, uni)
                        used_phases.update(uni.phases)
                    self.uniview.resizeColumnsToContents()
                    if hasattr(data['section'], 'dogmins') and data.get('version', '1.0.0') >= '2.3.0':
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
                        if data['bulk'] != self.tc.bulk:
                            qb = QtWidgets.QMessageBox
                            bulk_msg = 'The bulk coposition in project differs from one in scriptfile.\nDo you want to update your script file?'
                            reply = qb.question(self, 'Bulk changed', bulk_msg, qb.Yes | qb.No, qb.No)
                            if reply == qb.Yes:
                                self.bulk = data['bulk']
                                self.tc.update_scriptfile(bulk=data['bulk'], xsteps=self.spinSteps.value())
                                self.read_scriptfile()
                            else:
                                self.bulk = self.tc.bulk
                        else:
                            self.bulk = self.tc.bulk
                    else:
                        self.bulk = self.tc.bulk
                    self.statusBar().showMessage('Project loaded.')
                    if not used_phases.issubset(set(self.tc.phases)):
                        qb = QtWidgets.QMessageBox
                        missing = used_phases.difference(set(self.tc.phases))
                        if len(missing) > 1:
                            qb.warning(
                                self,
                                'Missing phases',
                                'The phases {} are not defined.\nCheck your a-x file {}.'.format(
                                    ' '.join(missing), 'tc-' + self.tc.axname + '.txt'
                                ),
                                qb.Ok,
                            )
                        else:
                            qb.warning(
                                self,
                                'Missing phase',
                                'The phase {} is not defined.\nCheck your a-x file {}.'.format(
                                    ' '.join(missing), 'tc-' + self.tc.axname + '.txt'
                                ),
                                qb.Ok,
                            )
                else:
                    qb = QtWidgets.QMessageBox
                    qb.critical(self, 'Error during openning', tc, qb.Abort)
            else:
                qb = QtWidgets.QMessageBox
                qb.critical(self, 'Error during openning', 'Unknown format of the project file', qb.Abort)
            QtWidgets.QApplication.restoreOverrideCursor()
        else:
            if projfile in self.recent:
                self.recent.pop(self.recent.index(projfile))
                self.app_settings(write=True)
                self.populate_recent()

    def import_from_pt(self):
        if self.ready:
            qd = QtWidgets.QFileDialog
            projfile = qd.getOpenFileName(
                self, 'Import from project', str(self.tc.workdir), 'PTBuilder project (*.ptb)'
            )[0]
            if Path(projfile).is_file():
                with gzip.open(projfile, 'rb') as stream:
                    data = pickle.load(stream)
                if 'section' in data:  # NEW
                    tm = sum(self.tc.trange) / 2
                    extend = self.spinOver.value()
                    prange = self.ax.get_ylim()
                    ps = extend * (prange[1] - prange[0]) / 100
                    prange = (max(prange[0] - ps, 0.01), prange[1] + ps)
                    # seek line
                    pt_line = LineString([(tm, prange[0]), (tm, prange[1])])
                    crange = self.ax.get_xlim()
                    cs = extend * (crange[1] - crange[0]) / 100
                    crange = (max(crange[0] - cs, 0), min(crange[1] + cs, 1))
                    #
                    self.statusBar().showMessage('Importing from PT section...')
                    QtWidgets.QApplication.processEvents()
                    QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
                    # change bulk
                    # bulk = self.tc.interpolate_bulk(crange)
                    # self.tc.update_scriptfile(bulk=bulk, xsteps=self.spinSteps.value(), xvals=crange)
                    # only uni
                    last = None
                    for id, uni in data['section'].unilines.items():
                        if pt_line.intersects(uni.shape()):
                            isnew, id_uni = self.ps.getiduni(uni)
                            if isnew:
                                tcout, ans = self.tc.calc_px(uni.phases, uni.out, prange=prange, trange=(tm, tm))
                                status, res, output = self.tc.parse_logfile()
                                if status == 'ok':
                                    if len(res) > 1:
                                        # rescale pts from zoomed composition
                                        uni_ok = UniLine(
                                            id=id_uni,
                                            phases=uni.phases,
                                            out=uni.out,
                                            cmd=ans,
                                            variance=res.variance,
                                            y=res.y,
                                            x=res.c,
                                            output=output,
                                            results=res,
                                        )
                                        self.unimodel.appendRow(id_uni, uni_ok)
                                        self.changed = True
                                        last = id_uni

                    if last is not None:
                        self.uniview.resizeColumnsToContents()
                        idx = self.unimodel.getIndexID(last)
                        self.uniview.selectRow(idx.row())
                    # restore bulk
                    # self.tc.update_scriptfile(bulk=self.bulk, xsteps=self.spinSteps.value())
                    self.refresh_gui()
                    QtWidgets.QApplication.restoreOverrideCursor()
                    self.statusBar().showMessage('Data imported.')
                else:
                    qb = QtWidgets.QMessageBox
                    qb.critical(self, 'Error during openning', 'Unknown format of the project file', qb.Abort)

    @property
    def plot_title(self):
        ex = list(self.ps.excess)
        ex.insert(0, '')
        tm = sum(self.tc.trange) / 2
        return self.tc.axname + ' +'.join(ex) + ' (at {:g}°C)'.format(tm)

    def reset_limits(self):
        if self.ready:
            self.tminEdit.setText(fmt(0))
            self.tmaxEdit.setText(fmt(1))
            self.pminEdit.setText(fmt(self.tc.prange[0]))
            self.pmaxEdit.setText(fmt(self.tc.prange[1]))

    def uni_explore(self):
        if self.unisel.hasSelection():
            idx = self.unisel.selectedIndexes()
            uni = self.ps.unilines[self.unimodel.data(idx[0])]
            phases = uni.phases
            out = uni.out
            old_guesses = None
            self.statusBar().showMessage('Searching for invariant points...')
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            # set guesses temporarily when asked
            if uni.connected == 1 and self.checkUseInvGuess.isChecked():
                inv_id = sorted([uni.begin, uni.end])[1]
                if not self.ps.invpoints[inv_id].manual:
                    old_guesses = self.tc.update_scriptfile(
                        guesses=self.ps.invpoints[inv_id].ptguess(), get_old_guesses=True
                    )
            # Try out from phases
            extend = self.spinOver.value()
            tm = sum(self.tc.trange) / 2
            trange = (
                max(tm - self.rangeSpin.value() / 2, self.tc.trange[0]),
                min(tm + self.rangeSpin.value() / 2, self.tc.trange[1]),
            )
            prange = self.ax.get_ylim()
            ps = extend * (prange[1] - prange[0]) / 100
            prange = (max(prange[0] - ps, self.tc.prange[0]), min(prange[1] + ps, self.tc.prange[1]))
            crange = self.ax.get_xlim()
            cs = extend * (crange[1] - crange[0]) / 100
            crange = (max(crange[0] - cs, 0), min(crange[1] + cs, 1))
            # change bulk
            # bulk = self.tc.interpolate_bulk(crange)
            # self.tc.update_scriptfile(bulk=bulk, xsteps=self.spinSteps.value(), xvals=crange)
            out_section = []
            cand = []
            line = uni._shape()
            for ophase in phases.difference(out).difference(self.ps.excess):
                nout = out.union(set([ophase]))
                self.tc.calc_px(phases, nout, prange=prange, trange=trange, xvals=crange, steps=self.spinSteps.value())
                status, res, output = self.tc.parse_logfile()
                inv = InvPoint(phases=phases, out=nout)
                isnew, id = self.ps.getidinv(inv)
                if status == 'ok':
                    if isnew:
                        exists, inv_id = '', ''
                    else:
                        exists, inv_id = '*', str(id)
                    if len(res) > 1:
                        # rescale pts from zoomed composition
                        splt = interp1d(res.x, res.y, bounds_error=False, fill_value=np.nan)
                        splx = interp1d(res.x, res.c, bounds_error=False, fill_value=np.nan)
                        Ym = splt([tm])
                        Xm = splx([tm])
                        if not np.isnan(Ym[0]):
                            cand.append(
                                (line.project(Point(Xm[0], Ym[0])), Xm[0], Ym[0], exists, ' '.join(inv.out), inv_id)
                            )
                        else:
                            ix = abs(res.x - tm).argmin()
                            out_section.append((res.x[ix], res.y[ix], exists, ' '.join(inv.out), inv_id))
                    else:
                        out_section.append((res.x[0], res.y[0], exists, ' '.join(inv.out), inv_id))

            for ophase in set(self.tc.phases).difference(self.ps.excess).difference(phases):
                nphases = phases.union(set([ophase]))
                nout = out.union(set([ophase]))
                self.tc.calc_px(nphases, nout, prange=prange, trange=trange, xvals=crange, steps=self.spinSteps.value())
                status, res, output = self.tc.parse_logfile()
                inv = InvPoint(phases=nphases, out=nout)
                isnew, id = self.ps.getidinv(inv)
                if status == 'ok':
                    if isnew:
                        exists, inv_id = '', ''
                    else:
                        exists, inv_id = '*', str(id)
                    if len(res) > 1:
                        # rescale pts from zoomed composition
                        splt = interp1d(res.x, res.y, bounds_error=False, fill_value=np.nan)
                        splx = interp1d(res.x, res.c, bounds_error=False, fill_value=np.nan)
                        Ym = splt([tm])
                        Xm = splx([tm])
                        if not np.isnan(Ym[0]):
                            cand.append(
                                (line.project(Point(Xm[0], Ym[0])), Xm[0], Ym[0], exists, ' '.join(inv.out), inv_id)
                            )
                        else:
                            ix = abs(res.x - tm).argmin()
                            out_section.append((res.x[ix], res.y[ix], exists, ' '.join(inv.out), inv_id))
                    else:
                        out_section.append((res.x[0], res.y[0], exists, ' '.join(inv.out), inv_id))

            # set original ptguesses when needed
            if old_guesses is not None:
                self.tc.update_scriptfile(guesses=old_guesses)
            # restore bulk
            # self.tc.update_scriptfile(bulk=self.bulk, xsteps=self.spinSteps.value())
            QtWidgets.QApplication.restoreOverrideCursor()
            txt = ''
            n_format = '{:10.4f}{:10.4f}{:>2}{:>8}{:>6}\n'
            if cand:
                txt += '         {}         {} E     Out   Inv\n'.format(self.ps.x_var, self.ps.y_var)
                for cc in sorted(cand, key=lambda elem: elem[0]):
                    txt += n_format.format(*cc[1:])

                self.textOutput.setPlainText(txt)
                self.statusBar().showMessage('Searching done. Found {} invariant points.'.format(len(cand)))
            elif out_section:
                txt += 'Solutions with single point (need increase number of steps)\n'
                txt += '         {}         {} E     Out   Inv\n'.format(self.ps.x_var, self.ps.y_var)
                for cc in out_section:
                    txt += n_format.format(*cc)

                self.textOutput.setPlainText(txt)
                self.statusBar().showMessage(
                    'Searching done. Found {} invariant points and {} out of section.'.format(
                        len(cand), len(out_section)
                    )
                )
            else:
                self.statusBar().showMessage('No invariant points found.')

    def dogminer(self, event):
        if event.inaxes is not None:
            phases, out = self.get_phases_out()
            variance = self.spinVariance.value()
            doglevel = self.spinDoglevel.value()
            # change bulk
            # bulk = self.tc.interpolate_bulk(event.xdata) #use onebulk
            tm = sum(self.tc.trange) / 2
            self.statusBar().showMessage('Running dogmin with max variance of equilibria at {}...'.format(variance))
            # self.read_scriptfile()
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            tcout = self.tc.dogmin(phases, event.ydata, tm, variance, doglevel=doglevel, onebulk=event.xdata)
            self.read_scriptfile()
            QtWidgets.QApplication.restoreOverrideCursor()
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

    def do_calc(self, calcT, phases={}, out={}, run_tc=True):
        if self.ready:
            if run_tc:
                if phases == {} and out == {}:
                    phases, out = self.get_phases_out()
                self.statusBar().showMessage('Running THERMOCALC...')
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            ###########
            extend = self.spinOver.value()
            tm = sum(self.tc.trange) / 2
            prange = self.ax.get_ylim()
            ps = extend * (prange[1] - prange[0]) / 100
            prange = (max(prange[0] - ps, self.tc.prange[0]), min(prange[1] + ps, self.tc.prange[1]))
            crange = self.ax.get_xlim()
            cs = extend * (crange[1] - crange[0]) / 100
            crange = (max(crange[0] - cs, 0), min(crange[1] + cs, 1))
            # change bulk
            # bulk = self.tc.interpolate_bulk(crange)
            # self.tc.update_scriptfile(bulk=bulk, xsteps=self.spinSteps.value(), xvals=crange)
            if not run_tc:
                status, res, output, (phases, out, ans) = self.tc.parse_logfile(get_phases=True)
                uni_tmp = UniLine(phases=phases, out=out)
                isnew, id_uni = self.ps.getiduni(uni_tmp)
            if len(out) == 1:
                if run_tc:
                    uni_tmp = UniLine(phases=phases, out=out)
                    isnew, id_uni = self.ps.getiduni(uni_tmp)
                    tcout, ans = self.tc.calc_px(
                        uni_tmp.phases,
                        uni_tmp.out,
                        prange=prange,
                        trange=(tm, tm),
                        xvals=crange,
                        steps=self.spinSteps.value(),
                    )
                    self.logText.setPlainText('Working directory:{}\n\n'.format(self.tc.workdir) + tcout)
                    status, res, output = self.tc.parse_logfile()
                if status == 'bombed':
                    self.statusBar().showMessage('Bombed.')
                elif status == 'nir':
                    self.statusBar().showMessage('Nothing in range.')
                elif len(res) < 2:
                    self.statusBar().showMessage('Only one point calculated. Change range.')
                else:
                    # rescale pts from zoomed composition
                    uni = UniLine(
                        id=id_uni,
                        phases=uni_tmp.phases,
                        out=uni_tmp.out,
                        cmd=ans,
                        variance=res.variance,
                        y=res.y,
                        x=res.c,
                        output=output,
                        results=res,
                    )
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
                            if self.pushMerge.isChecked():
                                uni_old = self.ps.unilines[id_uni]
                                dt = {}
                                for p in uni_old.phases.difference(uni_old.out):
                                    dt[p] = []
                                for res in uni_old.results:
                                    for p in uni_old.phases.difference(uni_old.out):
                                        dt[p].append(res[p]['mode'])
                                N = len(uni_old.results)
                                for res, x, y in zip(uni.results, uni._x, uni._y):
                                    if x not in uni_old._x and y not in uni_old._y:
                                        idx = []
                                        for p in uni_old.phases.difference(uni_old.out):
                                            q = interp1d(dt[p], np.arange(N), fill_value='extrapolate')
                                            q_val = q(res[p]['mode'])
                                            if np.isfinite(q_val):
                                                idx.append(np.ceil(q_val))

                                        idx_clip = np.clip(np.array(idx, dtype=int), 0, N)
                                        values, counts = np.unique(idx_clip, return_counts=True)
                                        if counts.size > 0:
                                            nix = values[np.argmax(counts)]
                                            # insert data to temporary dict
                                            for p in uni_old.phases.difference(uni_old.out):
                                                dt[p].insert(nix, res[p]['mode'])
                                            # insert real data
                                            uni_old.results.insert(nix, res)
                                            uni_old._x = np.insert(uni_old._x, nix, x)
                                            uni_old._y = np.insert(uni_old._y, nix, y)
                                            N += 1
                                uni_old.output += uni.output
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
                                self.statusBar().showMessage('Univariant line {} merged.'.format(id_uni))
                            else:
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
                if run_tc:
                    inv_tmp = InvPoint(phases=phases, out=out)
                    isnew, id_inv = self.ps.getidinv(inv_tmp)
                    trange = (
                        max(tm - self.rangeSpin.value() / 2, self.tc.trange[0]),
                        min(tm + self.rangeSpin.value() / 2, self.tc.trange[1]),
                    )
                    tcout, ans = self.tc.calc_px(
                        inv_tmp.phases,
                        inv_tmp.out,
                        prange=prange,
                        trange=trange,
                        xvals=crange,
                        steps=self.spinSteps.value(),
                    )
                    self.logText.setPlainText('Working directory:{}\n\n'.format(self.tc.workdir) + tcout)
                    status, res, output = self.tc.parse_logfile()
                if status == 'bombed':
                    self.statusBar().showMessage('Bombed.')
                elif status == 'nir':
                    self.statusBar().showMessage('Nothing in range.')
                elif len(res) < 2:
                    self.statusBar().showMessage('Only one point calculated. Change steps.')
                else:
                    # rescale pts from zoomed composition
                    splp = interp1d(res.x, res.y, bounds_error=False, fill_value=np.nan)
                    splx = interp1d(res.x, res.c, bounds_error=False, fill_value=np.nan)
                    Ym = splp([tm])
                    Xm = splx([tm])
                    if np.isnan(Ym[0]):
                        status = 'nir'
                        self.statusBar().showMessage(
                            'Nothing in range, but exists out ouf section in T range {:.2f} - {:.2f}.'.format(
                                min(res.x), max(res.x)
                            )
                        )
                    else:
                        ix = np.argmin((res.y - Ym) ** 2)
                        inv = InvPoint(
                            id=id_inv,
                            phases=inv_tmp.phases,
                            out=inv_tmp.out,
                            cmd=ans,
                            variance=res.variance,
                            y=Ym,
                            x=Xm,
                            output=output,
                            results=res[ix : ix + 1],
                        )
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
            # self.tc.update_scriptfile(bulk=self.bulk, xsteps=self.spinSteps.value())
            QtWidgets.QApplication.restoreOverrideCursor()
        else:
            self.statusBar().showMessage('Project is not yet initialized.')
        self.pushMerge.setChecked(False)


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
        # highlight not finished invpoints - move to plot ???
        # if role == QtCore.Qt.ForegroundRole:
        #     all_uni = inv.all_unilines()
        #     isnew1, id = self.ps.getiduni(UniLine(phases=all_uni[0][0], out=all_uni[0][1]))
        #     isnew2, id = self.ps.getiduni(UniLine(phases=all_uni[1][0], out=all_uni[1][1]))
        #     isnew3, id = self.ps.getiduni(UniLine(phases=all_uni[2][0], out=all_uni[2][1]))
        #     isnew4, id = self.ps.getiduni(UniLine(phases=all_uni[3][0], out=all_uni[3][1]))
        #     if isnew1 or isnew2 or isnew3 or isnew4:
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
        """Append model row."""
        self.beginInsertRows(QtCore.QModelIndex(), len(self.invlist), len(self.invlist))
        self.invlist.append(id)
        self.ps.add_inv(id, inv)
        self.endInsertRows()

    def removeRow(self, index):
        """Remove model row."""
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
        """Append model row."""
        self.beginInsertRows(QtCore.QModelIndex(), len(self.unilist), len(self.unilist))
        self.unilist.append(id)
        self.ps.add_uni(id, uni)
        self.endInsertRows()

    def removeRow(self, index):
        """Remove model row."""
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
        # editor.showPopup()

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
        if role != QtCore.Qt.DisplayRole:
            return None
        else:
            if index.column() == 0:
                return self.doglist[index.row()]
            else:
                return dgm.label(excess=self.ps.excess)

    def appendRow(self, id, dgm):
        """Append model row."""
        self.beginInsertRows(QtCore.QModelIndex(), len(self.doglist), len(self.doglist))
        self.doglist.append(id)
        self.ps.add_dogmin(id, dgm)
        self.endInsertRows()

    def removeRow(self, index):
        """Remove model row."""
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
    """Add inv dialog class"""

    def __init__(self, ps, inv, isnew, parent=None):
        super(AddInv, self).__init__(parent)
        self.setupUi(self)
        self.labelEdit.setText(inv.label(ps.excess))
        # labels
        self.x_label.setText(ps.x_var)
        self.y_label.setText(ps.y_var)
        # Keep Results
        self.checkKeep.setCheckState(QtCore.Qt.Unchecked)
        if isnew:
            self.checkKeep.setEnabled(False)
        else:
            self.checkKeep.setEnabled(True)
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
    """Add uni dialog class"""

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
    """Choose uni pt dialog class"""

    def __init__(self, values, parent=None):
        super(UniGuess, self).__init__(parent)
        self.setupUi(self)
        self.comboPoint.addItems(values)

    def getValue(self):
        return self.comboPoint.currentIndex()


class AboutDialog(QtWidgets.QDialog):
    """About dialog"""

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

        swinfo = QtWidgets.QLabel(
            'Python:{} Qt:{} PyQt:{}'.format(sys.version.split()[0], QT_VERSION_STR, PYQT_VERSION_STR)
        )
        swinfo.setAlignment(QtCore.Qt.AlignCenter)

        github = QtWidgets.QLabel(
            'GitHub: <a href="https://github.com/ondrolexa/pypsbuilder">https://github.com/ondrolexa/pypsbuilder</a>'
        )
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
    """Output dialog"""

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
            warnings.filterwarnings("ignore", category=FutureWarning)
            npos = nx.kamada_kawai_layout(G, pos=nx.planar_layout(G))
        # npos = nx.planar_layout(G)
        # npos = nx.kamada_kawai_layout(G, pos=pos)
        widths = Normalize(vmin=0, vmax=len(edges))
        color = cm.get_cmap('tab20', len(edges))
        for ix, out in enumerate(edges):
            nx.draw_networkx_edges(
                G,
                npos,
                ax=ax,
                edgelist=edges[out],
                width=2 + 6 * widths(ix),
                alpha=0.5,
                edge_color=len(edges[out]) * [color(ix)],
                label=list(out)[0],
            )

        nx.draw_networkx_nodes(G, npos, ax=ax, node_color='k')
        nx.draw_networkx_labels(G, npos, labels, ax=ax, font_size=9, font_weight='bold', font_color='w')

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

    def _rectangle_intersection_(x1, y1, x2, y2):
        S1, S2, S3, S4 = _rect_inter_inner(x1, x2)
        S5, S6, S7, S8 = _rect_inter_inner(y1, y2)

        C1 = np.less_equal(S1, S2)
        C2 = np.greater_equal(S3, S4)
        C3 = np.less_equal(S5, S6)
        C4 = np.greater_equal(S7, S8)

        ii, jj = np.nonzero(C1 & C2 & C3 & C4)
        return ii, jj

    # Linear length along the line:
    d1 = np.cumsum(np.sqrt(np.diff(uni1._x) ** 2 + np.diff(ratio * uni1._y) ** 2))
    d1 = np.insert(d1, 0, 0) / d1[-1]
    d2 = np.cumsum(np.sqrt(np.diff(uni2._x) ** 2 + np.diff(ratio * uni2._y) ** 2))
    d2 = np.insert(d2, 0, 0) / d2[-1]
    try:
        s1x = interp1d(d1, uni1._x, kind='quadratic', fill_value='extrapolate')
        s1y = interp1d(d1, ratio * uni1._y, kind='quadratic', fill_value='extrapolate')
        s2x = interp1d(d2, uni2._x, kind='quadratic', fill_value='extrapolate')
        s2y = interp1d(d2, ratio * uni2._y, kind='quadratic', fill_value='extrapolate')
    except ValueError:
        s1x = interp1d(d1, uni1._x, fill_value='extrapolate')
        s1y = interp1d(d1, ratio * uni1._y, fill_value='extrapolate')
        s2x = interp1d(d2, uni2._x, fill_value='extrapolate')
        s2y = interp1d(d2, ratio * uni2._y, fill_value='extrapolate')
    p = np.linspace(-extra, 1 + extra, N)
    x1, y1 = s1x(p), s1y(p)
    x2, y2 = s2x(p), s2y(p)

    ii, jj = _rectangle_intersection_(x1, y1, x2, y2)
    n = len(ii)

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
        except Exception:
            T[:, i] = np.NaN

    in_range = (T[0, :] >= 0) & (T[1, :] >= 0) & (T[0, :] <= 1) & (T[1, :] <= 1)

    xy0 = T[2:, in_range]
    xy0 = xy0.T
    return xy0[:, 0], xy0[:, 1] / ratio


def ptbuilder():
    application = QtWidgets.QApplication(sys.argv)
    window = PTBuilder()
    desktop = QtWidgets.QDesktopWidget().availableGeometry()
    width = (desktop.width() - window.width()) // 2
    height = (desktop.height() - window.height()) // 2
    window.show()
    window.move(width, height)
    sys.exit(application.exec_())


def txbuilder():
    application = QtWidgets.QApplication(sys.argv)
    window = TXBuilder()
    desktop = QtWidgets.QDesktopWidget().availableGeometry()
    width = (desktop.width() - window.width()) // 2
    height = (desktop.height() - window.height()) // 2
    window.show()
    window.move(width, height)
    sys.exit(application.exec_())


def pxbuilder():
    application = QtWidgets.QApplication(sys.argv)
    window = PXBuilder()
    desktop = QtWidgets.QDesktopWidget().availableGeometry()
    width = (desktop.width() - window.width()) // 2
    height = (desktop.height() - window.height()) // 2
    window.show()
    window.move(width, height)
    sys.exit(application.exec_())
