# Form implementation generated from reading ui file 'uniguess.ui'
#
# Created by: PyQt6 UI code generator 6.8.0
#
# WARNING: Any manual changes made to this file will be lost when pyuic6 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt6 import QtCore, QtGui, QtWidgets


class Ui_UniGuess(object):
    def setupUi(self, UniGuess):
        UniGuess.setObjectName("UniGuess")
        UniGuess.resize(242, 77)
        self.verticalLayout = QtWidgets.QVBoxLayout(UniGuess)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label_2 = QtWidgets.QLabel(parent=UniGuess)
        self.label_2.setObjectName("label_2")
        self.horizontalLayout.addWidget(self.label_2)
        self.comboPoint = QtWidgets.QComboBox(parent=UniGuess)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.comboPoint.sizePolicy().hasHeightForWidth())
        self.comboPoint.setSizePolicy(sizePolicy)
        self.comboPoint.setObjectName("comboPoint")
        self.horizontalLayout.addWidget(self.comboPoint)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.buttonBox = QtWidgets.QDialogButtonBox(parent=UniGuess)
        self.buttonBox.setOrientation(QtCore.Qt.Orientation.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.StandardButton.Cancel|QtWidgets.QDialogButtonBox.StandardButton.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(UniGuess)
        self.buttonBox.accepted.connect(UniGuess.accept) # type: ignore
        self.buttonBox.rejected.connect(UniGuess.reject) # type: ignore
        QtCore.QMetaObject.connectSlotsByName(UniGuess)

    def retranslateUi(self, UniGuess):
        _translate = QtCore.QCoreApplication.translate
        UniGuess.setWindowTitle(_translate("UniGuess", "Select point for guesses"))
        self.label_2.setText(_translate("UniGuess", "Choose p,T"))
