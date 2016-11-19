# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'addinv.ui'
#
# Created by: PyQt5 UI code generator 5.6
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_AddInv(object):
    def setupUi(self, AddInv):
        AddInv.setObjectName("AddInv")
        AddInv.resize(300, 100)
        self.verticalLayout = QtWidgets.QVBoxLayout(AddInv)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.label = QtWidgets.QLabel(AddInv)
        self.label.setObjectName("label")
        self.horizontalLayout_2.addWidget(self.label)
        self.labelEdit = QtWidgets.QLineEdit(AddInv)
        self.labelEdit.setObjectName("labelEdit")
        self.horizontalLayout_2.addWidget(self.labelEdit)
        self.verticalLayout.addLayout(self.horizontalLayout_2)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label_2 = QtWidgets.QLabel(AddInv)
        self.label_2.setObjectName("label_2")
        self.horizontalLayout.addWidget(self.label_2)
        self.tEdit = QtWidgets.QLineEdit(AddInv)
        self.tEdit.setObjectName("tEdit")
        self.horizontalLayout.addWidget(self.tEdit)
        self.label_3 = QtWidgets.QLabel(AddInv)
        self.label_3.setObjectName("label_3")
        self.horizontalLayout.addWidget(self.label_3)
        self.pEdit = QtWidgets.QLineEdit(AddInv)
        self.pEdit.setObjectName("pEdit")
        self.horizontalLayout.addWidget(self.pEdit)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.buttonBox = QtWidgets.QDialogButtonBox(AddInv)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(AddInv)
        self.buttonBox.accepted.connect(AddInv.accept)
        self.buttonBox.rejected.connect(AddInv.reject)
        QtCore.QMetaObject.connectSlotsByName(AddInv)

    def retranslateUi(self, AddInv):
        _translate = QtCore.QCoreApplication.translate
        AddInv.setWindowTitle(_translate("AddInv", "Add invariant point"))
        self.label.setText(_translate("AddInv", "Label"))
        self.label_2.setText(_translate("AddInv", "T:"))
        self.label_3.setText(_translate("AddInv", "p:"))

