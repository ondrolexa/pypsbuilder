# Form implementation generated from reading ui file 'adduni.ui'
#
# Created by: PyQt6 UI code generator 6.8.0
#
# WARNING: Any manual changes made to this file will be lost when pyuic6 is
# run again.  Do not edit this file unless you know what you are doing.


from qtpy import QtCore, QtGui, QtWidgets


class Ui_AddUni(object):
    def setupUi(self, AddUni):
        AddUni.setObjectName("AddUni")
        AddUni.resize(300, 100)
        self.verticalLayout = QtWidgets.QVBoxLayout(AddUni)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.label = QtWidgets.QLabel(parent=AddUni)
        self.label.setObjectName("label")
        self.horizontalLayout_2.addWidget(self.label)
        self.labelEdit = QtWidgets.QLineEdit(parent=AddUni)
        self.labelEdit.setReadOnly(True)
        self.labelEdit.setObjectName("labelEdit")
        self.horizontalLayout_2.addWidget(self.labelEdit)
        self.verticalLayout.addLayout(self.horizontalLayout_2)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label_2 = QtWidgets.QLabel(parent=AddUni)
        self.label_2.setObjectName("label_2")
        self.horizontalLayout.addWidget(self.label_2)
        self.comboBegin = QtWidgets.QComboBox(parent=AddUni)
        self.comboBegin.setObjectName("comboBegin")
        self.horizontalLayout.addWidget(self.comboBegin)
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        self.horizontalLayout.addItem(spacerItem)
        self.label_3 = QtWidgets.QLabel(parent=AddUni)
        self.label_3.setObjectName("label_3")
        self.horizontalLayout.addWidget(self.label_3)
        self.comboEnd = QtWidgets.QComboBox(parent=AddUni)
        self.comboEnd.setObjectName("comboEnd")
        self.horizontalLayout.addWidget(self.comboEnd)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.buttonBox = QtWidgets.QDialogButtonBox(parent=AddUni)
        self.buttonBox.setOrientation(QtCore.Qt.Orientation.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.StandardButton.Cancel|QtWidgets.QDialogButtonBox.StandardButton.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(AddUni)
        self.buttonBox.accepted.connect(AddUni.accept) # type: ignore
        self.buttonBox.rejected.connect(AddUni.reject) # type: ignore
        QtCore.QMetaObject.connectSlotsByName(AddUni)

    def retranslateUi(self, AddUni):
        _translate = QtCore.QCoreApplication.translate
        AddUni.setWindowTitle(_translate("AddUni", "Add univariant line"))
        self.label.setText(_translate("AddUni", "Label"))
        self.label_2.setText(_translate("AddUni", "Begin:"))
        self.label_3.setText(_translate("AddUni", "End:"))
