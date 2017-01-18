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
from pkg_resources import resource_filename

from PyQt5 import QtCore, QtGui, QtWidgets

import numpy as np
import matplotlib

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar)

from .ui_psbuilder import Ui_PSBuilder
from .ui_addinv import Ui_AddInv
from .ui_adduni import Ui_AddUni
from .ui_uniguess import Ui_UniGuess

__version__ = '2.0.5master'
# Make sure that we are using QT5
matplotlib.use('Qt5Agg')

matplotlib.rcParams['xtick.direction'] = 'out'
matplotlib.rcParams['ytick.direction'] = 'out'

popenkw = dict(stdout=subprocess.PIPE, stdin=subprocess.PIPE,
               stderr=subprocess.STDOUT, universal_newlines=False)
TCenc = 'mac-roman'


class PSBuilder(QtWidgets.QMainWindow, Ui_PSBuilder):
    """Main class
    """
    def __init__(self, parent=None):
        super(PSBuilder, self).__init__(parent)
        self.setupUi(self)
        self.resize(1024, 768)
        self.setWindowTitle('PSBuilder')
        window_icon = resource_filename(__name__, 'images/pypsbuilder.png')
        self.setWindowIcon(QtGui.QIcon(window_icon))
        self.__changed = False
        self.about_dialog = AboutDialog(__version__)
        self.unihigh = None
        self.invhigh = None

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
        self.phaseview.show()
        # Create outmodel
        self.outmodel = QtGui.QStandardItemModel(self.outview)
        self.outview.setModel(self.outmodel)
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
        self.pushCalcTatP.clicked.connect(lambda: self.do_calc(True, [], []))
        self.pushCalcPatT.clicked.connect(lambda: self.do_calc(False, [], []))
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
        #self.pushInvAdd.toggled.connect(self.addudinv)
        #self.pushInvAdd.setCheckable(True)
        self.pushInvAuto.clicked.connect(self.auto_inv_calc)
        self.pushUniZoom.clicked.connect(self.zoom_to_uni)
        self.pushUniZoom.setCheckable(True)
        self.pushManual.toggled.connect(self.add_userdefined)
        self.pushManual.setCheckable(True)
        self.pushInvRemove.clicked.connect(self.remove_inv)
        self.pushUniRemove.clicked.connect(self.remove_uni)
        self.tabOutput.tabBarDoubleClicked.connect(self.show_output)
        self.splitter_bottom.setSizes((400, 100))

        self.uniview.doubleClicked.connect(self.show_uni)
        self.invview.doubleClicked.connect(self.show_inv)
        self.invview.customContextMenuRequested[QtCore.QPoint].connect(self.invviewRightClicked)

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
        self.invsel.selectionChanged.connect(self.clean_high)

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
        self.unimodel.dataChanged.connect(self.show_uni)
        self.unisel = self.uniview.selectionModel()
        self.unisel.selectionChanged.connect(self.clean_high)


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
            builder_settings.setValue("overwrite", self.checkOverwrite.checkState())
            builder_settings.setValue("tcexe", self.tcexeEdit.text())
            builder_settings.setValue("drexe", self.drawpdexeEdit.text())
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
            self.checkOverwrite.setCheckState(builder_settings.value("overwrite", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            # default exe
            if sys.platform.startswith('win'):
                tcexe = 'tc340.exe'
                drexe = 'dr116.exe'
            elif sys.platform.startswith('linux'):
                tcexe = 'tc340L'
                drexe = 'dr115L'
            else:
                tcexe = 'tc340'
                drexe = 'dr116'
            self.tcexeEdit.setText(builder_settings.value("tcexe", tcexe, type=str))
            self.drawpdexeEdit.setText(builder_settings.value("drexe", drexe, type=str))
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
                self.ready = True
                self.project = None
                self.changed = True
                # update settings tab
                self.apply_setting(4)
                # read scriptfile
                self.read_scriptfile()
                # update plot
                self.plot()
                self.statusBar().showMessage('Ready')

    def doInit(self):
        """Parse configs and test TC settings
        """
        try:
            if not os.path.exists(self.prefsfile):
                self.errinfo = 'No tc-prefs.txt file in working directory.'
                raise Exception()
            self.errinfo = 'tc-prefs.txt file in working directory cannot be accessed.'
            for line in open(self.prefsfile, 'r'):
                kw = line.split()
                if kw != []:
                    if kw[0] == 'scriptfile':
                        self.bname = kw[1]
                        if not os.path.exists(self.scriptfile):
                            self.errinfo = 'tc-prefs: scriptfile tc-' + self.bname + '.txt does not exists in your working directory.'
                            raise Exception()
                    if kw[0] == 'calcmode':
                        if kw[1] != '1':
                            self.errinfo = 'tc-prefs: calcmode must be 1.'
                            raise Exception()

            self.excess = []
            self.trange = (200., 1000.)
            self.prange = (0.1, 20.)
            check = {'axfile': False, 'setbulk': False,
                     'setexcess': False, 'drawpd': False}
            self.errinfo = 'Check your scriptfile.'
            with open(self.scriptfile, 'r', encoding=TCenc) as f:
                lines = f.readlines()
            for line in lines:
                kw = line.split('%')[0].split()
                if kw != []:
                    if kw[0] == 'axfile':
                        self.axname = kw[1]
                        if not os.path.exists(self.axfile):
                            self.errinfo = 'Axfile tc-' + self.axname + '.txt does not exists in working directory'
                            raise Exception()
                        check['axfile'] = True
                    if kw[0] == 'setdefTwindow':
                        self.trange = (float(kw[-2]), float(kw[-1]))
                    if kw[0] == 'setdefPwindow':
                        self.prange = (float(kw[-2]), float(kw[-1]))
                    if kw[0] == 'setbulk':
                        self.bulk = kw[1:]
                        if 'yes' in self.bulk:
                            self.bulk.remove('yes')
                        check['setbulk'] = True
                    if kw[0] == 'setexcess':
                        self.excess = kw[1:]
                        if 'yes' in self.excess:
                            self.excess.remove('yes')
                        if 'no' in self.excess:
                            self.excess.remove('no')
                        if 'ask' in self.excess:
                            self.errinfo = 'Setexcess must not be set to ask.'
                            raise Exception()
                        check['setexcess'] = True
                    if kw[0] == 'calctatp':
                        if not kw[1:2] == ['ask']:
                            self.errinfo = 'Calctatp must be set to ask.'
                            raise Exception()
                    if kw[0] == 'drawpd':
                        if kw[1:2] == ['no']:
                            self.errinfo = 'Drawpd must be set to yes.'
                            raise Exception()
                        check['drawpd'] = True
                    if kw[0] == 'dogmin':
                        if not kw[1:2] == ['no']:
                            self.errinfo = 'Dogmin must be set to no.'
                            raise Exception()
                    if kw[0] == 'fluidpresent':
                        self.errinfo = 'Fluidpresent must be deleted from scriptfile.'
                        raise Exception()
                    if kw[0] == 'seta':
                        if not kw[1:2] == ['no']:
                            self.errinfo = 'Seta must be set to no.'
                            raise Exception()
                    if kw[0] == 'setmu':
                        if not kw[1:2] == ['no']:
                            self.errinfo = 'Setmu must be set to no.'
                            raise Exception()
                    if kw[0] == 'usecalcq':
                        if kw[1:2] == ['ask']:
                            self.errinfo = 'Usecalcq must be yes or no.'
                            raise Exception()
                    if kw[0] == 'pseudosection':
                        if kw[1:2] == ['ask']:
                            self.errinfo = 'Pseudosection must be yes or no.'
                            raise Exception()
                    if kw[0] == 'zeromodeiso':
                        if not kw[1:2] == ['yes']:
                            self.errinfo = 'Zeromodeiso must be set to yes.'
                            raise Exception()
                    if kw[0] == 'setmodeiso':
                        if not kw[1:2] == ['yes']:
                            self.errinfo = 'Setmodeiso must be set to yes.'
                            raise Exception()
                    if kw[0] == 'convliq':
                        self.errinfo = 'Convliq not yet supported.'
                        raise Exception()
                    if kw[0] == 'setiso':
                        if kw[1:2] != ['no']:
                            self.errinfo = 'Setiso must be set to no.'
                            raise Exception()

            if not check['axfile']:
                self.errinfo = 'Axfile name must be provided in scriptfile.'
                raise Exception()
            if not check['setbulk']:
                self.errinfo = 'Setbulk must be provided in scriptfile.'
                raise Exception()
            if not check['setexcess']:
                self.errinfo = 'Setexcess must not be set to ask. To suppress this error put empty setexcess keyword to your scriptfile.'
                raise Exception()
            if not check['drawpd']:
                self.errinfo = 'Drawpd must be set to yes. To suppress this error put drawpd yes keyword to your scriptfile.'
                raise Exception()

            # What???
            nc = 0
            for i in self.axname:
                if i.isupper():
                    nc += 1
            self.nc = nc
            # run tc to initialize
            tcout = self.initFromTC()
            # disconnect signal
            try:
                self.phasemodel.itemChanged.disconnect(self.phase_changed)
            except Exception:
                pass
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
            self.initViewModels()
            self.pushUniZoom.setChecked(False)
            self.errinfo = ''
            return True
        except BaseException as e:
            qb = QtWidgets.QMessageBox
            qb.critical(self, 'Error!', self.errinfo, qb.Abort)
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
                for row in data['unilist']:
                    self.unimodel.appendRow(row)
                self.adapt_uniview()
                for row in data['invlist']:
                    self.invmodel.appendRow(row)
                self.invview.resizeColumnsToContents()
                # all done
                self.ready = True
                self.project = projfile
                self.changed = False
                if projfile in self.recent:
                    self.recent.pop(self.recent.index(projfile))
                self.recent.insert(0, projfile)
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
                    'invlist': self.invmodel.invlist[1:]}
            # do save
            stream = gzip.open(self.project, 'wb')
            pickle.dump(data, stream)
            stream.close()
            self.changed = False
            if self.project in self.recent:
                self.recent.pop(self.recent.index(self.project))
            self.recent.insert(0, self.project)
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
        p = subprocess.Popen(exe, cwd=self.workdir, startupinfo=startupinfo, **popenkw)
        output = p.communicate(input=instr.encode(TCenc))[0].decode(TCenc)
        sys.stdout.flush()
        self.logText.setPlainText('Working directory:{}\n\n'.format(self.workdir) + output)
        return output

    def initFromTC(self):
        tcout = self.runprog(self.tc, '\nkill\n\n')
        self.phases = tcout.split('choose from:')[1].split('\n')[0].split()
        self.phases.sort()
        self.vre = int(tcout.split('variance of required equilibrium ')[1].split('\n')[0].split('(')[1].split('?')[0])
        self.deftrange = self.trange
        self.defprange = self.prange
        self.errinfo = ''
        self.tcversion = tcout.split('\n')[0]
        return tcout

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
                        out = r.split('-')[1].split()
                        phases = r.split('-')[0].split() + out
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
    def ofile(self):
        return os.path.join(self.workdir, 'tc-' + self.bname + '-o.txt')

    @property
    def drawpdfile(self):
        return os.path.join(self.workdir, 'dr-' + self.bname + '.txt')

    @property
    def tcinvestigatorfile(self):
        return os.path.join(self.workdir, 'dr-investigator.txt')

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
            # settings
            self.trange = trange
            self.prange = prange
            self.statusBar().showMessage('Project re-initialized from scriptfile.')
            self.changed = True
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

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
        if self.ready:
            if self.unihigh is not None:
                self.unihigh = None
                self.textOutput.clear()
                self.textFullOutput.clear()
                self.plot()
            if self.invhigh is not None:
                self.invhigh = None
                self.textOutput.clear()
                self.textFullOutput.clear()
                self.plot()
            if self.pushUniZoom.isChecked():
                idx = self.unisel.selectedIndexes()
                k = self.unimodel.getRow(idx[0])
                T, p = self.getunicutted(k[4], k[2], k[3])
                dT = (T.max() - T.min()) / 5
                dp = (p.max() - p.min()) / 5
                self.ax.set_xlim([T.min() - dT, T.max() + dT])
                self.ax.set_ylim([p.min() - dp, p.max() + dp])
                self.canvas.draw()


    def guess_toclipboard(self, p, T, clabels, vals, r):
        clipboard = QtWidgets.QApplication.clipboard()
        txt = '% --------------------------------------------------------'
        txt += '\n'
        txt += '% at P = {}, T = {}, for: '.format(p, T)
        txt += ' '.join(r['phases'])
        txt += ' with ' + ', '.join(['{} = 0'.format(o) for o in r['out']])
        txt += '\n'
        txt += '% --------------------------------------------------------'
        txt += '\n'
        txt += 'ptguess {} {}'.format(p, T)
        txt += '\n'
        txt += '% --------------------------------------------------------'
        txt += '\n'
        for c, v in zip(clabels, vals):
            txt += 'xyzguess {:<12}{:>10}'.format(c, v)
            txt += '\n'
        txt += '% --------------------------------------------------------'
        txt += '\n'
        clipboard.setText(txt)
        self.statusBar().showMessage('Guesses copied to clipboard.')

    def invsel_guesses(self):
        if self.invsel.hasSelection():
            idx = self.invsel.selectedIndexes()
            r = self.invmodel.data(idx[2])
            if not r['output'].startswith('User-defined'):
                try:
                    clabels, vals = self.parse_output(r['output'], False)
                    p, T = vals[0][:2]
                    vals = vals[0][2:]
                    clabels = clabels[2:]
                    self.guess_toclipboard(p, T, clabels, vals, r)
                except:
                    self.statusBar().showMessage('Unexpected output parsing error.')
            else:
                self.statusBar().showMessage('Guesses cannot be copied from user-defined invariant point.')

    def unisel_guesses(self):
        if self.unisel.hasSelection():
            idx = self.unisel.selectedIndexes()
            r = self.unimodel.data(idx[4])
            if not r['output'].startswith('User-defined'):
                try:
                    clabels, vals = self.parse_output(r['output'], False)
                    l = ['p = {}, T = {}'.format(p, T) for p, T in zip(r['p'], r['T'])]
                    uniguess = UniGuess(l, self)
                    respond = uniguess.exec()
                    if respond == QtWidgets.QDialog.Accepted:
                        ix = uniguess.getValue()
                        p, T = r['p'][ix], r['T'][ix]
                        self.guess_toclipboard(p, T, clabels[2:], vals[ix][2:], r)
                except:
                    self.statusBar().showMessage('Unexpected output parsing error.')
            else:
                self.statusBar().showMessage('Guesses cannot be copied from user-defined univariant line.')

    def parse_output(self, txt, getmodes=True):
        t = txt.splitlines()
        t = [r.strip(u'\u00A7') for r in t]
        za = [i + 1 for i in range(len(t)) if t[i].startswith('----')]
        st = [i for i in range(len(t)) if t[i].startswith('    mode')]

        clabels = []
        for ix in range(za[0], st[0] - 1, 2):
            clabels.extend(t[ix].split())
        mlabels = clabels[:2] + t[st[0]].split()[1:]
        vals, modes = [], []
        # estimate fixed width
        pl = t[st[0]].split()[-2]
        width = len(t[st[0]]) - t[st[0]].index(pl) - len(pl)

        for b, e in zip(za, st):
            val = []
            for ix in range(b + 1, e, 2):
                val.extend(list(map(float, t[ix].split())))
            vals.append(val)
            modstr = t[e + 1][8:] # skip mode
            mod = [float(modstr[0 + i:width + i]) for i in range(0, len(modstr), width)] #fixed width split
            modes.append(val[:2] + mod)

        # clabels = t[za[0]].split()
        # mlabels = clabels[:2] + t[st[0]].split()[1:]
        # vals, modes = [], []

        # for b, e in zip(za, st):
        #     val = list(map(float, t[b + 1].split()))
        #     mod = list(map(float, t[e + 1].split()))
        #     vals.append(val)
        #     modes.append(val[:2] + mod)
        #     for off in range((e-b-4)//2):
        #         vals.append(list(map(float, t[b + 3 + 2*off].split())))
        #         modes.append(list(map(float, t[e + 3 + 2*off].split())))

        if getmodes:
            return np.array(mlabels), np.array(modes)
        else:
            return np.array(clabels), np.array(vals)

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
        return set(phases), set(out)

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
            if not r['output'].startswith('User-defined'):
                try:
                    mlabels, modes = self.parse_output(r['output'])
                    mask = ~np.in1d(mlabels, list(r['out']))
                    mlabels = mlabels[mask]
                    modes = modes[:, mask]
                    txt = ''
                    h_format = '{:>10}{:>10}' + '{:>8}' * (len(mlabels) - 2)
                    n_format = '{:10.4f}{:10.4f}' + '{:8.4f}' * (len(mlabels) - 2)
                    txt += h_format.format(*mlabels)
                    txt += '\n'
                    for row in modes:
                        txt += n_format.format(*row)
                        txt += '\n'
                    txt += h_format.format(*mlabels)
                    self.textOutput.setPlainText(txt)
                except:
                    self.statusBar().showMessage('Unexpected output parsing error.')
            else:
                self.textOutput.setPlainText(r['output'])
            self.textFullOutput.setPlainText(r['output'])

    def show_uni(self, index):
        row = self.unimodel.getRow(index)
        self.set_phaselist(row[4])
        T, p = self.getunicutted(row[4], row[2], row[3])
        self.unihigh = (T, p)
        self.invhigh = None
        self.plot()
        if self.pushUniZoom.isChecked():
            self.zoom_to_uni(True)

    def show_inv(self, index):
        d = self.invmodel.getData(index, 'Data')
        self.set_phaselist(d)
        self.invhigh = (d['T'], d['p'])
        self.unihigh = None
        self.plot()

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
            nr4 = dict(phases=bphases, out=bset, output='User-defined')
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
            self.do_calc(True, phases=bphases, out=bset)

    def zoom_to_uni(self, checked):
        if checked:
            if self.unisel.hasSelection():
                idx = self.unisel.selectedIndexes()
                row = self.unimodel.getRow(idx[0])
                T, p = self.getunicutted(row[4], row[2], row[3])
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
                    if row[4]['output'].startswith('User-defined'):
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
                self.plot()
                self.statusBar().showMessage('Univariant line removed')

    def clicker(self, event):
        if event.inaxes is not None:
            phases, out = self.get_phases_out()
            r = {'phases':phases, 'out':out, 'cmd': ''}
            isnew, id = self.getidinv(r)
            if isnew:
                addinv = AddInv(parent=self)
            else:
                addinv = AddInv(label=False, parent=self)
            addinv.set_from_event(event)
            respond = addinv.exec()
            if respond == QtWidgets.QDialog.Accepted:
                label, T, p = addinv.getValues()
                r['T'], r['p'], r['output'] = np.array([T]), np.array([p]), 'User-defined invariant point.'
                if isnew:
                    self.invmodel.appendRow((id, label, r))
                else:
                    for row in self.invmodel.invlist[1:]:
                        if row[0] == id:
                            row[2] = r
                            if self.invhigh is not None:
                                self.set_phaselist(r)
                                self.invhigh = (r['T'], r['p'])
                                self.unihigh = None
                self.invview.resizeColumnsToContents()
                self.plot()
                self.statusBar().showMessage('User-defined invariant point added.')
            self.pushManual.setChecked(False)

    def add_userdefined(self, checked=True):
        if self.ready:
            phases, out = self.get_phases_out()
            if len(out) == 1:
                if checked:
                    invs = []
                    for row in self.invmodel.invlist[1:]:
                        d = row[2]
                        if phases.issubset(d['phases']):
                            if out.issubset(d['out']):
                                invs.append(row[0])
                    if len(invs) > 1:
                        adduni = AddUni(invs, self)
                        respond = adduni.exec()
                        if respond == QtWidgets.QDialog.Accepted:
                            label, b, e = adduni.getValues()
                            if b != e:
                                r = {'T': np.array([]), 'p': np.array([]),
                                     'output': 'User-defined univariant line.',
                                     'phases': set(phases), 'out': set(out), 'cmd': ''}
                                isnew, id = self.getiduni(r)
                                if isnew:
                                    self.unimodel.appendRow((id, label, b, e, r))
                                else:
                                    for row in self.unimodel.unilist:
                                        if row[0] == id:
                                            row[2] = b
                                            row[3] = e
                                            row[4] = r
                                            if label:
                                                row[1] = label
                                            if self.unihigh is not None:
                                                self.set_phaselist(r)
                                                T, p = self.getunicutted(r, row[2], row[3])
                                                self.unihigh = (T, p)
                                                self.invhigh = None
                                self.adapt_uniview()
                                self.plot()
                                self.statusBar().showMessage('User-defined univariant line.')
                            else:
                                msg = 'Begin and end must be different.'
                                qb = QtWidgets.QMessageBox
                                qb.critical(self, 'Error!',
                                            msg, qb.Abort)
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

    def do_calc(self, cT, phases=[], out=[]):
        if self.ready:
            if phases == []:
                for i in range(self.phasemodel.rowCount()):
                    item = self.phasemodel.item(i)
                    if item.checkState() == QtCore.Qt.Checked:
                        phases.append(item.text())
            if out == []:
                for i in range(self.outmodel.rowCount()):
                    item = self.outmodel.item(i)
                    if item.checkState() == QtCore.Qt.Checked:
                        out.append(item.text())
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
                typ, label, r = self.parsedrfile()
                r['phases'] = set(phases)
                r['out'] = set(out)
                r['cmd'] = ans
                if typ == 'uni':
                    if len(r['T']) > 1:
                        isnew, id = self.getiduni(r)
                        if isnew:
                            self.unimodel.appendRow((id, label, 0, 0, r))
                            self.statusBar().showMessage('New univariant line calculated.')
                        else:
                            if not self.checkOverwrite.isChecked():
                                for row in self.unimodel.unilist:
                                    if row[0] == id:
                                        row[1] = label
                                        row[4] = r
                                        if self.unihigh is not None:
                                            self.set_phaselist(r)
                                            T, p = self.getunicutted(r, row[2], row[3])
                                            self.unihigh = (T, p)
                                            self.invhigh = None
                                        self.statusBar().showMessage('Univariant line {} re-calculated.'.format(id))
                            else:
                                self.statusBar().showMessage('Univariant line already exists.')
                        self.adapt_uniview()
                        self.changed = True
                        self.plot()
                    elif len(r['T']) > 0:
                        self.statusBar().showMessage('Only one point calculated. Change range.')
                    else:
                        self.statusBar().showMessage('Nothing in range.')
                else:
                    self.statusBar().showMessage('Bombed.')
            elif len(out) == 2:
                tmpl = '{}\n\n{}\n{:.{prec}f} {:.{prec}f} {:.{prec}f} {:.{prec}f}\nn\n\nkill\n\n'
                ans = tmpl.format(' '.join(phases), ' '.join(out), *trange, *prange, prec=prec)
                tcout = self.runprog(self.tc, ans)
                typ, label, r = self.parsedrfile()
                r['phases'] = set(phases)
                r['out'] = set(out)
                r['cmd'] = ans
                if typ == 'inv':
                    if len(r['T']) > 0:
                        isnew, id = self.getidinv(r)
                        if isnew:
                            self.invmodel.appendRow((id, label, r))
                            self.statusBar().showMessage('New invariant point calculated.')
                        else:
                            if not self.checkOverwrite.isChecked():
                                for row in self.invmodel.invlist[1:]:
                                    if row[0] == id:
                                        row[1] = label
                                        row[2] = r
                                        if self.invhigh is not None:
                                            self.set_phaselist(r)
                                            self.invhigh = (r['T'], r['p'])
                                            self.unihigh = None
                                        self.statusBar().showMessage('Invariant point {} re-calculated.'.format(id))
                            else:
                                self.statusBar().showMessage('Invariant point already exists.')
                        self.invview.resizeColumnsToContents()
                        self.changed = True
                        self.plot()
                    else:
                        self.statusBar().showMessage('Nothing in range.')
                else:
                    self.statusBar().showMessage('Bombed.')
            else:
                self.statusBar().showMessage('{} zero mode phases selected. Select one or two!'.format(len(out)))
            #########
        else:
            self.statusBar().showMessage('Project is not yet initialized.')

    def parsedrfile(self):
        """Parse intermediate drfile
        """
        dr = []
        with open(self.drfile, 'r', encoding=TCenc) as drfile:
            for line in drfile:
                n = line.split('%')[0].strip()
                if n != '':
                    dr.append(n)

        typ, label, zm = '', '', {}
        if len(dr) > 0:
            label = ' '.join(dr[0].split()[1:])
            with open(self.ofile, 'r', encoding=TCenc) as ofile:
                output = ofile.read()
            if dr[0].split()[0] == 'u<k>':
                typ = 'uni'
                data = dr[2:]
            elif dr[0].split()[0] == 'i<k>':
                typ = 'inv'
                data = dr[1:]
            else:
                return 'none', label, zm
            pts = np.array([float(v) for v in ' '.join(data).split()])
            zm['p'] = pts[0::2]
            zm['T'] = pts[1::2]
            zm['output'] = output
            t = output.splitlines()
            t = [r.strip(u'\u00A7').strip() for r in t]
            za = [i + 1 for i in range(len(t)) if t[i].startswith('-')]
            if za:
                if t[za[0] + 1].startswith('#'):
                    typ = 'none'  # nonexisting values calculated
        return typ, label, zm

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
                ex = self.excess[:]
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
                    if u[4]['output'].startswith('User-defined'):
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
                        vertices, edges, phases = self.construct_areas()
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
                                     ' '.join(['u{}'.format(e['id']) for e in ed]) +
                                     ' % ' + ' '.join(ph) + '\n')
                                output.write(d)
                                tcinv.write(' '.join(list(ph) + self.excess) + '\n')
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
                qb.critical(self, 'Error {} during drawpd export!'.format(err), self.errinfo, qb.Abort)

    def construct_areas(self):
        import networkx as nx
        # Create Graph
        G = nx.Graph()
        for inv in self.invmodel.invlist[1:]:
            G.add_node(inv[0], label=inv[1], phases=inv[2]['phases'], out=inv[2]['out'], p=inv[2]['p'][0], T=inv[2]['T'][0])
        for uni in self.unimodel.unilist:
            if uni[2] != 0 and uni[3] != 0:
                G.add_edge(uni[2], uni[3], id=uni[0], label=uni[1], phases=uni[4]['phases'], out=uni[4]['out'])
        # skeletonize
        todel = [k for k,v in G.degree().items() if v < 2]
        while todel:
            for k in todel:
                G.remove_node(k)
            todel = [k for k,v in G.degree().items() if v < 2]
        # Convert to DiGraph and find all enclosed areas
        H = nx.DiGraph(G)
        ed = H.edges()
        areas = []
        vertices = []
        while ed:
            # choose arbitrary start
            go = True
            st = ed[0]
            err = 0
            vert = [(H.node[st[-2]]['T'], H.node[st[-2]]['p']), (H.node[st[-1]]['T'], H.node[st[-1]]['p'])]
            while go:
                (x0, y0), (x1, y1) = vert[-2:]
                u = (x1 - x0, y1 - y0)
                H.remove_edge(st[-2], st[-1])
                suc = H.successors(st[-1])
                if st[-2] in suc:
                    suc.pop(suc.index(st[-2]))
                ang = np.array([])
                nvert = []
                # find left most
                for n in suc:
                    x2, y2 = H.node[n]['T'], H.node[n]['p']
                    v = (x2 - x1, y2 - y1)
                    ang = np.append(ang, np.degrees(np.arctan2(u[1], u[0]) - np.arctan2(v[1], v[0])) % 360)
                    nvert.append((x2, y2))
                ang[ang >= 180] -= 360
                po = suc[ang.argmin()]
                st += (po,)
                vert += [nvert[ang.argmin()]]
                if po == st[0]:
                    H.remove_edge(st[-2], st[-1])
                    go = False
            # check for outer polygon
            if 0.5 * (sum(x0*y1 - x1*y0 for ((x0, y0), (x1, y1)) in zip(vert[:-1], vert[1:]))) > 0:
                areas.append(st)
                vertices.append(vert)
            # what remains...
            ed = H.edges()
        # find phases
        edges = [[G[c[ix - 1]][c[ix]] for ix in range(1, len(c))] for c in areas]
        phases = [set.intersection(*[edg['phases'] for edg in c]) for c in edges]
        return vertices, edges, phases

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

    def getunicutted(self, r, b, e):
        T = r['T'].copy()
        p = r['p'].copy()
        invids = [r[0] for r in self.invmodel.invlist]
        if b > 0:
            inv = invids.index(b)
            T1 = self.invmodel.invlist[inv][2]['T'][0]
            p1 = self.invmodel.invlist[inv][2]['p'][0]
        else:
            T1, p1 = T[0], p[0]
        if e > 0:
            inv = invids.index(e)
            T2 = self.invmodel.invlist[inv][2]['T'][0]
            p2 = self.invmodel.invlist[inv][2]['p'][0]
        else:
            T2, p2 = T[-1], p[-1]
        if len(T) == 0:
            return np.array([T1, T2]), np.array([p1, p2])
        elif len(T) == 1:
            dT = T2 - T1
            dp = p2 - p1
            d2 = dT**2 + dp**2
            u = (dT * (T[0] - T1) + dp * (p[0] - p1)) / d2
            if u > 0 and u < 1:
                return np.array([T1, T[0], T2]), np.array([p1, p[0], p2])
            else:
                return np.array([T1, T2]), np.array([p1, p2])
        else:
            i1 = self.getidx(T, p, T1, p1)
            i2 = self.getidx(T, p, T2, p2)
            if i2 > i1:
                za, ko = i1, i2
            else:
                za, ko = i2, i1
                b, e = e, b
                T1, T2 = T2, T1
                p1, p2 = p2, p1
            return np.hstack([T1, T[za:ko], T2]), np.hstack([p1, p[za:ko], p2])

    def getidx(self, T, p, Tp, pp):
        st = np.array([T[:-1], p[:-1]])
        vv = np.array([Tp - T[:-1], pp - p[:-1]])
        ww = np.array([np.diff(T), np.diff(p)])
        rat = sum(vv*ww)/np.linalg.norm(ww, axis=0)**2
        h = st + rat*ww
        d2 = sum(np.array([Tp - h[0], pp - h[1]])**2)
        cnd = np.flatnonzero(abs(rat - 0.5)<=0.5)
        if not np.any(cnd):
            ix = abs(rat - 0.5).argmin()
            if rat[ix]>1:
                ix += 1
            elif rat[ix]<0:
                ix -= 1
        else:
            ix = cnd[d2[cnd].argmin()]
        return ix + 1

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
            lalfa = self.spinAlpha.value()/100
            unilabel_kw = dict(ha='center', va='center', size='small',
                               bbox=dict(facecolor='cyan', alpha=lalfa, pad=4))
            invlabel_kw = dict(ha='center', va='center', size='small',
                               bbox=dict(facecolor='yellow', alpha=lalfa, pad=4))
            unihigh_kw = dict(lw=3, alpha=0.6, marker='o', ms=4, color='red',
                              zorder=10)
            invhigh_kw = dict(alpha=0.6, ms=6, color='red', zorder=10)
            if self.figure.axes == []:
                cur = None
            else:
                cur = (self.ax.get_xlim(), self.ax.get_ylim())
            self.ax = self.figure.add_subplot(111)
            self.ax.cla()
            self.ax.format_coord = self.format_coord
            for k in self.unimodel.unilist:
                T, p = self.getunicutted(k[4], k[2], k[3])
                self.ax.plot(T, p, 'k')
                if self.checkLabelUni.isChecked():
                    Tl, pl = self.getunilabelpoint(T, p)
                    if self.checkLabels.isChecked():
                        self.ax.text(Tl, pl, k[1], **unilabel_kw)
                    else:
                        self.ax.text(Tl, pl, str(k[0]), **unilabel_kw)
            for k in self.invmodel.invlist[1:]:
                T, p = k[2]['T'], k[2]['p']
                self.ax.plot(T, p, 'k.')
                if self.checkLabelInv.isChecked():
                    if self.checkLabels.isChecked():
                        self.ax.text(T, p, k[1], **invlabel_kw)
                    else:
                        self.ax.text(T, p, str(k[0]), **invlabel_kw)
            self.ax.set_xlabel('Temperature [C]')
            self.ax.set_ylabel('Pressure [kbar]')
            ex = self.excess[:]
            ex.insert(0, '')
            self.ax.set_title(self.axname + ' +'.join(ex))
            if self.unihigh is not None:
                self.ax.plot(self.unihigh[0], self.unihigh[1], '-',
                             **unihigh_kw)
            if self.invhigh is not None:
                self.ax.plot(self.invhigh[0], self.invhigh[1], 'o',
                             **invhigh_kw)
            if cur is None:
                self.ax.set_xlim(self.trange)
                self.ax.set_ylim(self.prange)
            else:
                self.ax.set_xlim(cur[0])
                self.ax.set_ylim(cur[1])
            self.canvas.draw()


class InvModel(QtCore.QAbstractTableModel):
    def __init__(self, parent, *args):
        super(InvModel, self).__init__(parent, *args)
        self.invlist = []
        self.header = ['ID', 'Label', 'Data']

    def rowCount(self, parent=None):
        return len(self.invlist)

    def columnCount(self, parent=None):
        return len(self.header)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        elif role != QtCore.Qt.DisplayRole:
            return None
        return self.invlist[index.row()][index.column()]

    def appendRow(self, datarow):
        """ Append model row. """
        self.beginInsertRows(QtCore.QModelIndex(),
                             len(self.invlist), len(self.invlist))
        self.invlist.append(list(datarow))
        self.endInsertRows()

    def removeRow(self, index):
        """ Remove model row. """
        self.beginRemoveRows(QtCore.QModelIndex(), index.row(), index.row())
        del self.invlist[index.row()]
        self.endRemoveRows()

    def headerData(self, col, orientation, role=QtCore.Qt.DisplayRole):
        if orientation == QtCore.Qt.Horizontal & role == QtCore.Qt.DisplayRole:
            return self.header[col]
        return None

    def getData(self, index, what='ID'):
        return self.invlist[index.row()][self.header.index(what)]

    def getRow(self, index):
        return self.invlist[index.row()]


class UniModel(QtCore.QAbstractTableModel):
    def __init__(self, parent, *args):
        super(UniModel, self).__init__(parent, *args)
        self.unilist = []
        self.header = ['ID', 'Label', 'Begin', 'End', 'Data']

    def rowCount(self, parent=None):
        return len(self.unilist)

    def columnCount(self, parent=None):
        return len(self.header)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        elif role != QtCore.Qt.DisplayRole:
            return None
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

    def removeRow(self, index):
        """ Remove model row. """
        self.beginRemoveRows(QtCore.QModelIndex(), index.row(), index.row())
        del self.unilist[index.row()]
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

    def getData(self, index, what='ID'):
        return self.unilist[index.row()][self.header.index(what)]

    def getRow(self, index):
        return self.unilist[index.row()]


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
        if not r['output'].startswith('User-defined'):
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
    def __init__(self, label=True, parent=None):
        super(AddInv, self).__init__(parent)
        self.setupUi(self)
        # validator
        if not label:
            self.label.hide()
            self.labelEdit.hide()
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
        label = self.labelEdit.text()
        T = float(self.tEdit.text())
        p = float(self.pEdit.text())
        return (label, T, p)


class AddUni(QtWidgets.QDialog, Ui_AddUni):
    """Add uni dialog class
    """
    def __init__(self, items, parent=None):
        super(AddUni, self).__init__(parent)
        self.setupUi(self)
        self.combomodel = QtGui.QStandardItemModel()
        for item in items:
            it = QtGui.QStandardItem(str(item))
            it.setData(item, 1)
            self.combomodel.appendRow(it)
        self.comboBegin.setModel(self.combomodel)
        self.comboEnd.setModel(self.combomodel)

    def getValues(self):
        label = self.labelEdit.text()
        b = self.comboBegin.currentData(1)
        e = self.comboEnd.currentData(1)
        return (label, b, e)


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
