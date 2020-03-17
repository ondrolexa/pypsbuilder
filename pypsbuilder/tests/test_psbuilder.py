import pytest

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QFileDialog

from pypsbuilder import psbuilders


@pytest.fixture
def window(qtbot):
    """Pass the application to the test functions via a pytest fixture."""
    window = psbuilders.PSBuilder()
    qtbot.addWidget(window)
    #new_window.show()
    return window


def test_window_title(qtbot, window):
    """Check that the window title shows as declared."""
    assert window.windowTitle() == 'PSBuilder'


def test_window_geometry(qtbot, window):
    """Check that the window width and height are set as declared."""
    assert window.width() == 1280
    assert window.height() == 720



