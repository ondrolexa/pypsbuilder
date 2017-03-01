#!/usr/bin/env python
"""
Visual pseudosection builder for THERMOCALC
"""
# author: Ondrej Lexa
# website: petrol.natur.cuni.cz/~ondro

from .utils import *

from pkg_resources import resource_filename

from PyQt5 import QtCore, QtGui, QtWidgets

import matplotlib
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar)

from .ui_psbuilder import Ui_PSBuilder
from .ui_addinv import Ui_AddInv
from .ui_adduni import Ui_AddUni
from .ui_uniguess import Ui_UniGuess

__version__ = '2.1.0devel'
# Make sure that we are using QT5
matplotlib.use('Qt5Agg')

matplotlib.rcParams['xtick.direction'] = 'out'
matplotlib.rcParams['ytick.direction'] = 'out'

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
        # self.actionExport_Drawpd.triggered.connect(self.gendrawpd)
        self.actionAbout.triggered.connect(self.about_dialog.exec)
        self.actionImport_project.triggered.connect(self.import_from_prj)
        # self.actionTest_topology.triggered.connect()
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
            #builder_settings.setValue("export_areas", self.checkAreas.checkState())
            #builder_settings.setValue("export_partial", self.checkPartial.checkState())
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
            #self.checkAreas.setCheckState(builder_settings.value("export_areas", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
            #self.checkPartial.setCheckState(builder_settings.value("export_partial", QtCore.Qt.Unchecked, type=QtCore.Qt.CheckState))
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
            self.tcexe = None
            for p in pathlib.Path(self.workdir).glob(tcpat):
                if p.is_file() and os.access(str(p), os.X_OK):
                    self.tcexe = p.name
                    break
            if not self.tcexe:
                errinfo = 'No THERMOCALC executable in working directory.'
                raise Exception()
            # DRAWPD exe
            self.drexe = None
            for p in pathlib.Path(self.workdir).glob(drpat):
                if p.is_file() and os.access(str(p), os.X_OK):
                    self.drexe = p.name
                    break
            if not self.drexe:
                errinfo = 'No drawpd executable in working directory.'
                raise Exception()
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
                     'setexcess': False, 'printxyz': False}
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
                    # elif kw[0] == 'drawpd':
                    #     errinfo = 'Wrong argument for drawpd keyword in scriptfile.'
                    #     if kw[1] == 'no':
                    #         errinfo = 'Drawpd must be set to yes.'
                    #         raise Exception()
                    #     check['drawpd'] = True
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
            # if not check['drawpd']:
            #     errinfo = 'Drawpd must be set to yes. To suppress this error put drawpd yes keyword to your scriptfile.'
            #     raise Exception()
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
            tcout = runprog(self.tc, self.workdir, '\nkill\n\n')
            self.logText.setPlainText('Working directory:{}\n\n'.format(self.workdir) + tcout)
            if 'BOMBED' in tcout:
                errinfo = tcout.split('BOMBED')[1].split('\n')[0]
                raise Exception()
            else:
                errinfo = 'Error parsing initial THERMOCALC output'
                self.phases = tcout.split('choose from:')[1].split('\n')[0].split()
                self.phases.sort()
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
            projfile = qd.getOpenFileName(self, 'Open project',
                                          os.path.expanduser('~'),
                                          'pypsbuilder project (*.psb)')[0]
        if os.path.exists(projfile):
            stream = gzip.open(projfile, 'rb')
            data = pickle.load(stream)
            stream.close()
            if data.get('version', '1.0.0') < '2.1.0':
                qb = QtWidgets.QMessageBox
                qb.critical(self, 'Old version',
                            'This project is created in older version.\nUse import from project.',
                            qb.Abort)
            else:
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
                    for row in data['unilist']:
                        self.unimodel.appendRow(row)
                    self.adapt_uniview()
                    for row in data['invlist']:
                        self.invmodel.appendRow(row)
                    self.invview.resizeColumnsToContents()
                    # cutting
                    for row in self.unimodel.unilist:
                        self.trimuni(row)
                    # update executables
                    if 'tcexe' in data:
                        p = pathlib.Path(self.workdir, data['tcexe'])
                        if p.is_file() and os.access(str(p), os.X_OK):
                            self.tcexe = p.name
                    if 'drexe' in data:
                        p = pathlib.Path(self.workdir, data['drexe'])
                        if p.is_file() and os.access(str(p), os.X_OK):
                            self.drexe = p.name
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

    def import_from_prj(self):
        if self.ready:
            qd = QtWidgets.QFileDialog
            projfile = qd.getOpenFileName(self, 'Import from project', self.workdir,
                                          'pypsbuilder project (*.psb)')[0]
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
                    # Import
                    for row in data['invlist']:
                        r = dict(phases=row[2]['phases'], out=row[2]['out'],
                                 cmd=row[2].get('cmd', ''), variance=-1,
                                 p=row[2]['p'], T=row[2]['T'], manual=True,
                                 output='Imported invariant point.')
                        label = self.format_label(row[2]['phases'], row[2]['out'])
                        self.invmodel.appendRow((row[0], label, r))
                    self.invview.resizeColumnsToContents()
                    for row in data['unilist']:
                        r = dict(phases=row[4]['phases'], out=row[4]['out'],
                                 cmd=row[4].get('cmd', ''), variance=-1,
                                 p=row[4]['p'], T=row[4]['T'], manual=True,
                                 output='Imported univariant line.')
                        label = self.format_label(row[4]['phases'], row[4]['out'])
                        self.unimodel.appendRow((row[0], label, row[2], row[3], r))
                    self.adapt_uniview()
                    # try to recalc
                    for row in data['invlist']:
                        if 'cmd' in row[2]:
                            tcout = runprog(self.tc, self.workdir, row[2]['cmd'])
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
                    self.invview.resizeColumnsToContents()
                    for row in data['unilist']:
                        if 'cmd' in row[4]:
                            tcout = runprog(self.tc, self.workdir, row[4]['cmd'])
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
                    self.adapt_uniview()
                    # cutting
                    for row in self.unimodel.unilist:
                        self.trimuni(row)
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
                    'tcexe': self.tcexe,
                    'drexe': self.drexe,
                    'tcversion': self.tcversion,
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

    def reparse_outouts(self):
        for row in data['invlist']:
            status, variance, pts, res, output = parse_logfile(self.logfile, out=row[2]['output'])
            if status == 'ok':
                r = dict(phases=row[2]['phases'], out=row[2]['out'], cmd=row[2]['cmd'],
                         variance=variance, p=pts[0], T=pts[1], manual=False,
                         output=output, results=res)
                label = self.format_label(row[2]['phases'], row[2]['out'])
                isnew, id = self.getidinv(r)
                urow = self.invmodel.getRowFromId(id)
                urow[1] = label
                urow[2] = r
        self.invview.resizeColumnsToContents()
        for row in data['unilist']:
            status, variance, pts, res, output = parse_logfile(self.logfile, out=row[4]['output'])
            if status == 'ok':
                r = dict(phases=row[4]['phases'], out=row[4]['out'], cmd=row[4]['cmd'],
                         variance=variance, p=pts[0], T=pts[1], manual=False,
                         output=output, results=res)
                label = self.format_label(row[4]['phases'], row[4]['out'])
                isnew, id = self.getiduni(r)
                urow = self.unimodel.getRowFromId(id)
                urow[1] = label
                urow[4] = r
        self.adapt_uniview()
        self.statusBar().showMessage('Outputs re-parsed.')
        self.changed = True

    def generate(self):
        if self.ready:
            qd = QtWidgets.QFileDialog
            tpfile = qd.getOpenFileName(self, 'Open text file', self.workdir,
                                        'Text files (*.txt);;All files (*.*)')[0]
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
    def logfile(self):
        return os.path.join(self.workdir, 'tc-log.txt')

    # @property
    # def drawpdfile(self):
    #     return os.path.join(self.workdir, 'dr-' + self.bname + '.txt')

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
                lbl = ['p = {}, T = {}'.format(p, T) for p, T in zip(r['p'], r['T'])]
                uniguess = UniGuess(lbl, self)
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
            # clear navigation toolbar history
            self.toolbar.update()
            # self.plot()
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
                # clear navigation toolbar history
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
            # prec = self.spinPrec.value()
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
                tcout = runprog(self.tc, self.workdir, ans)
                self.logText.setPlainText('Working directory:{}\n\n'.format(self.workdir) + tcout)
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
                        # self.unisel.select(idx, QtCore.QItemSelectionModel.ClearAndSelect | QtCore.QItemSelectionModel.Rows)
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
                tcout = runprog(self.tc, self.workdir, ans)
                self.logText.setPlainText('Working directory:{}\n\n'.format(self.workdir) + tcout)
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
                               bbox=dict(facecolor='cyan', alpha=lalfa, pad=2))
            invlabel_kw = dict(ha='center', va='center', size='small',
                               bbox=dict(facecolor='yellow', alpha=lalfa, pad=2))
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
