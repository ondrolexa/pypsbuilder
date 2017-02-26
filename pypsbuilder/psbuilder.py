#!/usr/bin/env python
"""
Visual pseudosection builder for THERMOCALC
"""
# author: Ondrej Lexa
# website: petrol.natur.cuni.cz/~ondro
# last edited: February 2016

# TODO
# user-defined uni and inv will use actual phases and out selected

import sys
import os
import pickle
import gzip
import subprocess
import time
import itertools
import pathlib
from collections import OrderedDict
from pkg_resources import resource_filename

from PyQt5 import QtCore, QtGui, QtWidgets

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.colorbar import ColorbarBase
from mpl_toolkits.axes_grid1 import make_axes_locatable
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar)

from shapely.geometry import LineString, Point, MultiPoint
from shapely.ops import polygonize, linemerge, unary_union
from shapely.prepared import prep
from scipy.interpolate import Rbf
from tqdm import tqdm, trange
from descartes import PolygonPatch

from .ui_psbuilder import Ui_PSBuilder
from .ui_addinv import Ui_AddInv
from .ui_adduni import Ui_AddUni
from .ui_uniguess import Ui_UniGuess

__version__ = '2.1.0devel'
# Make sure that we are using QT5
matplotlib.use('Qt5Agg')

matplotlib.rcParams['xtick.direction'] = 'out'
matplotlib.rcParams['ytick.direction'] = 'out'

popen_kw = dict(stdout=subprocess.PIPE, stdin=subprocess.PIPE,
               stderr=subprocess.STDOUT, universal_newlines=False)

TCenc = 'mac-roman'

unihigh_kw = dict(lw=3, alpha=1, marker='o', ms=4, color='red', zorder=10)
invhigh_kw = dict(alpha=1, ms=8, color='red', zorder=10)
outhigh_kw = dict(lw=3, alpha=1, marker=None, ms=4, color='red', zorder=10)

class PSBuilder(QtWidgets.QMainWindow, Ui_PSBuilder):
    """Main class
    """
    def __init__(self, parent=None):
        super(PSBuilder, self).__init__(parent)
        self.setupUi(self)
        res = QtWidgets.QDesktopWidget().screenGeometry()
        self.resize(min(1024, res.width() - 10), min(768, res.height() - 10))
        self.setWindowTitle('PSBuilder')
        window_icon = resource_filename(__name__, 'images/pypsbuilder.png')
        self.setWindowIcon(QtGui.QIcon(window_icon))
        self.__changed = False
        self.about_dialog = AboutDialog(__version__)
        self.unihigh = None
        self.invhigh = None
        self.outhigh = None

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

        # SET OUTPUT TEXT
        f = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.textOutput.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.textOutput.setReadOnly(True)
        self.textOutput.setFont(f)
        self.textFullOutput.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.textFullOutput.setReadOnly(True)
        self.textFullOutput.setFont(f)

        self.initViewModels()

        # CONNECT SIGNALS
        self.actionNew.triggered.connect(self.initProject)
        self.actionOpen.triggered.connect(self.openProject)
        self.actionSave.triggered.connect(self.saveProject)
        self.actionSave_as.triggered.connect(self.saveProjectAs)
        self.actionQuit.triggered.connect(self.close)
        self.actionExport_Drawpd.triggered.connect(self.gendrawpd)
        self.actionAbout.triggered.connect(self.about_dialog.exec)
        self.pushCalcTatP.clicked.connect(lambda: self.do_calc(True))
        self.pushCalcPatT.clicked.connect(lambda: self.do_calc(False))
        self.pushApplySettings.clicked.connect(lambda: self.apply_setting(5))
        self.pushResetSettings.clicked.connect(lambda: self.apply_setting(8))
        self.pushFromAxes.clicked.connect(lambda: self.apply_setting(2))
        self.tabMain.currentChanged.connect(lambda: self.apply_setting(4))
        self.pushReadScript.clicked.connect(self.read_scriptfile)
        self.pushSaveScript.clicked.connect(self.save_scriptfile)
        self.actionReload.triggered.connect(self.reinitialize)
        self.actionGenerate.triggered.connect(self.generate)
        self.pushGuessUni.clicked.connect(self.unisel_guesses)
        self.pushGuessInv.clicked.connect(self.invsel_guesses)
        self.pushInvAuto.clicked.connect(self.auto_inv_calc)
        self.pushUniZoom.clicked.connect(self.zoom_to_uni)
        self.pushUniZoom.setCheckable(True)
        self.pushManual.toggled.connect(self.add_userdefined)
        self.pushManual.setCheckable(True)
        self.pushInvRemove.clicked.connect(self.remove_inv)
        self.pushUniRemove.clicked.connect(self.remove_uni)
        self.tabOutput.tabBarDoubleClicked.connect(self.show_output)
        self.splitter_bottom.setSizes((400, 100))

        self.phaseview.doubleClicked.connect(self.show_out)
        self.uniview.doubleClicked.connect(self.show_uni)
        self.invview.doubleClicked.connect(self.show_inv)
        self.invview.customContextMenuRequested[QtCore.QPoint].connect(self.invviewRightClicked)
        # additional keyboard shortcuts
        self.scCalcTatP = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+T"), self)
        self.scCalcTatP.activated.connect(lambda: self.do_calc(True))
        self.scCalcPatT = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+P"), self)
        self.scCalcPatT.activated.connect(lambda: self.do_calc(False))
        self.scHome = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+H"), self)
        self.scHome.activated.connect(self.toolbar.home)

        self.app_settings()
        self.populate_recent()
        self.ready = False
        self.statusBar().showMessage('PSBuilder version {} (c) Ondrej Lexa 2016'. format(__version__))

    def initViewModels(self):
        # INVVIEW
        self.invmodel = InvModel(self.invview)
        self.invview.setModel(self.invmodel)
        # enable sorting
        self.invview.setSortingEnabled(False)
        # hide column
        self.invview.setColumnHidden(2, True)
        # select rows
        self.invview.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.invview.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.invview.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.invview.horizontalHeader().hide()
        self.invsel = self.invview.selectionModel()
        # default unconnected ghost
        self.invmodel.appendRow([0, 'Unconnected', {}])
        self.invview.setRowHidden(0, True)
        self.invview.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # signals
        self.invsel.selectionChanged.connect(self.sel_changed)

        # UNIVIEW
        self.unimodel = UniModel(self.uniview)
        self.uniview.setModel(self.unimodel)
        # enable sorting
        self.uniview.setSortingEnabled(False)
        # hide column
        self.uniview.setColumnHidden(4, True)
        self.uniview.setItemDelegateForColumn(2, ComboDelegate(self, self.invmodel))
        self.uniview.setItemDelegateForColumn(3, ComboDelegate(self, self.invmodel))
        # select rows
        self.uniview.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.uniview.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.uniview.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.uniview.horizontalHeader().hide()
        # edit trigger
        self.uniview.setEditTriggers(QtWidgets.QAbstractItemView.CurrentChanged | QtWidgets.QAbstractItemView.SelectedClicked)
        self.uniview.viewport().installEventFilter(self)
        # signals
        self.unimodel.dataChanged.connect(self.uni_edited)
        self.unisel = self.uniview.selectionModel()
        self.unisel.selectionChanged.connect(self.sel_changed)

    def app_settings(self, write=False):
        # Applicatiom settings
        builder_settings = QtCore.QSettings('LX', 'pypsbuilder')
        if write:
            builder_settings.setValue("steps", self.spinSteps.value())
            builder_settings.setValue("precision", self.spinPrec.value())
            builder_settings.setValue("label_uni", self.checkLabelUni.checkState())
            builder_settings.setValue("label_inv", self.checkLabelInv.checkState())
            builder_settings.setValue("label_alpha", self.spinAlpha.value())
            builder_settings.setValue("label_usenames", self.checkLabels.checkState())
            builder_settings.setValue("export_areas", self.checkAreas.checkState())
            builder_settings.setValue("export_partial", self.checkPartial.checkState())
            builder_settings.setValue("overwrite", self.checkOverwrite.checkState())
            builder_settings.beginWriteArray("recent")
            for ix, f in enumerate(self.recent):
                builder_settings.setArrayIndex(ix)
                builder_settings.setValue("projfile", f)
            builder_settings.endArray()
        else:
            self.spinSteps.setValue(builder_settings.value("steps", 50, type=int))
            self.spinPrec.setValue(builder_settings.value("precision", 1, type=int))
            self.checkLabelUni.setCheckState(builder_settings.value("label_uni", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.checkLabelInv.setCheckState(builder_settings.value("label_inv", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.spinAlpha.setValue(builder_settings.value("label_alpha", 50, type=int))
            self.checkLabels.setCheckState(builder_settings.value("label_usenames", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.checkAreas.setCheckState(builder_settings.value("export_areas", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.checkPartial.setCheckState(builder_settings.value("export_partial", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.checkOverwrite.setCheckState(builder_settings.value("overwrite", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            self.recent = []
            n = builder_settings.beginReadArray("recent")
            for ix in range(n):
                builder_settings.setArrayIndex(ix)
                self.recent.append(builder_settings.value("projfile", type=str))
            builder_settings.endArray()

    def populate_recent(self):
        self.menuOpen_recent.clear()
        for f in self.recent:
            self.menuOpen_recent.addAction(os.path.basename(f), lambda f=f: self.openProject(False, projfile=f))

    def initProject(self):
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
        workdir = qd.getExistingDirectory(self, "Select Directory",
                                          os.path.expanduser('~'),
                                          qd.ShowDirsOnly)
        if workdir:
            self.workdir = workdir
            # init THERMOCALC
            if self.doInit():
                self.initViewModels()
                self.ready = True
                self.project = None
                self.changed = True
                # update settings tab
                self.apply_setting(4)
                # read scriptfile
                self.read_scriptfile()
                # update plot
                self.figure.clear()
                self.plot()
                self.statusBar().showMessage('Ready')

    def doInit(self):
        """Parse configs and test TC settings
        """
        try:
            # default exe
            if sys.platform.startswith('win'):
                tcpat = 'tc3*.exe'
                drpat = 'dr1*.exe'
            elif sys.platform.startswith('linux'):
                tcpat = 'tc3*L'
                drpat = 'dr1*L'
            else:
                tcpat = 'tc3*'
                drpat = 'dr1*'
            # THERMOCALC exe
            errtitle = 'Initialize project error!'
            tcexe = None
            for p in pathlib.Path(self.workdir).glob(tcpat):
                if p.is_file() and os.access(str(p), os.X_OK):
                    tcexe = p.name
                    break
            if not tcexe:
                errinfo = 'No THERMOCALC executable in working directory.'
                raise Exception()
            self.tcexeEdit.setText(tcexe)
            # DRAWPD exe
            drexe = None
            for p in pathlib.Path(self.workdir).glob(drpat):
                if p.is_file() and os.access(str(p), os.X_OK):
                    drexe = p.name
                    break
            if not drexe:
                errinfo = 'No drawpd executable in working directory.'
                raise Exception()
            self.drawpdexeEdit.setText(drexe)
            # tc-prefs file
            if not os.path.exists(self.prefsfile):
                errinfo = 'No tc-prefs.txt file in working directory.'
                raise Exception()
            errinfo = 'tc-prefs.txt file in working directory cannot be accessed.'
            for line in open(self.prefsfile, 'r'):
                kw = line.split()
                if kw != []:
                    if kw[0] == 'scriptfile':
                        self.bname = kw[1]
                        if not os.path.exists(self.scriptfile):
                            errinfo = 'tc-prefs: scriptfile tc-' + self.bname + '.txt does not exists in your working directory.'
                            raise Exception()
                    if kw[0] == 'calcmode':
                        if kw[1] != '1':
                            errinfo = 'tc-prefs: calcmode must be 1.'
                            raise Exception()

            errtitle = 'Scriptfile error!'
            self.excess = set()
            self.trange = (200., 1000.)
            self.prange = (0.1, 20.)
            check = {'axfile': False, 'setbulk': False, 'printbulkinfo': False,
                     'setexcess': False, 'drawpd': False, 'printxyz': False}
            errinfo = 'Check your scriptfile.'
            with open(self.scriptfile, 'r', encoding=TCenc) as f:
                lines = f.readlines()
            gsb, gse = False, False
            for line in lines:
                kw = line.split('%')[0].split()
                if '{PSBGUESS-BEGIN}' in line:
                    gsb = True
                if '{PSBGUESS-END}' in line:
                    gse = True
                if kw == ['*']:
                    break
                if kw:
                    if kw[0] == 'axfile':
                        errinfo = 'Wrong argument for axfile keyword in scriptfile.'
                        self.axname = kw[1]
                        if not os.path.exists(self.axfile):
                            errinfo = 'Axfile tc-' + self.axname + '.txt does not exists in working directory'
                            raise Exception()
                        check['axfile'] = True
                    elif kw[0] == 'setdefTwindow':
                        errinfo = 'Wrong arguments for setdefTwindow keyword in scriptfile.'
                        self.trange = (float(kw[-2]), float(kw[-1]))
                    elif kw[0] == 'setdefPwindow':
                        errinfo = 'Wrong arguments for setdefPwindow keyword in scriptfile.'
                        self.prange = (float(kw[-2]), float(kw[-1]))
                    elif kw[0] == 'setbulk':
                        errinfo = 'Wrong arguments for setbulk keyword in scriptfile.'
                        self.bulk = kw[1:]
                        if 'yes' in self.bulk:
                            self.bulk.remove('yes')
                        check['setbulk'] = True
                    elif kw[0] == 'setexcess':
                        errinfo = 'Wrong argument for setexcess keyword in scriptfile.'
                        self.excess = set(kw[1:])
                        if 'yes' in self.excess:
                            self.excess.remove('yes')
                        if 'no' in self.excess:
                            self.excess = set()
                        if 'ask' in self.excess:
                            errinfo = 'Setexcess must not be set to ask.'
                            raise Exception()
                        check['setexcess'] = True
                    elif kw[0] == 'calctatp':
                        errinfo = 'Wrong argument for calctatp keyword in scriptfile.'
                        if not kw[1] == 'ask':
                            errinfo = 'Calctatp must be set to ask.'
                            raise Exception()
                    elif kw[0] == 'drawpd':
                        errinfo = 'Wrong argument for drawpd keyword in scriptfile.'
                        if kw[1] == 'no':
                            errinfo = 'Drawpd must be set to yes.'
                            raise Exception()
                        check['drawpd'] = True
                    elif kw[0] == 'printbulkinfo':
                        errinfo = 'Wrong argument for printbulkinfo keyword in scriptfile.'
                        if kw[1] == 'no':
                            errinfo = 'Printbulkinfo must be set to yes.'
                            raise Exception()
                        check['printbulkinfo'] = True
                    elif kw[0] == 'printxyz':
                        errinfo = 'Wrong argument for printxyz keyword in scriptfile.'
                        if kw[1] == 'no':
                            errinfo = 'Printxyz must be set to yes.'
                            raise Exception()
                        check['printxyz'] = True
                    elif kw[0] == 'dogmin':
                        errinfo = 'Wrong argument for dogmin keyword in scriptfile.'
                        if not kw[1] == 'no':
                            errinfo = 'Dogmin must be set to no.'
                            raise Exception()
                    elif kw[0] == 'fluidpresent':
                        errinfo = 'Fluidpresent must be deleted from scriptfile.'
                        raise Exception()
                    elif kw[0] == 'seta':
                        errinfo = 'Wrong argument for seta keyword in scriptfile.'
                        if not kw[1] == 'no':
                            errinfo = 'Seta must be set to no.'
                            raise Exception()
                    elif kw[0] == 'setmu':
                        errinfo = 'Wrong argument for setmu keyword in scriptfile.'
                        if not kw[1] == 'no':
                            errinfo = 'Setmu must be set to no.'
                            raise Exception()
                    elif kw[0] == 'usecalcq':
                        errinfo = 'Wrong argument for usecalcq keyword in scriptfile.'
                        if kw[1] == 'ask':
                            errinfo = 'Usecalcq must be yes or no.'
                            raise Exception()
                    elif kw[0] == 'pseudosection':
                        errinfo = 'Wrong argument for pseudosection keyword in scriptfile.'
                        if kw[1] == 'ask':
                            errinfo = 'Pseudosection must be yes or no.'
                            raise Exception()
                    elif kw[0] == 'zeromodeiso':
                        errinfo = 'Wrong argument for zeromodeiso keyword in scriptfile.'
                        if not kw[1] == 'yes':
                            errinfo = 'Zeromodeiso must be set to yes.'
                            raise Exception()
                    elif kw[0] == 'setmodeiso':
                        errinfo = 'Wrong argument for setmodeiso keyword in scriptfile.'
                        if not kw[1] == 'yes':
                            errinfo = 'Setmodeiso must be set to yes.'
                            raise Exception()
                    elif kw[0] == 'convliq':
                        errinfo = 'Convliq not yet supported.'
                        raise Exception()
                    elif kw[0] == 'setiso':
                        errinfo = 'Wrong argument for setiso keyword in scriptfile.'
                        if kw[1] != 'no':
                            errinfo = 'Setiso must be set to no.'
                            raise Exception()

            if not check['axfile']:
                errinfo = 'Axfile name must be provided in scriptfile.'
                raise Exception()
            if not check['setbulk']:
                errinfo = 'Setbulk must be provided in scriptfile.'
                raise Exception()
            if not check['setexcess']:
                errinfo = 'Setexcess must not be set to ask. To suppress this error put empty setexcess keyword to your scriptfile.'
                raise Exception()
            if not check['drawpd']:
                errinfo = 'Drawpd must be set to yes. To suppress this error put drawpd yes keyword to your scriptfile.'
                raise Exception()
            if not check['printbulkinfo']:
                errinfo = 'Printbulkinfo must be set to yes. To suppress this error put printbulkinfo yes keyword to your scriptfile.'
                raise Exception()
            if not check['printxyz']:
                errinfo = 'Printxyz must be set to yes. To suppress this error put printxyz yes keyword to your scriptfile.'
                raise Exception()
            if not (gsb and gse):
                errinfo = 'There are not {PSBGUESS-BEGIN} and {PSBGUESS-END} tags in your scriptfile.'
                raise Exception()

            # What???
            nc = 0
            for i in self.axname:
                if i.isupper():
                    nc += 1
            self.nc = nc
            # run tc to initialize
            errtitle = 'Initial THERMOCALC run error!'
            tcout = self.runprog(self.tc, '\nkill\n\n')
            if 'BOMBED' in tcout:
                errinfo = tcout.split('BOMBED')[1].split('\n')[0]
                raise Exception()
            else:
                errinfo = 'Error parsing initial THERMOCALC output'
                self.phases = tcout.split('choose from:')[1].split('\n')[0].split()
                self.phases.sort()
                self.vre = int(tcout.split('variance of required equilibrium ')[1].split('\n')[0].split('(')[1].split('?')[0])
                self.deftrange = self.trange
                self.defprange = self.prange
                self.tcversion = tcout.split('\n')[0]
            # disconnect signals
            try:
                self.phasemodel.itemChanged.disconnect(self.phase_changed)
            except Exception:
                pass
            errtitle = ''
            errinfo = ''
            self.phasemodel.clear()
            self.outmodel.clear()
            for p in self.phases:
                if p not in self.excess:
                    item = QtGui.QStandardItem(p)
                    item.setCheckable(True)
                    item.setSizeHint(QtCore.QSize(40, 20))
                    self.phasemodel.appendRow(item)
            # connect signal
            self.phasemodel.itemChanged.connect(self.phase_changed)
            self.textOutput.clear()
            self.textFullOutput.clear()
            self.unihigh = None
            self.invhigh = None
            self.outhigh = None
            self.pushUniZoom.setChecked(False)
            return True
        except BaseException as e:
            qb = QtWidgets.QMessageBox
            qb.critical(self, errtitle, errinfo + '\n' + str(e), qb.Abort)
            return False

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
            qd = QtWidgets.QFileDialog
            filt = 'pypsbuilder project (*.psb)'
            projfile = qd.getOpenFileName(self, 'Open project',
                                          os.path.expanduser('~'),
                                          filt)[0]
        if os.path.exists(projfile):
            stream = gzip.open(projfile, 'rb')
            data = pickle.load(stream)
            stream.close()
            # set actual working dir in case folder was moved
            self.workdir = os.path.dirname(projfile)
            if self.doInit():
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
                # settings
                self.trange = data['trange']
                self.prange = data['prange']
                # views
                if data['version'] < '2.1.0':
                    for row in data['invlist']:
                        r = dict(phases=row[2]['phases'], out=row[2]['out'], cmd=row[2]['cmd'],
                                 variance=-1, p=row[2]['p'], T=row[2]['T'], manual=True,
                                 output='Imported invariant point.')
                        label = self.format_label(row[2]['phases'], row[2]['out'])
                        self.invmodel.appendRow((row[0], label, r))
                    self.invview.resizeColumnsToContents()
                    for row in data['unilist']:
                        r = dict(phases=row[4]['phases'], out=row[4]['out'], cmd=row[4]['cmd'],
                                 variance=-1, p=row[4]['p'], T=row[4]['T'], manual=True,
                                 output='Imported univariant line.')
                        label = self.format_label(row[4]['phases'], row[4]['out'])
                        self.unimodel.appendRow((row[0], label, row[2], row[3], r))
                    self.adapt_uniview()
                    for row in tqdm(data['invlist'], desc='invlist'):
                        tcout = self.runprog(self.tc, row[2]['cmd'])
                        status, variance, pts, res, output = parse_logfile(self.logfile)
                        if status == 'ok':
                            r = dict(phases=row[2]['phases'], out=row[2]['out'], cmd=row[2]['cmd'],
                                     variance=variance, p=pts[0], T=pts[1], manual=False,
                                     output=output, results=res)
                            label = self.format_label(row[2]['phases'], row[2]['out'])
                            isnew, id = self.getidinv(r)
                            urow = self.invmodel.getRowFromId(id)
                            urow[1] = label
                            urow[2] = r
                            # retrim affected
                            for urow in self.unimodel.unilist:
                                if urow[2] == id or urow[3] == id:
                                    self.trimuni(urow)
                    self.invview.resizeColumnsToContents()
                    for row in tqdm(data['unilist'], desc='unilist'):
                        tcout = self.runprog(self.tc, row[4]['cmd'])
                        status, variance, pts, res, output = parse_logfile(self.logfile)
                        if status == 'ok':
                            r = dict(phases=row[4]['phases'], out=row[4]['out'], cmd=row[4]['cmd'],
                                     variance=variance, p=pts[0], T=pts[1], manual=False,
                                     output=output, results=res)
                            label = self.format_label(row[4]['phases'], row[4]['out'])
                            isnew, id = self.getiduni(r)
                            urow = self.unimodel.getRowFromId(id)
                            urow[1] = label
                            urow[4] = r
                            self.trimuni(urow)
                    self.adapt_uniview()
                else:
                    for row in data['unilist']:
                        # fix older
                        row[4]['phases'] = row[4]['phases'].union(self.excess)
                        row[1] = (' '.join(sorted(list(row[4]['phases'].difference(self.excess)))) +
                                  ' - ' +
                                  ' '.join(sorted(list(row[4]['out']))))
                        self.unimodel.appendRow(row)
                    self.adapt_uniview()
                    for row in data['invlist']:
                        # fix older
                        row[2]['phases'] = row[2]['phases'].union(self.excess)
                        row[1] = (' '.join(sorted(list(row[2]['phases'].difference(self.excess)))) +
                                  ' - ' +
                                  ' '.join(sorted(list(row[2]['out']))))
                        self.invmodel.appendRow(row)
                    self.invview.resizeColumnsToContents()
                # cutting
                for row in self.unimodel.unilist:
                    self.trimuni(row)
                # update executables
                if 'tcexe' in data:
                    p = pathlib.Path(self.workdir, data['tcexe'])
                    if p.is_file() and os.access(str(p), os.X_OK):
                        self.tcexeEdit.setText(p.name)
                if 'drexe' in data:
                    p = pathlib.Path(self.workdir, data['drexe'])
                    if p.is_file() and os.access(str(p), os.X_OK):
                        self.drawpdexeEdit.setText(p.name)
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
                # read scriptfile
                self.read_scriptfile()
                # update settings tab
                self.apply_setting(4)
                # update plot
                self.figure.clear()
                self.plot()
                self.statusBar().showMessage('Project loaded.')
        else:
            if projfile in self.recent:
                self.recent.pop(self.recent.index(projfile))
                self.app_settings(write=True)
                self.populate_recent()

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
            trange = self.trange
            prange = self.prange
            self.doInit()
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
            # adapt names to excess changes
            for row in self.unimodel.unilist:
                row[1] = (' '.join(sorted(list(row[4]['phases'].difference(self.excess)))) +
                          ' - ' +
                          ' '.join(sorted(list(row[4]['out']))))
            self.adapt_uniview()
            for row in self.invmodel.invlist[1:]:
                row[1] = (' '.join(sorted(list(row[2]['phases'].difference(self.excess)))) +
                          ' - ' +
                          ' '.join(sorted(list(row[2]['out']))))
            self.invview.resizeColumnsToContents()
            # settings
            self.trange = trange
            self.prange = prange
            self.statusBar().showMessage('Project re-initialized from scriptfile.')
            self.changed = True
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def saveProject(self):
        """Open working directory and initialize project
        """
        if self.ready:
            if self.project is None:
                filename = QtWidgets.QFileDialog.getSaveFileName(self, 'Save current project', self.workdir, 'pypsbuilder project (*.psb)')[0]
                if filename:
                    if not filename.lower().endswith('.psb'):
                        filename = filename + '.psb'
                    self.project = filename
                    self.do_save()
            else:
                self.do_save()

    def saveProjectAs(self):
        """Open working directory and initialize project
        """
        if self.ready:
            filename = QtWidgets.QFileDialog.getSaveFileName(self, 'Save current project as', self.workdir, 'pypsbuilder project (*.psb)')[0]
            if filename:
                if not filename.lower().endswith('.psb'):
                    filename = filename + '.psb'
                self.project = filename
                self.do_save()

    def do_save(self):
        """Open working directory and initialize project
        """
        if self.project:
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
                    'trange': self.trange,
                    'prange': self.prange,
                    'unilist': self.unimodel.unilist,
                    'invlist': self.invmodel.invlist[1:],
                    'tcexe': self.tcexeEdit.text(),
                    'drexe': self.drawpdexeEdit.text(),
                    'version': __version__}
            # do save
            stream = gzip.open(self.project, 'wb')
            pickle.dump(data, stream)
            stream.close()
            self.changed = False
            if self.project in self.recent:
                self.recent.pop(self.recent.index(self.project))
            self.recent.insert(0, self.project)
            if len(self.recent) > 15:
                self.recent = self.recent[:15]
            self.populate_recent()
            self.app_settings(write=True)
            self.statusBar().showMessage('Project saved.')

    def runprog(self, exe, instr):
        # get list of available phases
        if sys.platform.startswith('win'):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags = 1
            startupinfo.wShowWindow = 0
        else:
            startupinfo = None
        p = subprocess.Popen(exe, cwd=self.workdir, startupinfo=startupinfo, **popen_kw)
        output = p.communicate(input=instr.encode(TCenc))[0].decode(TCenc)
        sys.stdout.flush()
        self.logText.setPlainText('Working directory:{}\n\n'.format(self.workdir) + output)
        return output

    def generate(self):
        if self.ready:
            qd = QtWidgets.QFileDialog
            filt = 'Text files (*.txt);;All files (*.*)'
            tpfile = qd.getOpenFileName(self, 'Open text file',
                                        self.workdir, filt)[0]
            if tpfile:
                tp = []
                tpok = True
                with open(tpfile, 'r', encoding=TCenc) as tfile:
                    for line in tfile:
                        n = line.split('%')[0].strip()
                        if n != '':
                            if '-' not in n:
                                tpok = False
                            else:
                                tp.append(n)
                if tpok and tp:
                    for r in tp:
                        po = r.split('-')
                        out = set(po[1].split())
                        phases = set(po[0].split()).union(out).union(self.excess)
                        self.do_calc(True, phases=phases, out=out)
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    @property
    def tc(self):
        return os.path.join(self.workdir, self.tcexeEdit.text())

    @property
    def dr(self):
        return os.path.join(self.workdir, self.drawpdexeEdit.text())

    @property
    def scriptfile(self):
        return os.path.join(self.workdir, 'tc-' + self.bname + '.txt')

    @property
    def drfile(self):
        return os.path.join(self.workdir, 'tc-' + self.bname + '-dr.txt')

    @property
    def logfile(self):
        return os.path.join(self.workdir, 'tc-log.txt')

    @property
    def drawpdfile(self):
        return os.path.join(self.workdir, 'dr-' + self.bname + '.txt')

    @property
    def tcinvestigatorfile(self):
        return os.path.join(self.workdir, 'assemblages.txt')

    @property
    def axfile(self):
        return os.path.join(self.workdir, 'tc-' + self.axname + '.txt')

    @property
    def prefsfile(self):
        return os.path.join(self.workdir, 'tc-prefs.txt')

    @property
    def changed(self):
        return self.__changed

    @changed.setter
    def changed(self, status):
        self.__changed = status
        if self.project is None:
            title = 'PSbuilder - New project - {}'.format(self.tcversion)
        else:
            title = 'PSbuilder - {} - {}'.format(os.path.basename(self.project), self.tcversion)
        if status:
            title += '*'
        self.setWindowTitle(title)

    def format_coord(self, x, y):
        prec = self.spinPrec.value()
        return 'T={:.{prec}f} p={:.{prec}f}'.format(x, y, prec=prec)

    def show_output(self, int):
        if self.ready:
            if int == 0:
                dia = OutputDialog('Modes', self.textOutput.toPlainText())
                dia.exec()
            if int == 1:
                dia = OutputDialog('TC output', self.textFullOutput.toPlainText())
                dia.exec()

    def adapt_uniview(self):
        self.uniview.resizeColumnsToContents()
        self.uniview.setColumnWidth(2, 40)
        self.uniview.setColumnWidth(3, 40)

    def clean_high(self):
        if self.unihigh is not None:
            try:
                self.unihigh[0].remove()
            except:
                pass
            self.unihigh = None
            self.textOutput.clear()
            self.textFullOutput.clear()
            self.canvas.draw()
        if self.invhigh is not None:
            try:
                self.invhigh[0].remove()
            except:
                pass
            self.invhigh = None
            self.textOutput.clear()
            self.textFullOutput.clear()
            self.canvas.draw()
        if self.outhigh is not None:
            try:
                self.outhigh[0].remove()
            except:
                pass
            self.outhigh = None
            self.canvas.draw()

    def sel_changed(self):
        self.clean_high()
        if self.pushUniZoom.isChecked():
            idx = self.unisel.selectedIndexes()
            k = self.unimodel.getRow(idx[0])
            T, p = self.get_trimmed_uni(k)
            dT = (T.max() - T.min()) / 5
            dp = (p.max() - p.min()) / 5
            self.ax.set_xlim([T.min() - dT, T.max() + dT])
            self.ax.set_ylim([p.min() - dp, p.max() + dp])
            self.canvas.draw()

    def invsel_guesses(self):
        if self.invsel.hasSelection():
            idx = self.invsel.selectedIndexes()
            r = self.invmodel.data(idx[2])
            if not r['manual']:
                update_guesses(self.scriptfile, r['results'][0]['ptguess'])
                self.read_scriptfile()
                self.statusBar().showMessage('Guesses set.')
            else:
                self.statusBar().showMessage('Guesses cannot be set from user-defined invariant point.')

    def unisel_guesses(self):
        if self.unisel.hasSelection():
            idx = self.unisel.selectedIndexes()
            r = self.unimodel.data(idx[4])
            if not r['manual']:
                l = ['p = {}, T = {}'.format(p, T) for p, T in zip(r['p'], r['T'])]
                uniguess = UniGuess(l, self)
                respond = uniguess.exec()
                if respond == QtWidgets.QDialog.Accepted:
                    ix = uniguess.getValue()
                    update_guesses(self.scriptfile, r['results'][ix]['ptguess'])
                    self.read_scriptfile()
                    self.statusBar().showMessage('Guesses set.')
            else:
                self.statusBar().showMessage('Guesses cannot be set from user-defined univariant line.')

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
        return set(phases).union(self.excess), set(out)

    def set_phaselist(self, r, show_output=True):
        for i in range(self.phasemodel.rowCount()):
            item = self.phasemodel.item(i)
            if item.text() in r['phases'] or item.text() in r['out']:
                item.setCheckState(QtCore.Qt.Checked)
            else:
                item.setCheckState(QtCore.Qt.Unchecked)
        # select out
        for i in range(self.outmodel.rowCount()):
            item = self.outmodel.item(i)
            if item.text() in r['out']:
                item.setCheckState(QtCore.Qt.Checked)
            else:
                item.setCheckState(QtCore.Qt.Unchecked)
        if show_output:
            if not r['manual']:
                mlabels = sorted(list(r['results'][0]['data'].keys()))
                txt = ''
                h_format = '{:>10}{:>10}' + '{:>8}' * len(mlabels)
                n_format = '{:10.4f}{:10.4f}' + '{:8.5f}' * len(mlabels)
                txt += h_format.format('p', 'T', *mlabels)
                txt += '\n'
                for p, T, res in zip(r['p'], r['T'], r['results']):
                    row = [p, T] + [res['data'][lbl]['mode'] for lbl in mlabels]
                    txt += n_format.format(*row)
                    txt += '\n'
                if len(r['results']) > 5:
                    txt += h_format.format('p', 'T', *mlabels)
                self.textOutput.setPlainText(txt)
            else:
                self.textOutput.setPlainText(r['output'])
            self.textFullOutput.setPlainText(r['output'])

    def show_uni(self, index):
        row = self.unimodel.getRow(index)
        self.clean_high()
        self.set_phaselist(row[4], show_output=True)
        T, p = self.get_trimmed_uni(row)
        self.unihigh = self.ax.plot(T, p, '-', **unihigh_kw)
        self.canvas.draw()
        # if self.pushUniZoom.isChecked():
        #     self.zoom_to_uni(True)

    def uni_edited(self, index):
        row = self.unimodel.getRow(index)
        # self.set_phaselist(row[4])
        self.trimuni(row)
        self.changed = True
        # update plot
        self.plot()
        # if self.pushUniZoom.isChecked():
        #     self.zoom_to_uni(True)

    def show_inv(self, index):
        dt = self.invmodel.getData(index, 'Data')
        self.clean_high()
        self.set_phaselist(dt, show_output=True)
        self.invhigh = self.ax.plot(dt['T'], dt['p'], 'o', **invhigh_kw)
        self.canvas.draw()

    def show_out(self, index):
        out = self.phasemodel.itemFromIndex(index).text()
        self.clean_high()
        oT = []
        op = []
        for r in self.unimodel.unilist:
            if out in r[4]['out']:
                T, p = self.get_trimmed_uni(r)
                oT.append(T)
                oT.append([np.nan])
                op.append(p)
                op.append([np.nan])
        if oT:
            self.outhigh = self.ax.plot(np.concatenate(oT), np.concatenate(op),
                                        '-', **outhigh_kw)
            self.canvas.draw()

    def invviewRightClicked(self, QPos):
        if self.invsel.hasSelection():
            idx = self.invsel.selectedIndexes()
            r = self.invmodel.data(idx[2])
            phases = r['phases']
            a, b = r['out']
            aset, bset = set([a]), set([b])
            aphases, bphases = phases.difference(aset), phases.difference(bset)
            show_menu = False
            menu = QtWidgets.QMenu(self)
            nr1 = dict(phases=phases, out=aset, output='User-defined')
            lbl1 = ' '.join(nr1['phases']) + ' - ' + ' '.join(nr1['out'])
            isnew, id = self.getiduni(nr1)
            if isnew:
                menu_item1 = menu.addAction(lbl1)
                menu_item1.triggered.connect(lambda: self.set_phaselist(nr1, show_output=False))
                show_menu = True
            nr2 = dict(phases=phases, out=bset, output='User-defined')
            lbl2 = ' '.join(nr2['phases']) + ' - ' + ' '.join(nr2['out'])
            isnew, id = self.getiduni(nr2)
            if isnew:
                menu_item2 = menu.addAction(lbl2)
                menu_item2.triggered.connect(lambda: self.set_phaselist(nr2, show_output=False))
                show_menu = True
            nr3 = dict(phases=bphases, out=aset, output='User-defined')
            lbl3 = ' '.join(nr3['phases']) + ' - ' + ' '.join(nr3['out'])
            isnew, id = self.getiduni(nr3)
            if isnew:
                menu_item3 = menu.addAction(lbl3)
                menu_item3.triggered.connect(lambda: self.set_phaselist(nr3, show_output=False))
                show_menu = True
            nr4 = dict(phases=aphases, out=bset, output='User-defined')
            lbl4 = ' '.join(nr4['phases']) + ' - ' + ' '.join(nr4['out'])
            isnew, id = self.getiduni(nr4)
            if isnew:
                menu_item4 = menu.addAction(lbl4)
                menu_item4.triggered.connect(lambda: self.set_phaselist(nr4, show_output=False))
                show_menu = True
            if show_menu:
                menu.exec(self.invview.mapToGlobal(QPos))

    def auto_inv_calc(self):
        if self.invsel.hasSelection():
            idx = self.invsel.selectedIndexes()
            r = self.invmodel.data(idx[2])
            phases = r['phases']
            a, b = r['out']
            aset, bset = set([a]), set([b])
            aphases, bphases = phases.difference(aset), phases.difference(bset)
            self.do_calc(True, phases=phases, out=aset)
            self.do_calc(True, phases=phases, out=bset)
            self.do_calc(True, phases=bphases, out=aset)
            self.do_calc(True, phases=aphases, out=bset)

    def zoom_to_uni(self, checked):
        if checked:
            if self.unisel.hasSelection():
                idx = self.unisel.selectedIndexes()
                row = self.unimodel.getRow(idx[0])
                T, p = self.get_trimmed_uni(row)
                dT = (T.max() - T.min()) / 5
                dp = (p.max() - p.min()) / 5
                self.ax.set_xlim([T.min() - dT, T.max() + dT])
                self.ax.set_ylim([p.min() - dp, p.max() + dp])
                self.canvas.draw()
        else:
            self.ax.set_xlim(self.trange)
            self.ax.set_ylim(self.prange)
            #clear navigation toolbar history
            self.toolbar.update()
            #self.plot()
            self.canvas.draw()

    def remove_inv(self):
        if self.invsel.hasSelection():
            idx = self.invsel.selectedIndexes()
            invnum = self.invmodel.data(idx[0])
            todel = True
            # Check ability to delete
            for row in self.unimodel.unilist:
                if row[2] == invnum or row[3] == invnum:
                    if row[4]['manual']:
                        todel = False
            if todel:
                msg = '{}\nAre you sure?'.format(self.invmodel.data(idx[1]))
                qb = QtWidgets.QMessageBox
                reply = qb.question(self, 'Remove invariant point',
                                    msg, qb.Yes, qb.No)
                if reply == qb.Yes:

                    # Check unilines begins and ends
                    for row in self.unimodel.unilist:
                        if row[2] == invnum:
                            row[2] = 0
                        if row[3] == invnum:
                            row[3] = 0
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

    def clicker(self, event):
        if event.inaxes is not None:
            phases, out = self.get_phases_out()
            r = dict(phases=phases, out=out, cmd='', variance=-1, manual=True)
            label = self.format_label(phases, out)
            isnew, id = self.getidinv(r)
            addinv = AddInv(label, parent=self)
            addinv.set_from_event(event)
            respond = addinv.exec()
            if respond == QtWidgets.QDialog.Accepted:
                T, p = addinv.getValues()
                r['T'], r['p'], r['output'] = np.array([T]), np.array([p]), 'User-defined invariant point.'
                if isnew:
                    self.invmodel.appendRow((id, label, r))
                else:
                    row = self.invmodel.getRowFromId(id)
                    row[2] = r
                    # retrim affected
                    for row in self.unimodel.unilist:
                        if row[2] == id or row[3] == id:
                            self.trimuni(row)
                self.invview.resizeColumnsToContents()
                self.plot()
                idx = self.invmodel.index(self.invmodel.lookup[id], 0, QtCore.QModelIndex())
                self.show_inv(idx)
                self.statusBar().showMessage('User-defined invariant point added.')
            self.pushManual.setChecked(False)

    def add_userdefined(self, checked=True):
        if self.ready:
            phases, out = self.get_phases_out()
            if len(out) == 1:
                if checked:
                    label = self.format_label(phases, out)
                    invs = []
                    for row in self.invmodel.invlist[1:]:
                        d = row[2]
                        if phases.issubset(d['phases']):
                            if out.issubset(d['out']):
                                invs.append(row[0])
                    if len(invs) > 1:
                        adduni = AddUni(label, invs, self)
                        respond = adduni.exec()
                        if respond == QtWidgets.QDialog.Accepted:
                            b, e = adduni.getValues()
                            if b != e:
                                r = dict(phases=phases, out=out, cmd='', variance=-1,
                                         p=np.array([]), T=np.array([]), manual=True,
                                         output='User-defined univariant line.')
                                isnew, id = self.getiduni(r)
                                if isnew:
                                    self.unimodel.appendRow((id, label, b, e, r))
                                else:
                                    row = self.unimodel.getRowFromId(id)
                                    row[2] = b
                                    row[3] = e
                                    row[4] = r
                                    if label:
                                        row[1] = label
                                row = self.unimodel.getRowFromId(id)
                                self.trimuni(row)
                                # if self.unihigh is not None:
                                #     self.clean_high()
                                #     self.unihigh.set_data(row[4]['fT'], row[4]['fp'])
                                self.adapt_uniview()
                                self.changed = True
                                self.plot()
                                idx = self.unimodel.index(self.unimodel.lookup[id], 0, QtCore.QModelIndex())
                                if isnew:
                                    self.uniview.selectRow(idx.row())
                                    self.uniview.scrollToBottom()
                                self.show_uni(idx)
                                self.statusBar().showMessage('User-defined univariant line added.')
                            else:
                                msg = 'Begin and end must be different.'
                                qb = QtWidgets.QMessageBox
                                qb.critical(self, 'Error!', msg, qb.Abort)
                        self.pushManual.setChecked(False)
                    else:
                        self.statusBar().showMessage('Not enough invariant points calculated for selected univariant line.')
            elif len(out) == 2:
                if checked:
                    # cancle zoom and pan action on toolbar
                    if self.toolbar._active == "PAN":
                        self.toolbar.pan()
                    elif self.toolbar._active == "ZOOM":
                        self.toolbar.zoom()
                    self.cid = self.canvas.mpl_connect('button_press_event', self.clicker)
                    self.tabMain.setCurrentIndex(0)
                    self.statusBar().showMessage('Click on canvas to add invariant point.')
                else:
                    self.canvas.mpl_disconnect(self.cid)
                    self.statusBar().showMessage('')
            else:
                self.statusBar().showMessage('Select exactly one out phase for univariant line or two phases for invariant point.')
                self.pushManual.setChecked(False)
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def read_scriptfile(self):
        if self.ready:
            with open(self.scriptfile, 'r', encoding=TCenc) as f:
                self.outScript.setPlainText(f.read())

    def save_scriptfile(self):
        if self.ready:
            with open(self.scriptfile, 'w', encoding=TCenc) as f:
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
                self.trange = (float(self.tminEdit.text()),
                               float(self.tmaxEdit.text()))
                self.prange = (float(self.pminEdit.text()),
                               float(self.pmaxEdit.text()))
                self.ax.set_xlim(self.trange)
                self.ax.set_ylim(self.prange)
                #clear navigation toolbar history
                self.toolbar.update()
                self.statusBar().showMessage('Settings applied.')
                self.changed = True
                self.figure.clear()
                self.plot()
            if (1 << 1) & bitopt:
                self.tminEdit.setText(fmt(self.ax.get_xlim()[0]))
                self.tmaxEdit.setText(fmt(self.ax.get_xlim()[1]))
                self.pminEdit.setText(fmt(self.ax.get_ylim()[0]))
                self.pmaxEdit.setText(fmt(self.ax.get_ylim()[1]))
            if (1 << 2) & bitopt:
                self.tminEdit.setText(fmt(self.trange[0]))
                self.tmaxEdit.setText(fmt(self.trange[1]))
                self.pminEdit.setText(fmt(self.prange[0]))
                self.pmaxEdit.setText(fmt(self.prange[1]))
            if (1 << 3) & bitopt:
                self.tminEdit.setText(fmt(self.deftrange[0]))
                self.tmaxEdit.setText(fmt(self.deftrange[1]))
                self.pminEdit.setText(fmt(self.defprange[0]))
                self.pmaxEdit.setText(fmt(self.defprange[1]))
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

    def format_label(self, phases, out):
        return (' '.join(sorted(list(phases.difference(self.excess)))) +
                ' - ' +
                ' '.join(sorted(list(out))))

    def do_calc(self, cT, phases={}, out={}):
        if self.ready:
            if phases == {} and out == {}:
                phases, out = self.get_phases_out()
            self.statusBar().showMessage('Running THERMOCALC...')
            ###########
            trange = self.ax.get_xlim()
            prange = self.ax.get_ylim()
            steps = self.spinSteps.value()
            #prec = self.spinPrec.value()
            prec = max(int(2 - np.floor(np.log10(min(np.diff(trange)[0], np.diff(prange)[0])))), 0)
            var = self.nc + 2 - len(phases) - len(self.excess)

            if len(out) == 1:
                if cT:
                    step = (prange[1] - prange[0]) / steps
                    tmpl = '{}\n\n{}\ny\n{:.{prec}f} {:.{prec}f}\n{:.{prec}f} {:.{prec}f}\n{:g}\nn\n\nkill\n\n'
                    ans = tmpl.format(' '.join(phases), ' '.join(out), *prange, *trange, step, prec=prec)
                else:
                    step = (trange[1] - trange[0]) / steps
                    tmpl = '{}\n\n{}\nn\n{:.{prec}f} {:.{prec}f}\n{:.{prec}f} {:.{prec}f}\n{:g}\nn\n\nkill\n\n'
                    ans = tmpl.format(' '.join(phases), ' '.join(out), *trange, *prange, step, prec=prec)
                tcout = self.runprog(self.tc, ans)
                status, variance, pts, res, output = parse_logfile(self.logfile)
                if status == 'bombed':
                    self.statusBar().showMessage('Bombed.')
                elif status == 'nir':
                    self.statusBar().showMessage('Nothing in range.')
                elif len(res) < 2:
                    self.statusBar().showMessage('Only one point calculated. Change range.')
                else:
                    r = dict(phases=phases, out=out, cmd=ans, variance=variance,
                             p=pts[0], T=pts[1], manual=False,
                             output=output, results=res)
                    label = self.format_label(phases, out)
                    isnew, id = self.getiduni(r)
                    if isnew:
                        self.unimodel.appendRow((id, label, 0, 0, r))
                        row = self.unimodel.getRowFromId(id)
                        self.trimuni(row)
                        self.adapt_uniview()
                        self.changed = True
                        self.plot()
                        #self.unisel.select(idx, QtCore.QItemSelectionModel.ClearAndSelect | QtCore.QItemSelectionModel.Rows)
                        idx = self.unimodel.index(self.unimodel.lookup[id], 0, QtCore.QModelIndex())
                        self.uniview.selectRow(idx.row())
                        self.uniview.scrollToBottom()
                        self.show_uni(idx)
                        self.statusBar().showMessage('New univariant line calculated.')
                    else:
                        if not self.checkOverwrite.isChecked():
                            row = self.unimodel.getRowFromId(id)
                            row[1] = label
                            row[4] = r
                            self.trimuni(row)
                            self.changed = True
                            self.adapt_uniview()
                            idx = self.unimodel.index(self.unimodel.lookup[id], 0, QtCore.QModelIndex())
                            self.unimodel.dataChanged.emit(idx, idx)
                            self.plot()
                            self.show_uni(idx)
                            self.statusBar().showMessage('Univariant line {} re-calculated.'.format(id))
                        else:
                            self.statusBar().showMessage('Univariant line already exists.')
            elif len(out) == 2:
                tmpl = '{}\n\n{}\n{:.{prec}f} {:.{prec}f} {:.{prec}f} {:.{prec}f}\nn\n\nkill\n\n'
                ans = tmpl.format(' '.join(phases), ' '.join(out), *trange, *prange, prec=prec)
                tcout = self.runprog(self.tc, ans)
                status, variance, pts, res, output = parse_logfile(self.logfile)
                if status == 'bombed':
                    self.statusBar().showMessage('Bombed.')
                elif status == 'nir':
                    self.statusBar().showMessage('Nothing in range.')
                else:
                    r = dict(phases=phases, out=out, cmd=ans, variance=variance,
                             p=pts[0], T=pts[1], manual=False,
                             output=output, results=res)
                    label = self.format_label(phases, out)
                    isnew, id = self.getidinv(r)
                    if isnew:
                        self.invmodel.appendRow((id, label, r))
                        self.invview.resizeColumnsToContents()
                        self.changed = True
                        self.plot()
                        idx = self.invmodel.index(self.invmodel.lookup[id], 0, QtCore.QModelIndex())
                        self.invview.selectRow(idx.row())
                        self.invview.scrollToBottom()
                        self.show_inv(idx)
                        self.statusBar().showMessage('New invariant point calculated.')
                    else:
                        if not self.checkOverwrite.isChecked():
                            row = self.invmodel.getRowFromId(id)
                            row[1] = label
                            row[2] = r
                            # retrim affected
                            for row in self.unimodel.unilist:
                                if row[2] == id or row[3] == id:
                                    self.trimuni(row)
                            self.changed = True
                            idx = self.invmodel.index(self.invmodel.lookup[id], 0, QtCore.QModelIndex())
                            self.show_inv(idx)
                            self.plot()
                            self.invmodel.dataChanged.emit(idx, idx)
                            self.statusBar().showMessage('Invariant point {} re-calculated.'.format(id))
                        else:
                            self.statusBar().showMessage('Invariant point already exists.')
            else:
                self.statusBar().showMessage('{} zero mode phases selected. Select one or two!'.format(len(out)))
            #########
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def gendrawpd(self):
        if self.ready:
            self.ax.set_xlim(self.trange)
            self.ax.set_ylim(self.prange)
            #clear navigation toolbar history
            self.toolbar.update()
            self.plot()
            with open(self.drawpdfile, 'w', encoding=TCenc) as output:
                output.write('% Generated by PyPSbuilder (c) Ondrej Lexa 2016\n')
                output.write('2    % no. of variables in each line of data, in this case P, T\n')
                ex = list(self.excess)
                ex.insert(0, '')
                output.write('{}'.format(self.nc - len(self.excess)) +
                             '    %% effective size of the system: ' +
                             self.axname + ' +'.join(ex) + '\n')
                output.write('2 1  %% which columns to be x,y in phase diagram\n')
                output.write('\n')
                output.write('% Points\n')
                for i in self.invmodel.invlist[1:]:
                    output.write('% ------------------------------\n')
                    output.write('i%s   %s\n' % (i[0], i[1]))
                    output.write('\n')
                    output.write('%s %s\n' % (i[2]['p'][0], i[2]['T'][0]))
                    output.write('\n')
                output.write('% Lines\n')
                for u in self.unimodel.unilist:
                    output.write('% ------------------------------\n')
                    output.write('u%s   %s\n' % (u[0], u[1]))
                    output.write('\n')
                    b1 = 'i%s' % u[2]
                    if b1 == 'i0':
                        b1 = 'begin'
                    b2 = 'i%s' % u[3]
                    if b2 == 'i0':
                        b2 = 'end'
                    if u[4]['manual']:
                        output.write(b1 + ' ' + b2 + ' connect\n')
                        output.write('\n')
                    else:
                        output.write(b1 + ' ' + b2 + '\n')
                        output.write('\n')
                        for p, t in zip(u[4]['p'], u[4]['T']):
                            output.write('%s %s\n' % (p, t))
                        output.write('\n')
                output.write('*\n')
                output.write('% ----------------------------------------------\n\n')
                if self.checkAreas.isChecked():
                    # phases in areas for TC-Investigator
                    with open(self.tcinvestigatorfile, 'w', encoding=TCenc) as tcinv:
                        vertices, edges, phases, tedges, tphases = construct_areas(self.unimodel.unilist,
                                                                                   self.invmodel.invlist[1:],
                                                                                   self.trange,
                                                                                   self.prange)
                        # write output
                        output.write('% Areas\n')
                        output.write('% ------------------------------\n')
                        maxpf = max([len(p) for p in phases]) + 1
                        for ed, ph, ve in zip(edges, phases, vertices):
                            v = np.array(ve)
                            if not (np.all(v[:, 0] < self.trange[0]) or
                                    np.all(v[:, 0] > self.trange[1]) or
                                    np.all(v[:, 1] < self.prange[0]) or
                                    np.all(v[:, 1] > self.prange[1])):
                                d = ('{:.2f} '.format(len(ph) / maxpf) +
                                     ' '.join(['u{}'.format(e) for e in ed]) +
                                     ' % ' + ' '.join(ph) + '\n')
                                output.write(d)
                                tcinv.write(' '.join(ph.union(self.excess)) + '\n')
                        if self.checkPartial.isChecked():
                            for ed, ph in zip(tedges, tphases):
                                d = ('{:.2f} '.format(len(ph) / maxpf) +
                                     ' '.join(['u{}'.format(e) for e in ed]) +
                                     ' %- ' + ' '.join(ph) + '\n')
                                output.write(d)
                                tcinv.write(' '.join(ph.union(self.excess)) + '\n')
                output.write('\n')
                output.write('*\n')
                output.write('\n')
                output.write('window {} {} '.format(*self.trange) +
                             '{} {}\n\n'.format(*self.prange))
                output.write('darkcolour  56 16 101\n\n')
                xt, yt = self.ax.get_xticks(), self.ax.get_yticks()
                xt = xt[xt > self.trange[0]]
                xt = xt[xt < self.trange[1]]
                yt = yt[yt > self.prange[0]]
                yt = yt[yt < self.prange[1]]
                output.write('bigticks ' +
                             '{} {} '.format(xt[1] - xt[0], xt[0]) +
                             '{} {}\n\n'.format(yt[1] - yt[0], yt[0]))
                output.write('smallticks {} '.format((xt[1] - xt[0]) / 10) +
                             '{}\n\n'.format((yt[1] - yt[0]) / 10))
                output.write('numbering yes\n\n')
                if self.checkAreas.isChecked():
                    output.write('doareas yes\n\n')
                output.write('*\n')
                self.statusBar().showMessage('Drawpd file generated successfully.')

            try:
                self.runprog(self.dr, self.bname + '\n')
                self.statusBar().showMessage('Drawpd sucessfully executed.')
            except OSError as err:
                qb = QtWidgets.QMessageBox
                qb.critical(self, 'Drawpd error!', str(err), qb.Abort)

    def getiduni(self, zm=None):
        '''Return id of either new or existing univariant line'''
        ids = 0
        for r in self.unimodel.unilist:
            if zm is not None:
                if r[4]['phases'] == zm['phases']:
                    if r[4]['out'] == zm['out']:
                        return False, r[0]
            ids = max(ids, r[0])
        return True, ids + 1

    def getidinv(self, zm=None):
        '''Return id of either new or existing invvariant point'''
        ids = 0
        for r in self.invmodel.invlist[1:]:
            if zm is not None:
                if r[2]['phases'] == zm['phases']:
                    if r[2]['out'] == zm['out']:
                        return False, r[0]
            ids = max(ids, r[0])
        return True, ids + 1

    def trimuni(self, row):
        if not row[4]['manual']:
            xy = np.array([row[4]['T'], row[4]['p']]).T
            line = LineString(xy)
            if row[2] > 0:
                dt = self.invmodel.getDataFromId(row[2])
                p1 = Point(dt['T'][0], dt['p'][0])
            else:
                p1 = Point(row[4]['T'][0], row[4]['p'][0])
            if row[3] > 0:
                dt = self.invmodel.getDataFromId(row[3])
                p2 = Point(dt['T'][0], dt['p'][0])
            else:
                p2 = Point(row[4]['T'][-1], row[4]['p'][-1])
            # vertex distances
            vdst = np.array([line.project(Point(*v)) for v in xy])
            d1 = line.project(p1)
            d2 = line.project(p2)
            if d1 > d2:
                d1, d2 = d2, d1
                row[2], row[3] = row[3], row[2]
            # get indexex of points to keep
            row[4]['begix'] = np.flatnonzero(vdst >= d1)[0]
            row[4]['endix'] = np.flatnonzero(vdst <= d2)[-1]

    def get_trimmed_uni(self, row):
        if row[2] > 0:
            dt = self.invmodel.getDataFromId(row[2])
            T1, p1 = dt['T'][0], dt['p'][0]
        else:
            T1, p1 = [], []
        if row[3] > 0:
            dt = self.invmodel.getDataFromId(row[3])
            T2, p2 = dt['T'][0], dt['p'][0]
        else:
            T2, p2 = [], []
        if not row[4]['manual']:
            T = row[4]['T'][row[4]['begix']:row[4]['endix'] + 1]
            p = row[4]['p'][row[4]['begix']:row[4]['endix'] + 1]
        else:
            T, p = [], []
        return np.hstack((T1, T, T2)), np.hstack((p1, p, p2))

    def getunilabelpoint(self, T, p):
        if len(T) > 1:
            dT = np.diff(T)
            dp = np.diff(p)
            d = np.sqrt(dT**2 + dp**2)
            if np.sum(d) > 0:
                cl = np.append([0], np.cumsum(d))
                ix = np.interp(np.sum(d) / 2, cl, range(len(cl)))
                cix = int(ix)
                return T[cix] + (ix - cix) * dT[cix], p[cix] + (ix - cix) * dp[cix]
            else:
                return T[0], p[0]
        else:
            return T[0], p[0]

    def plot(self):
        if self.ready:
            lalfa = self.spinAlpha.value() / 100
            unilabel_kw = dict(ha='center', va='center', size='small',
                               bbox=dict(facecolor='cyan', alpha=lalfa, pad=4))
            invlabel_kw = dict(ha='center', va='center', size='small',
                               bbox=dict(facecolor='yellow', alpha=lalfa, pad=4))
            if self.figure.axes == []:
                cur = None
            else:
                cur = (self.ax.get_xlim(), self.ax.get_ylim())
            self.ax = self.figure.add_subplot(111)
            self.ax.cla()
            self.ax.format_coord = self.format_coord
            for k in self.unimodel.unilist:
                T, p = self.get_trimmed_uni(k)
                self.ax.plot(T, p, 'k')
                if self.checkLabelUni.isChecked():
                    Tl, pl = self.getunilabelpoint(T, p)
                    if self.checkLabels.isChecked():
                        self.ax.text(Tl, pl, k[1], **unilabel_kw)
                    else:
                        self.ax.text(Tl, pl, str(k[0]), **unilabel_kw)
            for k in self.invmodel.invlist[1:]:
                T, p = k[2]['T'][0], k[2]['p'][0]
                self.ax.plot(T, p, 'k.')
                if self.checkLabelInv.isChecked():
                    if self.checkLabels.isChecked():
                        self.ax.text(T, p, k[1], **invlabel_kw)
                    else:
                        self.ax.text(T, p, str(k[0]), **invlabel_kw)
            self.ax.set_xlabel('Temperature [C]')
            self.ax.set_ylabel('Pressure [kbar]')
            ex = list(self.excess)
            ex.insert(0, '')
            self.ax.set_title(self.axname + ' +'.join(ex))
            if cur is None:
                self.ax.set_xlim(self.trange)
                self.ax.set_ylim(self.prange)
            else:
                self.ax.set_xlim(cur[0])
                self.ax.set_ylim(cur[1])
            if self.unihigh is not None and self.unisel.hasSelection():
                idx = self.unisel.selectedIndexes()
                row = self.unimodel.getRow(idx[0])
                T, p = self.get_trimmed_uni(row)
                self.unihigh = self.ax.plot(T, p, '-', **unihigh_kw)
            if self.invhigh is not None and self.invsel.hasSelection():
                idx = self.invsel.selectedIndexes()
                dt = self.invmodel.getData(idx[0], 'Data')
                self.invhigh = self.ax.plot(dt['T'], dt['p'], 'o', **invhigh_kw)
            self.canvas.draw()


class InvModel(QtCore.QAbstractTableModel):
    def __init__(self, parent, *args):
        super(InvModel, self).__init__(parent, *args)
        self.invlist = []
        self.header = ['ID', 'Label', 'Data']
        self.lookup = {}

    def rowCount(self, parent=None):
        return len(self.invlist)

    def columnCount(self, parent=None):
        return len(self.header)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        elif role == QtCore.Qt.ForegroundRole:
            if self.invlist[index.row()][self.header.index('Data')]['manual']:
                brush = QtGui.QBrush()
                brush.setColor(QtGui.QColor('red'))
                return brush
        elif role != QtCore.Qt.DisplayRole:
            return None
        else:
            return self.invlist[index.row()][index.column()]

    def appendRow(self, datarow):
        """ Append model row. """
        self.beginInsertRows(QtCore.QModelIndex(),
                             len(self.invlist), len(self.invlist))
        self.invlist.append(list(datarow))
        self.endInsertRows()
        self.lookup[datarow[0]] = self.rowCount() - 1

    def removeRow(self, index):
        """ Remove model row. """
        self.beginRemoveRows(QtCore.QModelIndex(), index.row(), index.row())
        del self.invlist[index.row()]
        self.endRemoveRows()
        self.lookup = {dt[0]: ix + 1 for ix, dt in enumerate(self.invlist[1:])}

    def headerData(self, col, orientation, role=QtCore.Qt.DisplayRole):
        if orientation == QtCore.Qt.Horizontal & role == QtCore.Qt.DisplayRole:
            return self.header[col]
        return None

    def getData(self, index, what='Data'):
        return self.invlist[index.row()][self.header.index(what)]

    def getRow(self, index):
        return self.invlist[index.row()]

    def getDataFromId(self, id, what='Data'):
        # print(id, self.rowCount(), what, self.lookup)
        return self.invlist[self.lookup[id]][self.header.index(what)]

    def getRowFromId(self, id):
        return self.invlist[self.lookup[id]]


class UniModel(QtCore.QAbstractTableModel):
    def __init__(self, parent, *args):
        super(UniModel, self).__init__(parent, *args)
        self.unilist = []
        self.header = ['ID', 'Label', 'Begin', 'End', 'Data']
        self.lookup = {}

    def rowCount(self, parent=None):
        return len(self.unilist)

    def columnCount(self, parent=None):
        return len(self.header)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        elif role == QtCore.Qt.ForegroundRole:
            if self.unilist[index.row()][self.header.index('Data')]['manual']:
                brush = QtGui.QBrush()
                brush.setColor(QtGui.QColor('red'))
                return brush
        elif role != QtCore.Qt.DisplayRole:
            return None
        else:
            return self.unilist[index.row()][index.column()]

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        # DO change and emit plot
        if role == QtCore.Qt.EditRole:
            self.unilist[index.row()][index.column()] = value
            self.dataChanged.emit(index, index)
        return False

    def appendRow(self, datarow):
        """ Append model row. """
        self.beginInsertRows(QtCore.QModelIndex(),
                             len(self.unilist), len(self.unilist))
        self.unilist.append(list(datarow))
        self.endInsertRows()
        self.lookup[datarow[0]] = self.rowCount() - 1

    def removeRow(self, index):
        """ Remove model row. """
        self.beginRemoveRows(QtCore.QModelIndex(), index.row(), index.row())
        del self.unilist[index.row()]
        self.endRemoveRows()
        self.lookup = {dt[0]: ix for ix, dt in enumerate(self.unilist)}

    def headerData(self, col, orientation, role=QtCore.Qt.DisplayRole):
        if orientation == QtCore.Qt.Horizontal & role == QtCore.Qt.DisplayRole:
            return self.header[col]
        return None

    def flags(self, index):
        if index.column() > 1:
            return QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        else:
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def getData(self, index, what='Data'):
        return self.unilist[index.row()][self.header.index(what)]

    def getRow(self, index):
        return self.unilist[index.row()]

    def getDataFromId(self, id, what='Data'):
        return self.unilist[self.lookup[id]][self.header.index(what)]

    def getRowFromId(self, id):
        return self.unilist[self.lookup[id]]


class ComboDelegate(QtWidgets.QItemDelegate):
    """
    A delegate that places a fully functioning QtWidgets.QComboBox in every
    cell of the column to which it's applied
    """
    def __init__(self, parent, invmodel):
        super(ComboDelegate, self).__init__(parent)
        self.invmodel = invmodel

    def createEditor(self, parent, option, index):
        r = index.model().getData(index, 'Data')
        phases, out = r['phases'], r['out']
        combomodel = QtGui.QStandardItemModel()
        if not r['manual']:
            item = QtGui.QStandardItem('0')
            item.setData(0, 1)
            combomodel.appendRow(item)
        # filter possible candidates
        for row in self.invmodel.invlist[1:]:
            d = row[2]
            if phases.issubset(d['phases']): # if out.issubset(d['out']):
                item = QtGui.QStandardItem(str(row[0]))
                item.setData(row[0], 1)
                combomodel.appendRow(item)
        combo = QtWidgets.QComboBox(parent)
        combo.setModel(combomodel)
        return combo

    def setEditorData(self, editor, index):
        editor.setCurrentText(str(index.model().data(index)))

    def setModelData(self, editor, model, index):
        if index.column() == 2:
            other = model.getData(index, 'End')
        else:
            other = model.getData(index, 'Begin')
        new = editor.currentData(1)
        if other == new and new != 0:
            editor.setCurrentText(str(model.data(index)))
            self.parent().statusBar().showMessage('Begin and end must be different.')
        else:
            model.setData(index, new)


class AddInv(QtWidgets.QDialog, Ui_AddInv):
    """Add inv dialog class
    """
    def __init__(self, label, parent=None):
        super(AddInv, self).__init__(parent)
        self.setupUi(self)
        self.labelEdit.setText(label)
        # validator
        validator = QtGui.QDoubleValidator()
        validator.setLocale(QtCore.QLocale.c())
        self.tEdit.setValidator(validator)
        self.tEdit.textChanged.connect(self.check_validity)
        self.tEdit.textChanged.emit(self.tEdit.text())
        self.pEdit.setValidator(validator)
        self.pEdit.textChanged.connect(self.check_validity)
        self.pEdit.textChanged.emit(self.pEdit.text())

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
        self.tEdit.setText(str(event.xdata))
        self.pEdit.setText(str(event.ydata))

    def getValues(self):
        T = float(self.tEdit.text())
        p = float(self.pEdit.text())
        return T, p


class AddUni(QtWidgets.QDialog, Ui_AddUni):
    """Add uni dialog class
    """
    def __init__(self, label, items, parent=None):
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
    def __init__(self, version, parent=None):
        """Display a dialog that shows application information."""
        super(AboutDialog, self).__init__(parent)

        self.setWindowTitle('About')
        self.resize(300, 100)

        about = QtWidgets.QLabel('PSbuilder {}\nTHERMOCALC front-end for constructing PT pseudosections'.format(version))
        about.setAlignment(QtCore.Qt.AlignCenter)

        author = QtWidgets.QLabel('Ondrej Lexa')
        author.setAlignment(QtCore.Qt.AlignCenter)

        github = QtWidgets.QLabel('GitHub: ondrolexa')
        github.setAlignment(QtCore.Qt.AlignCenter)

        self.layout = QtWidgets.QVBoxLayout()
        self.layout.setAlignment(QtCore.Qt.AlignVCenter)

        self.layout.addWidget(about)
        self.layout.addWidget(author)
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

class ProjectFile(object):
    def __init__(self, projfile):
        if os.path.exists(projfile):
            stream = gzip.open(projfile, 'rb')
            self.data = pickle.load(stream)
            stream.close()
            self.workdir = os.path.dirname(projfile)
            self.name = os.path.splitext(os.path.basename(projfile))[0]
            self.unilookup = {}
            self.invlookup = {}
            for ix, r in enumerate(self.unilist):
                self.unilookup[r[0]] = ix
            for ix, r in enumerate(self.invlist):
                self.invlookup[r[0]] = ix
        else:
            raise Exception('File {} does not exists.'.format(projfile))

    @property
    def selphases(self):
        return self.data['selphases']

    @property
    def out(self):
        return self.data['out']

    @property
    def trange(self):
        return self.data['trange']

    @property
    def prange(self):
        return self.data['prange']

    @property
    def unilist(self):
        return self.data['unilist']

    @property
    def invlist(self):
        return self.data['invlist']

    @property
    def tcexe(self):
        if 'tcexe' in self.data:
            return self.data['tcexe']
        else:
            print('Old format. No tcexe.')

    @property
    def drexe(self):
        if 'drexe' in self.data:
            return self.data['drexe']
        else:
            print('Old format. No drexe.')

    @property
    def version(self):
        if 'version' in self.data:
            return self.data['version']
        else:
            print('Old format. No version.')

    def unidata(self, fid):
        uni = self.unilist[self.unilookup[fid]]
        dt = uni[4]
        dt['begin'] = uni[2]
        dt['end'] = uni[3]
        return dt

    def invdata(self, fid):
        return self.invlist[self.invlookup[fid]][2]

    def get_trimmed_uni(self, fid):
        uni = self.unilist[self.unilookup[fid]]
        if uni[2] > 0:
            dt = self.invdata(uni[2])
            T1, p1 = dt['T'][0], dt['p'][0]
        else:
            T1, p1 = [], []
        if uni[3] > 0:
            dt = self.invdata(uni[3])
            T2, p2 = dt['T'][0], dt['p'][0]
        else:
            T2, p2 = [], []
        if not uni[4]['manual']:
            T = uni[4]['T'][uni[4]['begix']:uni[4]['endix'] + 1]
            p = uni[4]['p'][uni[4]['begix']:uni[4]['endix'] + 1]
        else:
            T, p = [], []
        return np.hstack((T1, T, T2)), np.hstack((p1, p, p2))

class PTPS:
    def __init__(self, projfile):
        self.prj = ProjectFile(projfile)
        # Check prefs and scriptfile
        if not os.path.exists(self.prefsfile):
            raise Exception('No tc-prefs.txt file in working directory.')
        for line in open(self.prefsfile, 'r'):
            kw = line.split()
            if kw != []:
                if kw[0] == 'scriptfile':
                    self.bname = kw[1]
                    if not os.path.exists(self.scriptfile):
                        raise Exception('tc-prefs: scriptfile tc-' + self.bname + '.txt does not exists in your working directory.')
                if kw[0] == 'calcmode':
                    if kw[1] != '1':
                        raise Exception('tc-prefs: calcmode must be 1.')
        if not hasattr(self, 'bname'):
            raise Exception('No scriptfile defined in tc-prefs.txt')
        if os.path.exists(self.project):
            self.load()
            print('Compositions loaded.')
        else:
            self.shapes = OrderedDict()
            self.edges = OrderedDict()
            self.variance = OrderedDict()
            # traverse pseudosecton
            (vertices, edges, phases,
             tedges, tphases) = construct_areas(self.prj.unilist,
                                                self.prj.invlist,
                                                self.prj.trange,
                                                self.prj.prange)
            # default p-t range boundary
            bnd = [LineString([(self.prj.trange[0], self.prj.prange[0]),
                              (self.prj.trange[1], self.prj.prange[0])]),
                   LineString([(self.prj.trange[1], self.prj.prange[0]),
                              (self.prj.trange[1], self.prj.prange[1])]),
                   LineString([(self.prj.trange[1], self.prj.prange[1]),
                              (self.prj.trange[0], self.prj.prange[1])]),
                   LineString([(self.prj.trange[0], self.prj.prange[1]),
                              (self.prj.trange[0], self.prj.prange[0])])]
            bnda = list(polygonize(bnd))[0]
            # Create all full areas
            tq = trange(len(edges), desc='Full areas')
            for ind in tq:
                e, f = edges[ind], phases[ind]
                lns = [LineString(np.c_[self.prj.get_trimmed_uni(fid)]) for fid in e]
                pp = polygonize(lns)
                invalid = True
                for ppp in pp:
                    ppok = bnda.intersection(ppp)
                    if ppok.geom_type == 'Polygon':
                        invalid = False
                        self.edges[f] = e
                        self.variance[f] = self.parse_variance(self.runtc('{}\nkill\n\n'.format(' '.join(f))))
                        if f in self.shapes:
                            self.shapes[f] = self.shapes[f].union(ppok)
                        else:
                            self.shapes[f] = ppok
                if invalid:
                    tq.write('Lines {} have invalid geometry.'.format(e))
            # Create all partial areas
            tq = trange(len(tedges), desc='Partial areas')
            for ind in tq:
                e, f = tedges[ind], tphases[ind]
                lns = [LineString(np.c_[self.prj.get_trimmed_uni(fid)]) for fid in e]
                pp = linemerge(lns)
                invalid = True
                if pp.geom_type == 'LineString':
                    bndu = unary_union([s for s in bnd if pp.crosses(s)])
                    if not bndu.is_empty:
                        pps = pp.difference(bndu)
                        bnds = bndu.difference(pp)
                        pp = polygonize(pps.union(bnds))
                        for ppp in pp:
                            ppok = bnda.intersection(ppp)
                            if ppok.geom_type == 'Polygon':
                                invalid = False
                                self.edges[f] = e
                                self.variance[f] = self.parse_variance(self.runtc('{}\nkill\n\n'.format(' '.join(f))))
                                if f in self.shapes:
                                    self.shapes[f] = self.shapes[f].union(ppok)
                                else:
                                    self.shapes[f] = ppok
                if invalid:
                    tq.write('Lines {} does not form valid polygon for default p-T range.'.format(e))
            # Fix possible overlaps of partial areas
            for k1, k2 in itertools.combinations(self.shapes, 2):
                if self.shapes[k1].within(self.shapes[k2]):
                    self.shapes[k2] = self.shapes[k2].difference(self.shapes[k1])
                if self.shapes[k2].within(self.shapes[k1]):
                    self.shapes[k1] = self.shapes[k1].difference(self.shapes[k2])
            print('{} compositions not yet calculated. Run calculate_composition() method.'.format(self.prj.name))

    def __iter__(self):
        return iter(self.shapes)

    @property
    def phases(self):
        return {phase for key in self for phase in key}

    @property
    def keys(self):
        return list(self.shapes.keys())

    @property
    def tstep(self):
        return self.tspace[1] - self.tspace[0]

    @property
    def pstep(self):
        return self.pspace[1] - self.pspace[0]

    @property
    def scriptfile(self):
        return os.path.join(self.prj.workdir, 'tc-' + self.bname + '.txt')

    @property
    def logfile(self):
        return os.path.join(self.prj.workdir, 'tc-log.txt')

    @property
    def prefsfile(self):
        return os.path.join(self.prj.workdir, 'tc-prefs.txt')

    @property
    def tcexe(self):
        return os.path.join(self.prj.workdir, self.prj.tcexe)

    @property
    def project(self):
        return os.path.join(self.prj.workdir, self.prj.name + '.psi')

    def unidata(self, fid):
        return self.prj.unidata(fid)

    def invdata(self, fid):
        return self.prj.invdata(fid)

    def save(self):
        # put to dict
        data = {'shapes': self.shapes,
                'edges': self.edges,
                'variance': self.variance,
                'tspace': self.tspace,
                'pspace': self.pspace,
                'tg': self.tg,
                'pg': self.pg,
                'gridcalcs': self.gridcalcs,
                'masks': self.masks,
                'status': self.status,
                'delta': self.delta}
        # do save
        stream = gzip.open(self.project, 'wb')
        pickle.dump(data, stream)
        stream.close()

    def load(self):
        stream = gzip.open(self.project, 'rb')
        data = pickle.load(stream)
        stream.close()
        self.shapes  = data['shapes']
        self.edges  = data['edges']
        self.variance = data['variance']
        self.tspace = data['tspace']
        self.pspace = data['pspace']
        self.tg = data['tg']
        self.pg = data['pg']
        self.gridcalcs = data['gridcalcs']
        self.masks = data['masks']
        self.status = data['status']
        self.delta = data['delta']

#    def calculate_composition_old(self, T_N=51, p_N=51):
#        self.T_N, self.p_N = T_N, p_N
#        # Calc by areas
#        tspace = np.linspace(self.prj.trange[0], self.prj.trange[1], self.T_N)
#        tstep = tspace[1] - tspace[0]
#        pspace = np.linspace(self.prj.prange[0], self.prj.prange[1], self.p_N)
#        pstep = pspace[1] - pspace[0]
#        total, done = len(self.keys), 0
#        for key in self:
#            tmin, pmin, tmax, pmax = self.shapes[key].bounds
#            trange = tspace[np.logical_and(tspace >= tmin, tspace <= tmax)]
#            prange = pspace[np.logical_and(pspace >= pmin, pspace <= pmax)]
#            done += 1
#            print('{} of {} - {} Calculating...'.format(done, total, ' '.join(key)))
#            if trange.size > 0 and prange.size > 0:
#                ans = '{}\n\n\n{} {}\n{} {}\n{}\n{}\nkill\n\n'.format(' '.join(key), prange.min(), prange.max(), trange.min(), trange.max(), tstep, pstep)
#                out = self.runtc(ans)
#                self.calcs[key] = dict(output=out, input=ans)
#            else:
#                rp = self.shapes[key].representative_point()
#                t, p = rp.x, rp.y
#                ans = '{}\n\n\n{}\n{}\nkill\n\n'.format(' '.join(key), p, t)
#                out = self.runtc(ans)
#                self.calcs[key] = dict(output=out, input=ans)
#            if not self.data_keys(key):
#                print('Nothing in range for {}'.format(' '.join(key)))
#        self.show_success()

    def calculate_composition(self, numT=51, numP=51):
        self.tspace = np.linspace(self.prj.trange[0], self.prj.trange[1], numT)
        self.pspace = np.linspace(self.prj.prange[0], self.prj.prange[1], numP)
        self.tg, self.pg = np.meshgrid(self.tspace, self.pspace)
        self.gridcalcs = np.empty(self.tg.shape, np.dtype(object))
        self.status = np.empty(self.tg.shape)
        self.status[:] = np.nan
        self.delta = np.empty(self.tg.shape)
        self.delta[:] = np.nan
        for (r, c) in tqdm(np.ndindex(self.tg.shape), desc='Gridding', total=np.prod(self.tg.shape)):
            t, p = self.tg[r, c], self.pg[r, c]
            k = self.identify(t, p)
            if k is not None:
                self.status[r, c] = 0
                ans = '{}\n\n\n{}\n{}\nkill\n\n'.format(' '.join(k), p, t)
                start_time = time.time()
                out = self.runtc(ans)
                delta = time.time() - start_time
                status, variance, pts, res, output = parse_logfile(self.logfile)
                if len(res) == 1:
                    self.gridcalcs[r, c] = res[0]
                    self.status[r, c] = 1
                    self.delta[r, c] = delta
                # search already done inv neighs
                if self.status[r, c] == 0:
                    edges = self.edges[k]
                    for inv in {self.unidata(ed)['begin'] for ed in edges}.union({self.unidata(ed)['end'] for ed in edges}).difference({0}):
                        if not self.invdata(inv)['manual']:
                            update_guesses(self.scriptfile, self.invdata(inv)['results'][0]['ptguess'])
                            start_time = time.time()
                            out = self.runtc(ans)
                            delta = time.time() - start_time
                            status, variance, pts, res, output = parse_logfile(self.logfile)
                            if len(res) == 1:
                                self.gridcalcs[r, c] = res[0]
                                self.status[r, c] = 1
                                self.delta[r, c] = delta
                                break
                if self.status[r, c] == 0:
                    for rn, cn in self.neighs(r, c):
                        if self.status[rn, cn] == 1:
                            update_guesses(self.scriptfile, self.gridcalcs[rn, cn]['ptguess'])
                            start_time = time.time()
                            out = self.runtc(ans)
                            delta = time.time() - start_time
                            status, variance, pts, res, output = parse_logfile(self.logfile)
                            if len(res) == 1:
                                self.gridcalcs[r, c] = res[0]
                                self.status[r, c] = 1
                                self.delta[r, c] = delta
                                break
                    if self.status[r, c] == 0:
                        self.gridcalcs[r, c] = None
            else:
                self.gridcalcs[r, c] = None
        print('Grid search done. {} empty grid points left.'.format(len(np.flatnonzero(self.status == 0))))
        self.fix_solutions()
        # Create data masks
        points = MultiPoint(list(zip(self.tg.flatten(), self.pg.flatten())))
        self.masks = OrderedDict()
        for key in tqdm(self, desc='Masking', total=len(self.shapes)):
            self.masks[key] = np.array(list(map(self.shapes[key].contains, points))).reshape(self.tg.shape)
        self.save()

    def fix_solutions(self):
        ri, ci = np.nonzero(self.status == 0)
        fixed, ftot = 0, len(ri)
        tq = trange(ftot, desc='Fix ({}/{})'.format(fixed, ftot))
        for ind in tq:
            r, c = ri[ind], ci[ind]
            t, p = self.tg[r, c], self.pg[r, c]
            k = self.identify(t, p)
            ans = '{}\n\n\n{}\n{}\nkill\n\n'.format(' '.join(k), p, t)
            # search already done grid neighs
            for rn, cn in self.neighs(r, c):
                if self.status[rn, cn] == 1:
                    start_time = time.time()
                    out = self.runtc(ans)
                    delta = time.time() - start_time
                    status, variance, pts, res, output = parse_logfile(self.logfile)
                    if len(res) == 1:
                        self.gridcalcs[r, c] = res[0]
                        self.status[r, c] = 1
                        self.delta[r, c] = delta
                        fixed += 1
                        tq.set_description(desc='Fix ({}/{})'.format(fixed, ftot))
                        break
                    else:
                        update_guesses(self.scriptfile, self.gridcalcs[rn, cn]['ptguess'])
                    start_time = time.time()
                    out = self.runtc(ans)
                    delta = time.time() - start_time
                    status, variance, pts, res, output = parse_logfile(self.logfile)
                    if len(res) == 1:
                        self.gridcalcs[r, c] = res[0]
                        self.status[r, c] = 1
                        self.delta[r, c] = delta
                        fixed += 1
                        tq.set_description(desc='Fix ({}/{})'.format(fixed, ftot))
                        break
            # search already done inv neighs
            if self.status[r, c] == 0:
                edges = self.edges[k]
                for inv in {self.unidata(ed)['begin'] for ed in edges}.union({self.unidata(ed)['end'] for ed in edges}).difference({0}):
                    if not self.invdata(inv)['manual']:
                        update_guesses(self.scriptfile, self.invdata(inv)['results'][0]['ptguess'])
                        start_time = time.time()
                        out = self.runtc(ans)
                        delta = time.time() - start_time
                        status, variance, pts, res, output = parse_logfile(self.logfile)
                        if len(res) == 1:
                            self.gridcalcs[r, c] = res[0]
                            self.status[r, c] = 1
                            self.delta[r, c] = delta
                            fixed += 1
                            tq.set_description(desc='Fix ({}/{})'.format(fixed, ftot))
                            break
            if self.status[r, c] == 0:
                tqdm.write('No solution find for {}, {}'.format(t, p))
        print('Fix done. {} empty grid points left.'.format(len(np.flatnonzero(self.status == 0))))

    def neighs(self, r, c):
        m = np.array([[(r-1,c-1), (r-1,c), (r-1,c+1)],
                      [(r,c-1), (None,None), (r,c+1)],
                      [(r+1,c-1), (r+1,c), (r+1,c+1)]])
        if r < 1:
            m = m[1:, :]
        if r > len(self.pspace) - 2:
            m = m[:-1, :]
        if c < 1:
            m = m[:, 1:]
        if c > len(self.tspace) - 2:
            m = m[:, :-1]
        return zip([i for i in m[:,:,0].flat if i is not None],
                   [i for i in m[:,:,1].flat if i is not None])

    def runtc(self, instr):
        if sys.platform.startswith('win'):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags = 1
            startupinfo.wShowWindow = 0
        else:
            startupinfo = None
        p = subprocess.Popen(self.tcexe, cwd=self.prj.workdir, startupinfo=startupinfo, **popen_kw)
        output = p.communicate(input=instr.encode(TCenc))[0].decode(TCenc)
        sys.stdout.flush()
        return output

    def parse_variance(self, out):
        for ln in out.splitlines():
            if 'variance of required equilibrium' in ln:
                break
        return int(ln[ln.index('(') + 1:ln.index('?')])

    def data_keys(self, key):
        data = dict()
        if key in self.masks:
            res = self.calcs(key)
            if res:
                dt = res[0]['data']
                ph = sorted(list(dt.keys()))
                set(self.calcs(key)[0]['data']['q'].keys()).difference({'mode','rbi'})
        return sorted(list(data.keys()))

    @property
    def all_data_keys(self):
        keys = set()
        for key in self.masks:
            res = self.calcs(key)
            if res:
                p, T, data = res[0]
                keys.update(data.keys())
        return sorted(list(keys))

    def collect_inv_data(self, key, phase, comp, ox=None):
        dt = dict(pts=[], data=[])
        edges = self.edges[key]
        for i in {self.unidata(ed)['begin'] for ed in edges}.union({self.unidata(ed)['end'] for ed in edges}).difference({0}):
            T = self.invdata(i)['T'][0]
            p = self.invdata(i)['p'][0]
            res = self.invdata(i)['results'][0]
            if comp == 'rbi':
                v = res['data'][phase][comp][ox]
                dt['pts'].append((T, p))
                dt['data'].append(v)
            else:
                v = res['data'][phase][comp]
                dt['pts'].append((T, p))
                dt['data'].append(v)
        return dt

    def collect_edges_data(self, key, phase, comp, ox=None):
        dt = dict(pts=[], data=[])
        for e in self.edges[key]:
            if not self.unidata(e)['manual']:
                bix, eix = self.unidata(e)['begix'], self.unidata(e)['endix']
                edt = zip(self.unidata(e)['T'][bix:eix + 1],
                          self.unidata(e)['p'][bix:eix + 1],
                          self.unidata(e)['results'][bix:eix + 1])
                for T, p, res in edt:
                    if comp == 'rbi':
                        v = res['data'][phase][comp][ox]
                        dt['pts'].append((T, p))
                        dt['data'].append(v)
                    else:
                        v = res['data'][phase][comp]
                        dt['pts'].append((T, p))
                        dt['data'].append(v)
        return dt

    def collect_grid_data(self, key, phase, comp, ox=None):
        dt = dict(pts=[], data=[])
        gdt = zip(self.tg[self.masks[key]],
                  self.pg[self.masks[key]],
                  self.gridcalcs[self.masks[key]],
                  self.status[self.masks[key]])
        for T, p, res, s in gdt:
            if s:
                if comp == 'rbi':
                    v = res['data'][phase][comp][ox]
                    dt['pts'].append((T, p))
                    dt['data'].append(v)
                else:
                    v = res['data'][phase][comp]
                    dt['pts'].append((T, p))
                    dt['data'].append(v)
        return dt

    def collect_all_data(self, key, phase, comp, ox=None):
        d = self.collect_inv_data(key, phase, comp, ox=ox)
        de = self.collect_edges_data(key, phase, comp, ox=ox)
        dg = self.collect_grid_data(key, phase, comp, ox=ox)
        d['pts'].extend(de['pts'])
        d['pts'].extend(dg['pts'])
        d['data'].extend(de['data'])
        d['data'].extend(dg['data'])
        return d

    def merge_data(self, phase, comp, ox=None, which='all'):
        mn, mx = sys.float_info.max, sys.float_info.min
        recs = OrderedDict()
        for key in self:
            if phase in key:
                if which == 'inv':
                    d = self.collect_inv_data(key, phase, comp, ox=ox)
                elif which == 'edges':
                    d = self.collect_edges_data(key, phase, comp, ox=ox)
                elif which == 'area':
                    d = self.collect_grid_data(key, phase, comp, ox=ox)
                else:
                    d = self.collect_all_data(key, phase, comp, ox=ox)
                z = d['data']
                if z:
                    recs[key] = d
                    mn = min(mn, min(z))
                    mx = max(mx, max(z))
        return recs, mn, mx

    def show(self, out=[], cmap='viridis', alpha=1, label=False):
        def split_key(key):
            tl = list(key)
            l = len(tl)
            wp = l // 4 + int(l%4 > 1)
            return '\n'.join([' '.join(s) for s in [tl[i*l // wp: (i+1)*l // wp] for i in range(wp)]])
        if isinstance(out, str):
            out = [out]
        vv = np.unique([self.variance[k] for k in self])
        pscolors = plt.get_cmap(cmap)(np.linspace(0, 1, vv.size))
        # Set alpha
        pscolors[:,-1] = alpha
        pscmap = ListedColormap(pscolors)
        norm = BoundaryNorm(np.arange(min(vv) - 0.5, max(vv) + 1), vv.size)
        fig, ax = plt.subplots()
        lbls = []
        exc = frozenset.intersection(*self.keys)
        for k in self:
            lbls.append((split_key(k.difference(exc)), self.shapes[k].representative_point().coords[0]))
            ax.add_patch(PolygonPatch(self.shapes[k], fc=pscmap(norm(self.variance[k])), ec='none'))
        ax.autoscale_view()
        self.overlay(ax)
        if out:
            for o in out:
                segx = [np.append(row[4]['fT'], np.nan) for row in self.prj.unilist if o in row[4]['out']]
                segy = [np.append(row[4]['fp'], np.nan) for row in self.prj.unilist if o in row[4]['out']]
                ax.plot(np.hstack(segx)[:-1], np.hstack(segy)[:-1], lw=2, label=o)
            # Shrink current axis's height by 6% on the bottom
            box = ax.get_position()
            ax.set_position([box.x0 + box.width * 0.05, box.y0, box.width * 0.95, box.height])
            # Put a legend below current axis
            ax.legend(loc='upper right', bbox_to_anchor=(-0.04, 1), title='Out', borderaxespad=0, frameon=False)
        if label:
            for txt, xy in lbls:

                ax.annotate(s=txt, xy=xy, weight='bold', fontsize=6, ha='center', va='center')
        divider = make_axes_locatable(ax)
        cax = divider.append_axes('right', size='4%', pad=0.05)
        cb = ColorbarBase(ax=cax, cmap=pscmap, norm=norm, orientation='vertical', ticks=vv)
        cb.set_label('Variance')
        ax.axis(self.prj.trange + self.prj.prange)
        if label:
            ax.set_title(self.prj.name + (len(exc) * ' +{}').format(*exc))
        else:
            ax.set_title(self.prj.name)
        plt.show()
        return ax

    def overlay(self, ax, fc='none', ec='k'):
        for k in self:
            ax.add_patch(PolygonPatch(self.shapes[k], ec=ec, fc=fc, lw=0.5))

    def show_data(self, key, phase, comp, ox=None, which='all'):
        if which == 'inv':
            dt = self.collect_inv_data(key, phase, comp, ox=ox)
        elif which == 'edges':
            dt = self.collect_edges_data(key, phase, comp, ox=ox)
        elif which == 'area':
            dt = self.collect_grid_data(key, phase, comp, ox=ox)
        else:
            dt = self.collect_all_data(key, phase, comp, ox=ox)
        x, y = np.array(dt['pts']).T
        fig, ax = plt.subplots()
        pts = ax.scatter(x, y, c=dt['data'])
        ax.set_title(' '.join(key))
        cb = plt.colorbar(pts)
        cb.set_label('{}-{}'.format(phase, comp))
        plt.show()

    def show_status(self):
        fig, ax = plt.subplots()
        extent = (self.prj.trange[0] - self.tstep / 2, self.prj.trange[1] + self.tstep / 2,
                  self.prj.prange[0] - self.pstep / 2, self.prj.prange[1] + self.pstep / 2)
        cmap = ListedColormap(['orangered', 'limegreen'])
        ax.imshow(self.status, extent=extent, aspect='auto', origin='lower', cmap=cmap)
        self.overlay(ax)
        plt.axis(self.prj.trange + self.prj.prange)
        plt.show()

    def show_delta(self):
        fig, ax = plt.subplots()
        extent = (self.prj.trange[0] - self.tstep / 2, self.prj.trange[1] + self.tstep / 2,
                  self.prj.prange[0] - self.pstep / 2, self.prj.prange[1] + self.pstep / 2)
        im = ax.imshow(self.delta, extent=extent, aspect='auto', origin='lower')
        self.overlay(ax)
        cb = plt.colorbar(im)
        cb.set_label('sec/point')
        plt.title('THERMOCALC execution time')
        plt.axis(self.prj.trange + self.prj.prange)
        plt.show()

    def identify(self, T, p):
        for key in self:
            if Point(T, p).intersects(self.shapes[key]):
                return key

    def ginput(self):
        plt.ion()
        self.show()
        return self.identify(*plt.ginput()[0])

    def isopleths(self, phase, comp, ox=None, which='all',smooth=0, filled=True, step=None, N=None, gradient=False, dt=True, only=None):
        if step is None and N is None:
            N = 10
        if only is not None:
            recs = OrderedDict()
            if which == 'inv':
                d = self.collect_inv_data(only, phase, comp, ox=ox)
            elif which == 'edges':
                d = self.collect_edges_data(only, phase, comp, ox=ox)
            elif which == 'area':
                d = self.collect_grid_data(only, phase, comp, ox=ox)
            else:
                d = self.collect_all_data(only, phase, comp, ox=ox)
            z = d['data']
            if z:
                recs[only] = d
                mn = min(z)
                mx = max(z)
        else:
            print('Collecting...')
            recs, mn, mx = self.merge_data(phase, comp, ox=ox)
        if step:
            cntv = np.arange(0, mx + step, step)
            cntv = cntv[cntv > mn - step]
        else:
            cntv = np.linspace(mn, mx, N)
        # Thin-plate contouring of areas
        print('Contouring...')
        scale = self.tstep / self.pstep
        fig, ax = plt.subplots()
        for key in recs:
            tmin, pmin, tmax, pmax = self.shapes[key].bounds
            ttspace = self.tspace[np.logical_and(self.tspace >= tmin - self.tstep, self.tspace <= tmax + self.tstep)]
            ppspace = self.pspace[np.logical_and(self.pspace >= pmin - self.pstep, self.pspace <= pmax + self.pstep)]
            tg, pg = np.meshgrid(ttspace, ppspace)
            x, y = np.array(recs[key]['pts']).T
            try:
                # Use scaling
                rbf = Rbf(x, scale*y, recs[key]['data'], function='thin_plate', smooth=smooth)
                zg = rbf(tg, scale*pg)
                # experimental
                if gradient:
                    if dt:
                        zg = np.gradient(zg, self.tstep, self.pstep)[0]
                    else:
                        zg = -np.gradient(zg, self.tstep, self.pstep)[1]
                    if N:
                        cntv = N
                    else:
                        cntv = 10
                # ------------
                if filled:
                    cont = ax.contourf(tg, pg, zg, cntv)
                else:
                    cont = ax.contour(tg, pg, zg, cntv)
                patch = PolygonPatch(self.shapes[key], fc='none', ec='none')
                ax.add_patch(patch)
                for col in cont.collections:
                    col.set_clip_path(patch)
            except:
                print('Error for {}'.format(' '.join(key)))
        if only is None:
            self.overlay(ax)
        plt.colorbar(cont)
        if only is None:
            ax.axis(self.prj.trange + self.prj.prange)
            ax.set_title('Isopleths - {}'.format(comp))
        else:
            ax.set_title('{} - {}'.format(' '.join(only), comp))
        plt.show()

    def gridded(self, comp, which='all', smooth=0):
        recs, mn, mx = self.merge_data(comp, which)
        scale = self.tstep / self.pstep
        gd = np.empty(self.tg.shape)
        gd[:] = np.nan
        for key in recs:
            tmin, pmin, tmax, pmax = self.shapes[key].bounds
            ttind = np.logical_and(self.tspace >= tmin - self.tstep, self.tspace <= tmax + self.tstep)
            ppind = np.logical_and(self.pspace >= pmin - self.pstep, self.pspace <= pmax + self.pstep)
            slc = np.ix_(ppind, ttind)
            tg, pg = self.tg[slc], self.pg[slc]
            x, y = np.array(recs[key]['pts']).T
            # Use scaling
            rbf = Rbf(x, scale*y, recs[key]['data'], function='thin_plate', smooth=smooth)
            zg = rbf(tg, scale*pg)
            gd[self.masks[key]] = zg[self.masks[key][slc]]
        return gd

    def save_tab(self, tabfile=None, comps=None):
        if not tabfile:
            tabfile = os.path.join(self.prj.workdir, self.prj.name + '.tab')
        if not comps:
            comps = self.all_data_keys
        data = []
        for comp in tqdm(comps, desc='Exporting'):
            data.append(self.gridded(comp).flatten())
        with open(tabfile, 'wb') as f:
            head = ['psbuilder', self.prj.name + '.tab', '{:12d}'.format(2),
                    'T(°C)', '   {:16.16f}'.format(self.prj.trange[0])[:19],
                    '   {:16.16f}'.format(self.tstep)[:19], '{:12d}'.format(len(self.tspace)),
                    'p(kbar)', '   {:16.16f}'.format(self.prj.prange[0])[:19],
                    '   {:16.16f}'.format(self.pstep)[:19], '{:12d}'.format(len(self.pspace)),
                    '{:12d}'.format(len(data)), (len(data)*'{:15s}').format(*comps)]
            for ln in head:
                f.write(bytes(ln + '\n', 'utf-8'))
            np.savetxt(f, np.transpose(data), fmt='%15.6f', delimiter='')
        print('Saved.')

#
#------------------UTILS---------------
#

def parse_logfile(logfile):
    # res is list of dicts with data and ptguess keys
    # data is dict with keys of phases and each contain dict of components, rbi dict and mode
    # res[0]['data']['g']['mode']
    # res[0]['data']['g']['z']
    # res[0]['data']['g']['rbi']['MnO']
    with open(logfile, 'r', encoding=TCenc) as f:
        out = f.read()
    lines = [''.join([c for c in ln if ord(c)<128]) for ln in out.splitlines() if ln != '']
    pts = []
    res = []
    variance = -1
    if [ix for ix, ln in enumerate(lines) if 'BOMBED' in ln]:
        status = 'bombed'
    else:
        correct = {'L':'liq'}
        for ln in lines:
            if 'variance of required equilibrium' in ln:
                variance = int(ln[ln.index('(') + 1:ln.index('?')])
                break
        bstarts = [ix for ix, ln in enumerate(lines) if ln.startswith(' P(kbar)')]
        bstarts.append(len(lines))
        for bs, be in zip(bstarts[:-1], bstarts[1:]):
            block = lines[bs:be]
            pts.append([float(n) for n in block[1].split()[:2]])
            xyz = [ix for ix, ln in enumerate(block) if ln.startswith('xyzguess')]
            gixs = [ix for ix, ln in enumerate(block) if ln.startswith('ptguess')][0] - 3
            gixe = xyz[-1] + 2
            ptguess = block[gixs:gixe]
            data = {}
            rbix = [ix for ix, ln in enumerate(block) if ln.startswith('rbi yes')][0]
            phases = block[rbix - 1].split()[1:]
            for phase, val in zip(phases, block[rbix].split()[2:]):
                data[phase] = dict(mode=float(val))
            for ix in xyz:
                lbl = block[ix].split()[1]
                phase, comp = lbl[lbl.find('(') + 1:lbl.find(')')], lbl[:lbl.find('(')]
                phase = correct.get(phase, phase)
                data[phase][comp] = float(block[ix].split()[2])
            rbiox = block[rbix + 1].split()[2:]
            for delta in range(len(phases)):
                comp = {c:float(v) for c, v in zip(rbiox, block[rbix + 2 + delta].split()[2:-2])}
                comp['H2O'] = float(block[rbix + 2 + delta].split()[1])
                data[phases[delta]]['rbi'] = comp
            res.append(dict(data=data,ptguess=ptguess))
        if res:
            status = 'ok'
        else:
            status = 'nir'
    return status, variance, np.array(pts).T, res, out

def construct_areas(unilist, invlist, trange, prange):
    def area_exists(indexes):
        def dfs_visit(graph, u, found_cycle, pred_node, marked, path):
            if found_cycle[0]:
                return
            marked[u] = True
            path.append(u)
            for v in graph[u]:
                if marked[v] and v != pred_node:
                    found_cycle[0] = True
                    return
                if not marked[v]:
                    dfs_visit(graph, v, found_cycle, u, marked, path)
        # create graph
        graph = {}
        for ix in indexes:
            b, e = unilist[ix][2], unilist[ix][3]
            if b == 0:
                nix = max(list(inv_coords.keys())) + 1
                inv_coords[nix] = unilist[ix][4]['T'][0], unilist[ix][4]['p'][0]
                b = nix
            if e == 0:
                nix = max(list(inv_coords.keys())) + 1
                inv_coords[nix] = unilist[ix][4]['T'][-1], unilist[ix][4]['p'][-1]
                e = nix
            if b in graph:
                graph[b] = graph[b] + (e,)
            else:
                graph[b] = (e,)
            if e in graph:
                graph[e] = graph[e] + (b,)
            else:
                graph[e] = (b,)
            uni_index[(b, e)] = unilist[ix][0]
            uni_index[(e, b)] = unilist[ix][0]
        # do search
        path = []
        marked = { u : False for u in graph }
        found_cycle = [False]
        for u in graph:
            if not marked[u]:
                dfs_visit(graph, u, found_cycle, u, marked, path)
            if found_cycle[0]:
                break
        return found_cycle[0], path
    uni_index = {}
    for r in unilist:
        uni_index[(r[2], r[3])] = r[0]
        uni_index[(r[3], r[2])] = r[0]
    inv_coords = {}
    for r in invlist:
        inv_coords[r[0]] = r[2]['T'][0], r[2]['p'][0]
    faces = {}
    for ix, uni in enumerate(unilist):
        f1 = frozenset(uni[4]['phases'])
        f2 = frozenset(uni[4]['phases'] - uni[4]['out'])
        if f1 in faces:
            faces[f1].append(ix)
        else:
            faces[f1] = [ix]
        if f2 in faces:
            faces[f2].append(ix)
        else:
            faces[f2] = [ix]
        # topology of polymorphs is degenerated
        for poly in [{'sill', 'and'}, {'ky', 'and'}, {'sill', 'ky'}, {'q', 'coe'}, {'diam', 'gph'}]:
            if poly.issubset(uni[4]['phases']):
                f2 = frozenset(uni[4]['phases'] - poly.difference(uni[4]['out']))
                if f2 in faces:
                    faces[f2].append(ix)
                else:
                    faces[f2] = [ix]
    vertices, edges, phases = [], [], []
    tedges, tphases = [], []
    for f in faces:
        exists, path = area_exists(faces[f])
        if exists:
            edge = []
            vert = []
            for b, e in zip(path, path[1:] + path[:1]):
                edge.append(uni_index.get((b, e), None))
                vert.append(inv_coords[b])
            # check for bad topology
            if not None in edge:
                edges.append(edge)
                vertices.append(vert)
                phases.append(f)
            else:
                raise Exception('Topology error in path {}. Edges {}'.format(path, edge))
        else:
            # loop not found, search for range crossing chain
            for ppath in itertools.permutations(path):
                edge = []
                vert = []
                for b, e in zip(ppath[:-1], ppath[1:]):
                    edge.append(uni_index.get((b, e), None))
                    vert.append(inv_coords[b])
                vert.append(inv_coords[e])
                if not None in edge:
                    x, y = vert[0]
                    if (x < trange[0] or x > trange[1] or y < prange[0] or y > prange[1]):
                        x, y = vert[-1]
                        if (x < trange[0] or x > trange[1] or y < prange[0] or y > prange[1]):
                            tedges.append(edge)
                            tphases.append(f)
                    break
    return vertices, edges, phases, tedges, tphases

def update_guesses(scriptfile, guesses):
    # Store scriptfile content and initialize dicts
    with open(scriptfile, 'r', encoding=TCenc) as f:
        sc = f.readlines()
    gsb = [ix for ix, ln in enumerate(sc) if '{PSBGUESS-BEGIN}' in ln]
    gse = [ix for ix, ln in enumerate(sc) if '{PSBGUESS-END}' in ln]
    if gsb and gse:
        with open(scriptfile, 'w', encoding=TCenc) as f:
            for ln in sc[:gsb[0] + 1]:
                f.write(ln)
            for ln in guesses:
                f.write(ln)
                f.write('\n')
            for ln in sc[gse[0]:]:
                f.write(ln)

def main():
    application = QtWidgets.QApplication(sys.argv)
    window = PSBuilder()
    desktop = QtWidgets.QDesktopWidget().availableGeometry()
    width = (desktop.width() - window.width()) / 2
    height = (desktop.height() - window.height()) / 2
    window.show()
    window.move(width, height)
    sys.exit(application.exec_())

if __name__ == "__main__":
    main()
