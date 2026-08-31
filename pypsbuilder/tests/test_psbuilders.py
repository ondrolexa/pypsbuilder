"""Coverage-extension tests for psbuilders.py, scoped to non-GUI-coupled
pure logic and headless smoke instantiation (per the confirmed plan scope)
- not deep simulated interaction flows (mocked click-through calc runs,
dialogs). psbuilders.py drives a real Qt widget tree and THERMOCALC
subprocess calls with no existing safety net, so exhaustive interaction
testing there is a poor effort/value trade; this focuses on what can be
tested with high confidence: the pure algorithms, the Qt table models
(which don't need a visible widget tree), and confirming the three
builders construct without crashing.

Requires QT_QPA_PLATFORM=offscreen, set below before any Qt import.
"""

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from qtpy import QtCore, QtWidgets

# A QApplication must exist before psbuilders.py's module-level
# `matplotlib.use("QtAgg")` runs below: matplotlib only permits the Qt
# backend without a real X/Wayland DISPLAY (as on a headless CI runner) if
# it detects an already-running QApplication.
_qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from pypsbuilder import InvPoint, PTsection, PXsection, TXsection, UniLine  # noqa: E402
from pypsbuilder.psbuilders import (  # noqa: E402
    BuildersBase,
    DogminModel,
    InvModel,
    PTBuilder,
    PXBuilder,
    TXBuilder,
    UniModel,
    fmt,
    intersection,
)

# ---------------------------------------------------------------------
# QApplication fixture (module-scoped: Qt only supports one instance)
# ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


# ---------------------------------------------------------------------
# fmt
# ---------------------------------------------------------------------


def test_fmt():
    assert fmt(1.0) == "1"
    assert fmt(1.5) == "1.5"
    assert fmt(0.000123456) == "0.000123456"
    assert fmt(1234567) == "1.23457e+06"


# ---------------------------------------------------------------------
# intersection() - pure numpy/scipy line-intersection algorithm
# ---------------------------------------------------------------------


def _fake_uni(x, y):
    return SimpleNamespace(_x=np.array(x), _y=np.array(y))


def test_intersection_crossing_lines():
    # two segments crossing at (5, 5)
    uni1 = _fake_uni([0, 10], [0, 10])
    uni2 = _fake_uni([0, 10], [10, 0])
    x, y = intersection(uni1, uni2)
    assert len(x) >= 1
    assert np.isclose(x[0], 5, atol=0.5)
    assert np.isclose(y[0], 5, atol=0.5)


def test_intersection_parallel_lines_no_crossing():
    uni1 = _fake_uni([0, 1, 2, 3], [0, 0, 0, 0])
    uni2 = _fake_uni([0, 1, 2, 3], [1, 1, 1, 1])
    x, y = intersection(uni1, uni2)
    assert len(x) == 0


# ---------------------------------------------------------------------
# BuildersBase.toolbar_mode_name - safe fallback, no real Qt widget needed
# ---------------------------------------------------------------------


def test_toolbar_mode_name_with_mode():
    stub = SimpleNamespace(toolbar=SimpleNamespace(mode=SimpleNamespace(name="PAN")))
    assert BuildersBase.toolbar_mode_name(stub) == "PAN"


def test_toolbar_mode_name_missing_attrs_falls_back():
    stub = SimpleNamespace(toolbar=SimpleNamespace())  # no .mode at all
    assert BuildersBase.toolbar_mode_name(stub) == ""
    stub2 = SimpleNamespace(toolbar=None)
    assert BuildersBase.toolbar_mode_name(stub2) == ""


# ---------------------------------------------------------------------
# QAbstractTableModel classes - no visible widget tree needed, just a
# QApplication instance
# ---------------------------------------------------------------------


def _make_ps_with_inv_and_dogmin():
    from pypsbuilder.psclasses import Dogmin

    ps = PTsection(trange=(400.0, 700.0), prange=(7.0, 16.0))
    inv = InvPoint(phases={"a", "b", "c"}, out={"a"}, x=[500], y=[10], manual=True)
    dgm = Dogmin(output="assemblage bi g q\n", resic="", x=500.0, y=10.0)
    return ps, inv, dgm


def test_invmodel_row_lifecycle(qapp):
    ps, inv, _ = _make_ps_with_inv_and_dogmin()
    model = InvModel(ps, None)
    assert model.rowCount() == 0
    assert model.columnCount() == 2
    assert model.headerData(0, QtCore.Qt.Orientation.Horizontal) == "ID"

    model.appendRow(1, inv)
    assert model.rowCount() == 1
    assert ps.invpoints[1] is inv

    idx0 = model.index(0, 0, QtCore.QModelIndex())
    idx1 = model.index(0, 1, QtCore.QModelIndex())
    assert model.data(idx0) == 1
    assert model.data(idx1) == inv.label(excess=ps.excess)
    assert model.getRowID(idx0) == 1
    assert model.getIndexID(1).row() == 0

    model.removeRow(idx0)
    assert model.rowCount() == 0
    assert 1 not in ps.invpoints


def test_dogminmodel_row_lifecycle(qapp):
    ps, _, dgm = _make_ps_with_inv_and_dogmin()
    model = DogminModel(ps, None)
    model.appendRow(1, dgm)
    assert model.rowCount() == 1
    assert ps.dogmins[1] is dgm

    idx1 = model.index(0, 1, QtCore.QModelIndex())
    assert model.data(idx1) == dgm.label(excess=ps.excess)

    model.removeRow(model.index(0, 0, QtCore.QModelIndex()))
    assert model.rowCount() == 0
    assert 1 not in ps.dogmins


def test_unimodel_row_lifecycle(qapp):
    ps = PTsection(trange=(400.0, 700.0), prange=(7.0, 16.0))
    uni = UniLine(
        phases={"a", "b"},
        out={"a"},
        manual=True,
        x=np.array([1.0, 2.0]),
        y=np.array([1.0, 2.0]),
        begin=0,
        end=0,
    )
    model = UniModel(ps, None)
    model.appendRow(1, uni)
    assert model.rowCount() == 1

    idx_id = model.index(0, 0, QtCore.QModelIndex())
    idx_begin = model.index(0, 2, QtCore.QModelIndex())
    assert model.data(idx_id) == 1
    assert model.data(idx_begin) == 0

    model.setData(idx_begin, 5, role=QtCore.Qt.ItemDataRole.EditRole)
    assert uni.begin == 5

    model.removeRow(model.index(0, 0, QtCore.QModelIndex()))
    assert model.rowCount() == 0


# ---------------------------------------------------------------------
# BuildersBase._build_export_json (pure data construction, no Qt/file I/O
# so it's tested directly against a duck-typed stand-in for self, avoiding
# a live QMainWindow/THERMOCALC just like import_from_json's schema is
# validated by _validate_import_json without one)
# ---------------------------------------------------------------------


def _fake_builder(
    builder_name, ps, tc_prange=(1.9, 10.1), tc_trange=(345.0, 805.0), spin_steps=50
):
    return SimpleNamespace(
        builder_name=builder_name,
        ps=ps,
        tc=SimpleNamespace(prange=tc_prange, trange=tc_trange),
        spinSteps=SimpleNamespace(value=lambda: spin_steps),
    )


def test_build_export_json_pt():
    ps = PTsection(trange=(345.0, 805.0), prange=(1.9, 10.1))
    inv = InvPoint(
        phases={"bi", "g", "mu"},
        out={"bi", "g"},
        x=np.array([530.0]),
        y=np.array([5.5]),
    )
    uni = UniLine(
        phases={"bi", "g", "mu"},
        out={"mu"},
        x=np.array([500.0, 560.0]),
        y=np.array([5.0, 6.0]),
    )
    ps.invpoints[1] = inv
    ps.unilines[1] = uni

    data = BuildersBase._build_export_json(_fake_builder("PTBuilder", ps))

    assert data["kind"] == "PT"
    assert data["P"] == [1.9, 10.1]
    assert data["T"] == [345.0, 805.0]

    inv_entry = data["inv"][0]
    assert inv_entry["P"] == [5.5, 5.5]
    assert inv_entry["T"] == [530.0, 530.0]
    assert inv_entry["X"] is None
    assert inv_entry["phases"] == sorted(["bi", "g", "mu"])
    assert inv_entry["out"] == sorted(["bi", "g"])

    uni_entry = data["uni"][0]
    assert uni_entry["P"] == [5.0, 6.0]
    assert uni_entry["T"] == [500.0, 560.0]
    assert uni_entry["X"] is None
    assert uni_entry["out"] == ["mu"]


def test_build_export_json_tx():
    ps = TXsection(trange=(345.0, 805.0))
    inv = InvPoint(
        phases={"a", "b", "c"}, out={"a", "b"}, x=np.array([500.0]), y=np.array([0.4])
    )
    uni = UniLine(
        phases={"a", "b", "c"},
        out={"c"},
        x=np.array([480.0, 520.0]),
        y=np.array([0.3, 0.5]),
    )
    ps.invpoints[1] = inv
    ps.unilines[1] = uni

    data = BuildersBase._build_export_json(
        _fake_builder("TXBuilder", ps, tc_prange=(2.0, 8.0))
    )

    assert data["kind"] == "TX"
    assert data["P"] == 5.0
    assert data["T"] == [345.0, 805.0]

    inv_entry = data["inv"][0]
    assert inv_entry["P"] is None
    assert inv_entry["T"] == [500.0, 500.0]
    assert inv_entry["X"] == [0.4, 0.4]

    uni_entry = data["uni"][0]
    assert uni_entry["P"] is None
    assert uni_entry["T"] == [480.0, 520.0]
    assert uni_entry["X"] == [0.3, 0.5]


def test_build_export_json_px():
    ps = PXsection(prange=(1.9, 10.1))
    inv = InvPoint(
        phases={"a", "b", "c"}, out={"a", "b"}, x=np.array([0.4]), y=np.array([5.0])
    )
    uni = UniLine(
        phases={"a", "b", "c"},
        out={"c"},
        x=np.array([0.3, 0.5]),
        y=np.array([4.5, 5.5]),
    )
    ps.invpoints[1] = inv
    ps.unilines[1] = uni

    data = BuildersBase._build_export_json(
        _fake_builder("PXBuilder", ps, tc_trange=(400.0, 600.0))
    )

    assert data["kind"] == "PX"
    assert data["P"] == [1.9, 10.1]
    assert data["T"] == 500.0

    inv_entry = data["inv"][0]
    assert inv_entry["T"] is None
    assert inv_entry["X"] == [0.4, 0.4]
    assert inv_entry["P"] == [5.0, 5.0]

    uni_entry = data["uni"][0]
    assert uni_entry["T"] is None
    assert uni_entry["X"] == [0.3, 0.5]
    assert uni_entry["P"] == [4.5, 5.5]


# ---------------------------------------------------------------------
# BuildersBase._entry_xy / _nearest_invpoint / _import_step_count
# (pure JSON-import helpers, tested the same duck-typed way as
# _build_export_json above)
# ---------------------------------------------------------------------


def test_entry_xy_pt():
    ps = PTsection(trange=(345.0, 805.0), prange=(1.9, 10.1))
    b = _fake_builder("PTBuilder", ps)
    x, y = BuildersBase._entry_xy(b, {"T": [500.0, 560.0], "P": [5.0, 6.0]})
    assert x == 530.0
    assert y == 5.5


def test_entry_xy_tx():
    ps = TXsection(trange=(345.0, 805.0))
    b = _fake_builder("TXBuilder", ps)
    x, y = BuildersBase._entry_xy(b, {"T": [480.0, 520.0], "X": [0.3, 0.5], "P": None})
    assert x == 500.0
    assert y == 0.4


def test_entry_xy_px():
    ps = PXsection(prange=(1.9, 10.1))
    b = _fake_builder("PXBuilder", ps)
    x, y = BuildersBase._entry_xy(b, {"X": [0.3, 0.5], "P": [4.5, 5.5], "T": None})
    assert x == 0.4
    assert y == 5.0


def test_entry_xy_missing_key_returns_none():
    ps = PTsection(trange=(345.0, 805.0), prange=(1.9, 10.1))
    b = _fake_builder("PTBuilder", ps)
    x, y = BuildersBase._entry_xy(b, {"T": [500.0, 560.0]})
    assert (x, y) == (None, None)


def test_nearest_invpoint_normalizes_by_range():
    # xrange span 100, yrange span 10: a point that's far in x but close in y
    # should win over one that's close in x but far in y, once both are
    # normalized by their axis span - the opposite of what raw Euclidean
    # distance would pick.
    ps = PTsection(trange=(0.0, 100.0), prange=(0.0, 10.0))
    inv_close_in_y = InvPoint(
        phases={"a", "b"}, out={"a"}, x=np.array([10.0]), y=np.array([5.0])
    )
    inv_close_in_x = InvPoint(
        phases={"a", "c"}, out={"a"}, x=np.array([50.0]), y=np.array([0.0])
    )
    ps.invpoints[1] = inv_close_in_y
    ps.invpoints[2] = inv_close_in_x
    b = _fake_builder("PTBuilder", ps)
    nearest = BuildersBase._nearest_invpoint(b, 50.0, 5.0)
    assert nearest is inv_close_in_y


def test_nearest_invpoint_none_when_empty():
    ps = PTsection(trange=(345.0, 805.0), prange=(1.9, 10.1))
    b = _fake_builder("PTBuilder", ps)
    assert BuildersBase._nearest_invpoint(b, 500.0, 5.0) is None


def test_import_step_count_keeps_user_steps_for_wide_span():
    b = _fake_builder("PTBuilder", PTsection(), spin_steps=50)
    # full_span=600 -> min step 3; a wide local span of 300 allows up to 100
    # steps before hitting the floor, well above the user's configured 50
    assert BuildersBase._import_step_count(b, span=300.0, full_span=600.0) == 50


def test_import_step_count_floor_kicks_in_for_narrow_span():
    b = _fake_builder("PTBuilder", PTsection(), spin_steps=50)
    # full_span=600 -> min step 3; a narrow local span of 15 only allows 5
    # steps before the step size would drop below the floor, capping the
    # user's configured 50 down to 5
    assert BuildersBase._import_step_count(b, span=15.0, full_span=600.0) == 5


def test_import_step_count_falls_back_when_full_span_zero():
    b = _fake_builder("PTBuilder", PTsection(), spin_steps=50)
    assert BuildersBase._import_step_count(b, span=15.0, full_span=0.0) == 50


# ---------------------------------------------------------------------
# PTBuilder._uni_calc_strategy (calctatp yes/no choice for JSON-imported
# univariant lines)
# ---------------------------------------------------------------------


def test_uni_calc_strategy_steps_t_for_near_isobaric_line():
    # full P span 19.9, full T span 700; local P span 0.05 (~0.25% of P
    # range) vs local T span 100 (~14% of T range) - near-isobaric line,
    # step T and solve P (calc_p, calctatp no)
    b = _fake_builder(
        "PTBuilder", PTsection(), tc_prange=(0.1, 20.0), tc_trange=(300.0, 1000.0)
    )
    assert PTBuilder._uni_calc_strategy(b, 5.0, 5.05, 500.0, 600.0) == "calc_p"


def test_uni_calc_strategy_steps_p_for_near_isothermal_line():
    # local P span 10 (~50% of P range) vs local T span 1 (~0.14% of T
    # range) - near-isothermal line, step P and solve T (calc_t, calctatp
    # yes)
    b = _fake_builder(
        "PTBuilder", PTsection(), tc_prange=(0.1, 20.0), tc_trange=(300.0, 1000.0)
    )
    assert PTBuilder._uni_calc_strategy(b, 5.0, 15.0, 500.0, 501.0) == "calc_t"


# ---------------------------------------------------------------------
# Headless smoke instantiation of the three builders
# ---------------------------------------------------------------------


@pytest.mark.parametrize("builder_cls", [PTBuilder, TXBuilder, PXBuilder])
def test_builder_headless_smoke_instantiation(qapp, builder_cls):
    window = builder_cls()
    assert window.ready is False
    assert window.centralWidget() is not None
    assert window.actionExport_json.text() == "Export JSON..."
    window.close()
