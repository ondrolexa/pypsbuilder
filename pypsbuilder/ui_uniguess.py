# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'uniguess.ui'
#
# Created by: PyQt5 UI code generator 5.9.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_UniGuess(object):
    def setupUi(self, UniGuess):
        UniGuess.setObjectName("UniGuess")
        UniGuess.resize(242, 77)
        self.verticalLayout = QtWidgets.QVBoxLayout(UniGuess)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label_2 = QtWidgets.QLabel(UniGuess)
        self.label_2.setObjectName("label_2")
        self.horizontalLayout.addWidget(self.label_2)
        self.comboPoint = QtWidgets.QComboBox(UniGuess)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.comboPoint.sizePolicy().hasHeightForWidth())
        self.comboPoint.setSizePolicy(sizePolicy)
        self.comboPoint.setObjectName("comboPoint")
        self.horizontalLayout.addWidget(self.comboPoint)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.buttonBox = QtWidgets.QDialogButtonBox(UniGuess)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(UniGuess)
        self.buttonBox.accepted.connect(UniGuess.accept)
        self.buttonBox.rejected.connect(UniGuess.reject)
        QtCore.QMetaObject.connectSlotsByName(UniGuess)

    def retranslateUi(self, UniGuess):
        _translate = QtCore.QCoreApplication.translate
        UniGuess.setWindowTitle(_translate("UniGuess", "Select point for guesses"))
        self.label_2.setText(_translate("UniGuess", "Choose p,T"))

