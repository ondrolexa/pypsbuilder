#!/usr/bin/env python
"""
Visual pseudosection builder for THERMOCALC
"""
# author: Ondrej Lexa
# website: petrol.natur.cuni.cz/~ondro
# last edited: February 2016

import sys
import os
import pickle
import gzip
import subprocess
import threading
import pkg_resources

from PyQt5 import QtCore, QtGui, QtWidgets

import numpy as np
import matplotlib

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar)

from builder import Ui_PSBuilder
from addinv import Ui_AddInv
from adduni import Ui_AddUni

__version__ = '2.0.1'
# Make sure that we are using QT5
matplotlib.use('Qt5Agg')

matplotlib.rcParams['xtick.direction'] = 'out'
matplotlib.rcParams['ytick.direction'] = 'out'

popenkw = dict(stdout=subprocess.PIPE, stdin=subprocess.PIPE,
               stderr=subprocess.STDOUT, universal_newlines=False)
TCenc = 'latin1'


class PSBuilder(QtWidgets.QMainWindow, Ui_PSBuilder):
    """Main class
    """
    def __init__(self, parent=None):
        super(PSBuilder, self).__init__(parent)
        self.setupUi(self)
        self.resize(1024, 768)
        self.setWindowTitle('PSBuilder')
        window_icon = pkg_resources.resource_filename('images',
                                                      'pypsbuilder.png')
        self.setWindowIcon(QtGui.QIcon(window_icon))
        self.__changed = False
        self.about_dialog = AboutDialog()

        # Create figure
        self.figure = Figure(facecolor='white')
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setParent(self.tabPlot)
        self.canvas.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.mplvl.addWidget(self.canvas)
        self.toolbar = NavigationToolbar(self.canvas, self.tabPlot,
                                         coordinates=False)
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

        self.initViewModels()

        # CONNECT SIGNALS
        self.actionNew.triggered.connect(self.initProject)
        self.actionOpen.triggered.connect(self.openProject)
        self.actionSave.triggered.connect(self.saveProject)
        self.actionQuit.triggered.connect(self.close)
        self.actionAbout.triggered.connect(lambda: self.about_dialog.exec_())
        self.pushCalcTatP.clicked.connect(lambda: self.do_calc(True))
        self.pushCalcPatT.clicked.connect(lambda: self.do_calc(False))
        self.pushApplySettings.clicked.connect(lambda: self.apply_setting(5))
        self.pushResetSettings.clicked.connect(lambda: self.apply_setting(8))
        self.pushFromAxes.clicked.connect(lambda: self.apply_setting(2))
        self.tabMain.currentChanged.connect(lambda: self.apply_setting(4))
        self.pushReadScript.clicked.connect(self.read_scriptfile)
        self.pushSaveScript.clicked.connect(self.save_scriptfile)
        self.actionReload.triggered.connect(self.reinitialize)
        self.pushUnselectUni.clicked.connect(self.unisel_clear)
        self.pushUnselectInv.clicked.connect(self.invsel_clear)
        self.pushInvAdd.toggled.connect(self.addudinv)
        self.pushInvAdd.setCheckable(True)
        self.pushUniAdd.clicked.connect(self.adduduni)
        self.pushInvRemove.clicked.connect(self.remove_inv)
        self.pushUniRemove.clicked.connect(self.remove_uni)

        self.uniview.doubleClicked.connect(self.show_uni)
        self.invview.doubleClicked.connect(self.show_inv)

        self.app_settings()
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
        self.invsel.selectionChanged.connect(self.invsel_changed)
        # default unconnected ghost
        self.invmodel.appendRow([0, 'Unconnected', {}])
        self.invview.setRowHidden(0, True)

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
        # signal
        self.unimodel.dataChanged.connect(self.plot)
        self.unisel = self.uniview.selectionModel()
        self.unisel.selectionChanged.connect(self.unisel_changed)

    def app_settings(self, write=False):
        # Applicatiom settings
        builder_settings = QtCore.QSettings('LX', 'pypsbuilder')
        if write:
            builder_settings.setValue("steps", self.spinSteps.value())
            builder_settings.setValue("precision", self.spinPrec.value())
            builder_settings.setValue("label_uni", self.checkLabelUni.checkState())
            builder_settings.setValue("label_inv", self.checkLabelInv.checkState())
            builder_settings.setValue("label_usenames", self.checkLabels.checkState())
        else:
            self.spinSteps.setValue(builder_settings.value("steps", 50, type=int))
            self.spinPrec.setValue(builder_settings.value("precision", 1, type=int))
            self.checkLabelUni.setCheckState(builder_settings.value("label_uni", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.checkLabelInv.setCheckState(builder_settings.value("label_inv", QtCore.Qt.Checked, type=QtCore.Qt.CheckState))
            self.checkLabels.setCheckState(builder_settings.value("label_usenames", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState)) 

    def initProject(self):
        """Open working directory and initialize project
        """
        workdir = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Directory",
                                                   os.path.expanduser('~'),
                                                   QtWidgets.QFileDialog.ShowDirsOnly)
        if workdir:
            self.workdir = workdir
            # init THERMOCALC
            self.doInit()
            # init UI
            self.outText.clear()
            self.logText.clear()
            self.initViewModels()
            # all done
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
            self.update_exe()
            if not os.path.exists(os.path.join(self.workdir, 'tc-prefs.txt')):
                self.errinfo = 'No tc-prefs.txt file in working directory.'
                raise Exception()
            for line in open(os.path.join(self.workdir, 'tc-prefs.txt'), 'r'):
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
            for line in open(self.scriptfile, 'r'):
                kw = line.split()
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
            self.logText.setPlainText(tcout)
        except BaseException as e:
                QtWidgets.QMessageBox.critical(self, 'Error!', self.errinfo,
                                               QtWidgets.QMessageBox.Abort)

    def openProject(self):
        """Open working directory and initialize project
        """
        projfile = QtWidgets.QFileDialog.getOpenFileName(self, 'Open project', os.path.expanduser('~'), 'pypsbuilder project (*.psb)')[0]
        if projfile:
            if not projfile.lower().endswith('.psb'):
                projfile = projfile + '.psb'
            stream = gzip.open(projfile, 'rb')
            data = pickle.load(stream)
            stream.close()
            # set actual working dir in case folder was moved
            self.workdir = os.path.dirname(projfile)
            self.doInit()
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
            self.initViewModels()
            for row in data['unilist']:
                self.unimodel.appendRow(row)
            self.uniview.resizeColumnsToContents()
            for row in data['invlist']:
                self.invmodel.appendRow(row)
            self.invview.resizeColumnsToContents()
            # all done
            self.ready = True
            self.project = projfile
            self.changed = False
            # read scriptfile
            self.read_scriptfile()
            # update settings tab
            self.apply_setting(4)
            # update plot
            self.plot()
            self.statusBar().showMessage('Project loaded.')

    def saveProject(self):
        """Open working directory and initialize project
        """
        if self.ready:
            if self.project is None:
                projfile = QtWidgets.QFileDialog.getSaveFileName(self, 'Save current project', self.workdir, 'pypsbuilder project (*.psb)')[0]
                if projfile:
                    if not projfile.lower().endswith('.psb'):
                        projfile = projfile + '.psb'
                    self.project = projfile
            if self.project is not None:
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
                self.statusBar().showMessage('Project saved.')

    def update_exe(self):
        if sys.platform.startswith('win'):
            self.tcexe = 'tc340.exe'
            self.drexe = 'dr116.exe'
        elif sys.platform.startswith('linux'):
            self.tcexe = 'tc340L'
            self.drexe = 'dr115L'
        elif sys.platform.startswith('darwin'):
            self.tcexe = 'tc340'
            self.drexe = 'dr116'
        else:
            self.errinfo = 'Running on unknown platform'
            raise Exception()

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
        return output

    def initFromTC(self):
        tcout = self.runprog(self.tc, '\nkill\n\n')
        self.phases = tcout.split('choose from:')[1].split('\n')[0].split()
        self.phases.sort()
        self.vre = int(tcout.split('variance of required equilibrium ')[1].split('\n')[0].split('(')[1].split('?')[0])
        self.deftrange = self.trange
        self.defprange = self.prange
        self.errinfo = ''
        return tcout

    @property
    def tc(self):
        return os.path.join(self.workdir, self.tcexe)

    @property
    def dr(self):
        return os.path.join(self.workdir, self.drexe)

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
    def axfile(self):
        return os.path.join(self.workdir,'tc-' + self.axname + '.txt')

    @property
    def changed(self):
        return self.__changed

    @changed.setter
    def changed(self, status):
        self.__changed = status
        if self.project is None:
            title = 'PSbuilder - New project'
        else:
            title = 'PSbuilder - {}'.format(os.path.basename(self.project))
        if status:
            title += '*'
        self.setWindowTitle(title)

    def reinitialize(self):
        if self.ready:
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
            trange = self.trange
            prange = self.prange
            self.doInit()
            # select phases
            for i in range(self.phasemodel.rowCount()):
                item = self.phasemodel.item(i)
                if item.text() in selphases:
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

    def unisel_changed(self, item=QtCore.QItemSelection, olditem=QtCore.QItemSelection):
        idx = self.unisel.selectedIndexes()
        if idx:
            r = self.unimodel.data(idx[4])
            self.unihigh.set_visible(True)
            self.unihigh.set_data(r['T'], r['p'])
            self.canvas.draw()

    def unisel_clear(self):
        if self.ready:
            self.unisel.clearSelection()
            self.unihigh.set_visible(False)
            self.canvas.draw()

    def invsel_changed(self, item=QtCore.QItemSelection, olditem=QtCore.QItemSelection):
        idx = self.invsel.selectedIndexes()
        if idx:
            pass # HIGHLIFT INV

    def invsel_clear(self):
        if self.ready:
            self.invsel.clearSelection()

    def show_uni(self, index):
        r = self.unimodel.unilist[index.row()][4]
        self.outText.setPlainText(r['output'])

    def show_inv(self, index):
        r = self.invmodel.invlist[index.row()][2]
        self.outText.setPlainText(r['output'])

    def remove_inv(self):
        if self.invsel.hasSelection():
            idx = self.invsel.selectedIndexes()
            msg = '{}\nAre you sure?'.format(self.invmodel.data(idx[1]))
            reply = QtWidgets.QMessageBox.question(self, 'Remove invariant point', msg,
                                                   QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No)
            if reply == QtWidgets.QMessageBox.Yes:
                # Check unilines begins and ends
                for row in self.unimodel.unilist:
                    if row[2] == idx[0].row():
                        row[2] = 0
                    if row[3] == idx[0].row():
                        row[3] = 0
                self.invmodel.removeRow(idx[0])

    def remove_uni(self):
        if self.unisel.hasSelection():
            idx = self.unisel.selectedIndexes()
            msg = '{}\nAre you sure?'.format(self.unimodel.data(idx[1]))
            reply = QtWidgets.QMessageBox.question(self, 'Remove univariant line', msg,
                                                   QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No)
            if reply == QtWidgets.QMessageBox.Yes:
                self.unimodel.removeRow(idx[0])

    def clicker(self, event):
        if event.inaxes is not None:
            addinv = AddInv(self)
            addinv.set_from_event(event)
            respond = addinv.exec()
            if respond == QtWidgets.QDialog.Accepted:
                label, T, p = addinv.getValues()
                zm = {'T': np.array([T]), 'p': np.array([p]),
                      'output': 'User-defined invariant point.'}
                id = self.getidinv()
                self.invmodel.appendRow((id, label, zm))
                self.invview.resizeColumnsToContents()
                self.plot()
                self.statusBar().showMessage('User-defined invariant point added.')
            self.pushInvAdd.setChecked(False)

    def addudinv(self, checked=True):
        if self.ready:
            if checked:
                # cancle zoom and pan action on toolbar
                if self.toolbar._active == "PAN":
                    self.toolbar.pan()
                elif self.toolbar._active == "ZOOM":
                    self.toolbar.zoom()
                self.cid = self.canvas.mpl_connect('button_press_event', self.clicker)
                self.tabMain.setCurrentIndex(0)
            else:
                self.canvas.mpl_disconnect(self.cid)

    def adduduni(self):
        if self.ready:
            adduni = AddUni(self.invmodel, self)
            respond = adduni.exec()
            if respond == QtWidgets.QDialog.Accepted:
                label, b, e = adduni.getValues()
                if b and e:
                    zm = {'T': np.array([]), 'p': np.array([]),
                          'output': 'User-defined univariant line.'}
                    id = self.getiduni()
                    self.unimodel.appendRow((id, label, b, e, zm))
                    self.uniview.resizeColumnsToContents()
                    self.plot()
                    self.statusBar().showMessage('User-defined univariant line.')
                else:
                    msg = 'You must provide begin and end.'
                    QtWidgets.QMessageBox.critical(self, 'Error!', msg,
                                                   QtWidgets.QMessageBox.Abort)

    def read_scriptfile(self):
        if self.ready:
            with open(self.scriptfile, 'r', encoding=TCenc) as f:
                self.outScript.setPlainText(f.read())

    def save_scriptfile(self):
        if self.ready:
            with open(self.scriptfile, 'w', encoding=TCenc) as f:
                f.write(self.outScript.toPlainText())

    def closeEvent(self, event):
        """Catch exit of app.
        """
        self.app_settings(write=True)
        if self.changed:
            quit_msg = 'Project {} have been changed. Save ?'.format(self.project)
            reply = QtWidgets.QMessageBox.question(self, 'Message', quit_msg,
                                                   QtWidgets.QMessageBox.Cancel | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Save,
                                                   QtWidgets.QMessageBox.Save)

            if reply == QtWidgets.QMessageBox.Save:
                self.saveProject()
                if self.project is not None:
                    event.accept()
                else:
                    event.ignore()
            elif reply == QtWidgets.QMessageBox.Discard:
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

    def move_progress(self):
        nv = (self.progressBar.value() + 10) % 100
        self.progressBar.setValue(nv)

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

    def do_calc(self, cT):
        if self.ready:
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
            progress = RotatingProgress(0.25, self.move_progress)
            progress.start()
            ###########
            trange = self.ax.get_xlim()
            prange = self.ax.get_ylim()
            steps = self.spinSteps.value()
            prec = self.spinPrec.value()
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
                self.logText.setPlainText(tcout)
                typ, isnew, id, label, b, e, r = self.parsedrfile()
                if typ == 'uni':
                    if len(r['T']) > 0:
                        if isnew:
                            self.unimodel.appendRow((id, label, b, e, r))
                            self.uniview.openPersistentEditor(self.unimodel.index(self.unimodel.rowCount(), 2, QtCore.QModelIndex()))
                            self.uniview.openPersistentEditor(self.unimodel.index(self.unimodel.rowCount(), 3, QtCore.QModelIndex()))
                            self.uniview.resizeColumnsToContents()
                        else:
                            for row in self.unimodel.unilist:
                                if row[1] == label:
                                    row[4] = r
                        self.statusBar().showMessage('Univariant line calculated.')
                        self.changed = True
                        self.plot()
                    else:
                        self.statusBar().showMessage('Nothing in range.')
            elif len(out) == 2:
                tmpl = '{}\n\n{}\n{:.{prec}f} {:.{prec}f} {:.{prec}f} {:.{prec}f}\nn\n\nkill\n\n'
                ans = tmpl.format(' '.join(phases), ' '.join(out), *trange, *prange, prec=prec)
                tcout = self.runprog(self.tc, ans)
                self.logText.setPlainText(tcout)
                typ, isnew, id, label, b, e, r = self.parsedrfile()
                if typ == 'inv':
                    if len(r['T']) > 0:
                        if isnew:
                            self.invmodel.appendRow((id, label, r))
                            self.invview.resizeColumnsToContents()
                        else:
                            for row in self.invmodel.invlist[1:]:
                                if row[1] == label:
                                    row[2] = r
                        self.statusBar().showMessage('Invariant point calculated.')
                        self.changed = True
                        self.plot()
                    else:
                        self.statusBar().showMessage('Nothing in range.')
            else:
                self.statusBar().showMessage('{} zero mode phases selected. Select one or two!'.format(len(out.split())))
            #########
            progress.cancel()
            self.progressBar.setValue(0)

    def parsedrfile(self):
        """Parse intermediate drfile
        """
        dr = []
        # for line in open(self.drfile, 'rb'):
        with open(self.drfile, 'r', encoding=TCenc) as drfile:
            for line in drfile:
                n = line.split('%')[0].strip()
                if n != '':
                    dr.append(n)

        typ = ''
        label = ''
        zm = {}
        isnew = True
        b = 0
        e = 0
        if len(dr) > 0:
            label = ' '.join(dr[0].split()[1:])
            with open(self.ofile, 'r', encoding=TCenc) as ofile:
                output = ofile.read()
            if dr[0].split()[0] == 'u<k>':
                typ = 'uni'
                id = self.getiduni()
                data = dr[2:]
                for r in self.unimodel.unilist:
                    if label == r[1]:
                        b = r[2]
                        e = r[3]
                        id = r[0]
                        isnew = False
            elif dr[0].split()[0] == 'i<k>':
                typ = 'inv'
                id = self.getidinv()
                data = dr[1:]
                for r in self.invmodel.invlist[1:]:
                    if label == r[1]:
                        id = r[0]
                        isnew = False
            else:
                self.errinfo = 'Unknown format of dr file.'
                raise Exception()
            pts = np.array([float(v) for v in ' '.join(data).split()])
            zm['p'] = pts[0::2]
            zm['T'] = pts[1::2]
            zm['output'] = output
        return typ, isnew, id, label, b, e, zm

    def gendrawpd(self, exedrawpd):
        with open(self.drawpdfile, 'w', encoding=TCenc) as output:
            output.write('% Generated by PyPSbuilder (c) Ondrej Lexa 2016\n')
            output.write('2    % no. of variables in each line of data, in this case P, T\n')
            ex = self.excess[:]
            ex.insert(0,'')
            output.write(('%s    %% effective size of the system: ' + self.axname + ' +'.join(ex) + '\n') % (self.nc - len(self.excess)))
            output.write('2 1  %% which columns to be x,y in phase diagram\n')
            output.write('\n')
            output.write('% Points\n')
            for i in self.invmodel.invlist:
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
                if u[4]['output'] == 'User-defined univariant line.':
                    output.write(b1 + ' ' + b2 + 'connect\n')
                    output.write('\n')
                else:
                    output.write(b1 + ' ' + b2 + '\n')
                    output.write('\n')
                    for p, t in zip(u[4]['p'], u[4]['T']):
                        output.write('%s %s\n' % (p, t))
                    output.write('\n')
            output.write('*\n')
            output.write('% ----------------------------------------------\n')
            output.write('\n')
            output.write('% Areas\n')
            output.write('\n')
            output.write('*\n')
            output.write('\n')
            output.write('window %s %s %s %s       %% T,P window\n' % (self.trange + self.prange))
            output.write('\n')
            output.write('bigticks 50 %s 1 %s\n' % (int(100*np.round(self.trange[0]/100)), int(np.round(self.prange[0]))))
            output.write('\n')
            output.write('smallticks 10 0.1\n')
            output.write('\n')
            output.write('numbering yes\n')
            output.write('\n')
            output.write('*\n')

        if exedrawpd:
            try:
                self.runprog(self.dr, self.bname + '\n')
            except OSError:
                pass

    def getiduni(self):
        ids = [r[0] for r in self.unimodel.unilist]
        if ids == []:
            res = 1
        else:
            res = max(ids) + 1
        return res

    def getidinv(self):
        ids = [r[0] for r in self.invmodel.invlist[1:]]
        if ids == []:
            res = 1
        else:
            res = max(ids) + 1
        return res

    def getunicutted(self, r, b, e):
        T = r['T'].copy()
        p = r['p'].copy()
        invids = [r[0] for r in self.invmodel.invlist]
        if len(T) and len(p):
            # trim/extend begin
            s1, T1, p1 = 0, [], []
            if b != 0:
                inv = invids.index(b)
                T1 = self.invmodel.invlist[inv][2]['T'][0]
                p1 = self.invmodel.invlist[inv][2]['p'][0]
                if len(T) > 0:
                    dst = [np.sqrt((T1 - x) ** 2 + (p1 - y) ** 2) for x, y in zip(T, p)]
                    ix = np.array(dst).argmin()
                    if ix < len(T) - 1:
                        u = self.segmentpos(T1, p1,
                                            T[ix], p[ix],
                                            T[ix + 1], p[ix + 1])
                        if u > 0:
                            s1 = ix + 1
                        else:
                            s1 = ix
                    else:
                        s1, T1, p1 = 0, [], []
            # trim/extend end
            s2, T2, p2 = len(T), [], []
            if e != 0:
                inv = invids.index(e)
                T2 = self.invmodel.invlist[inv][2]['T'][0]
                p2 = self.invmodel.invlist[inv][2]['p'][0]
                if len(T) > 0:
                    dst = [np.sqrt((T2 - x) ** 2 + (p2 - y) ** 2) for x, y in zip(T, p)]
                    ix = np.array(dst).argmin()
                    if ix > 0:
                        u = self.segmentpos(T2, p2,
                                            T[ix], p[ix],
                                            T[ix - 1], p[ix - 1])
                        if u > 0:
                            s2 = ix
                        else:
                            s2 = ix - 1
                    else:
                        s2, T2, p2 = len(T), [], []
        else:
            inv = invids.index(b)
            T1 = self.invmodel.invlist[inv][2]['T'][0]
            p1 = self.invmodel.invlist[inv][2]['p'][0]
            inv = invids.index(e)
            T2 = self.invmodel.invlist[inv][2]['T'][0]
            p2 = self.invmodel.invlist[inv][2]['p'][0]
            T = [(T1 + T2) / 2]
            p = [(p1 + p2) / 2]
            s1, s2 = 0, 1

        return np.hstack((T1, T[s1:s2], T2)), np.hstack((p1, p[s1:s2], p2))

    def segmentpos(self, px, py, x1, y1, x2, y2):
        ll = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
        u1 = ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1))
        u = u1 / ll
        return u

    def plot(self):
        if self.ready:
            unilabel_kw = dict(ha='center', va='center', size='small',
                               bbox=dict(facecolor='cyan', alpha=0.5, pad=4))
            invlabel_kw = dict(ha='center', va='center', size='small',
                               bbox=dict(facecolor='yellow', alpha=0.5, pad=4))
            unihigh_kw = dict(lw=3, alpha=0.6, marker='o', ms=4, color='red')
            if self.figure.axes == []:
                cur = None
            else:
                cur = (self.ax.get_xlim(), self.ax.get_ylim())
            self.ax = self.figure.add_subplot(111)
            self.ax.cla()
            for k in self.unimodel.unilist:
                T, p = self.getunicutted(k[4], k[2], k[3])
                self.ax.plot(T, p, 'k')
                if self.checkLabelUni.isChecked():
                    if self.checkLabels.isChecked():
                        self.ax.text(T[len(T) // 2], p[len(p) // 2], k[1],
                                     **unilabel_kw)
                    else:
                        self.ax.text(T[len(T) // 2], p[len(p) // 2], str(k[0]),
                                     **unilabel_kw)
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
            self.unihigh, = self.ax.plot([0], [0], '-', visible=False,
                                         **unihigh_kw)
            if cur is None:
                self.ax.set_xlim(self.trange)
                self.ax.set_ylim(self.prange)
            else:
                self.ax.set_xlim(cur[0])
                self.ax.set_ylim(cur[1])
            self.unisel_changed()
            self.invsel_changed()
            self.canvas.draw()


class RotatingProgress():
    """Threading class to visualize progress
    """
    def __init__(self, t, hFunction):
        self.t = t
        self.hFunction = hFunction
        self.thread = threading.Timer(self.t, self.handle_function)

    def handle_function(self):
        self.hFunction()
        self.thread = threading.Timer(self.t, self.handle_function)
        self.thread.start()

    def start(self):
        self.thread.start()

    def cancel(self):
        self.thread.cancel()


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


class UniModel(QtCore.QAbstractTableModel):
    def __init__(self, parent, *args):
        super(UniModel, self).__init__(parent, *args)
        self.unilist = []
        self.header = ['ID', 'Label', 'Begin', ' End ', 'Data']

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


class ComboDelegate(QtWidgets.QItemDelegate):
    """
    A delegate that places a fully functioning QtWidgets.QComboBox in every
    cell of the column to which it's applied
    """
    def __init__(self, parent, combomodel):
        super(ComboDelegate, self).__init__(parent)
        self.combomodel = combomodel

    def createEditor(self, parent, option, index):
        combo = QtWidgets.QComboBox(parent)
        combo.setModel(self.combomodel)
        combo.setModelColumn(0)
        return combo

    def setEditorData(self, editor, index):
        editor.setCurrentIndex(index.model().data(index))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentIndex())


class AddInv(QtWidgets.QDialog, Ui_AddInv):
    """Add inv dialog class
    """
    def __init__(self, parent=None):
        super(AddInv, self).__init__(parent)
        self.setupUi(self)
        # validator
        validator = QtGui.QDoubleValidator()
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
    def __init__(self, combomodel, parent=None):
        super(AddUni, self).__init__(parent)
        self.setupUi(self)
        self.combomodel = combomodel
        self.comboBegin.setModel(self.combomodel)
        self.comboBegin.setModelColumn(0)
        self.comboEnd.setModel(self.combomodel)
        self.comboEnd.setModelColumn(0)

    def getValues(self):
        label = self.labelEdit.text()
        b = self.comboBegin.currentIndex()
        e = self.comboEnd.currentIndex()
        return (label, b, e)


class AboutDialog(QtWidgets.QDialog):
    """About dialog
    """
    def __init__(self, parent=None):
        """Display a dialog that shows application information."""
        super(AboutDialog, self).__init__(parent)

        self.setWindowTitle('About')
        self.resize(300, 100)

        about = QtWidgets.QLabel('PSbuilder\nsimplistic THERMOCALC front-end for constructing PT pseudosections')
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

