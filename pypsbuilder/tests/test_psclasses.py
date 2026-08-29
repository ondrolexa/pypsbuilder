"""Coverage-extension tests for psclasses.py gaps not exercised by
test_pclasses.py (which focuses on parsing real THERMOCALC fixtures and
SectionBase point/line bookkeeping). Uses fresh, independent objects
throughout (not the shared `pytest.ps` from test_pclasses.py) so these
tests don't depend on, or interfere with, that file's test ordering.
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest
from shapely.geometry import Point

from pypsbuilder import InvPoint, PTsection, PXsection, TXsection, UniLine
from pypsbuilder.psclasses import (
    Dogmin,
    PolygonPatch,
    PolygonPath,
    Polygon as PsbPolygon,
    TCResult,
    TCResultSet,
)


# --------------------------------------------------------------------------
# Dogmin
# --------------------------------------------------------------------------


def test_dogmin_tc35_style():
    output = "some preamble\nassemblage bi g mu q ilm hem H2O\nmore stuff"
    resic = "fake ic content"
    dgm = Dogmin(output=output, resic=resic, x=500.0, y=10.0)

    assert dgm.phases == {"bi", "g", "mu", "q", "ilm", "hem", "H2O"}
    assert dgm.output == output
    assert dgm.resic == resic
    assert dgm.out == set()
    assert dgm.x == 500.0
    assert dgm.y == 10.0


def test_dogmin_gibbs_info_style():
    # Synthetic reconstruction of the older "Gibbs energy minimisation
    # info" dogmin output format (ranked candidate assemblages, "best"
    # marked by number) - hand-traced against Dogmin.__init__'s parsing
    # logic since no real example of this format exists in the repo.
    asm = (
        "header line\n  #\n"
        "1  extra stuff\n"
        "phases : bi g mu q ilm hem H2O #1\n"
        "  block1 detail\n"
        "phases : bi g mu q sill H2O #2\n"
        "  block2 detail\n"
    )
    output = "prefix\nGibbs energy minimisation info\n" + asm
    dgm = Dogmin(output=output, resic="")

    assert dgm.phases == {"bi", "g", "mu", "q", "ilm", "hem", "H2O"}


def test_dogmin_label_and_annotation():
    dgm = Dogmin(output="assemblage bi g mu q ilm hem H2O\n", resic="", id=7)
    assert dgm.label() == "H2O bi g hem ilm mu q"
    assert dgm.label(excess={"H2O"}) == "bi g hem ilm mu q"
    assert dgm.annotation(show_out=False) == "7"
    assert dgm.annotation(show_out=True) == dgm.label()


def test_dogmin_ptguess():
    output = "\n".join(
        [
            "assemblage bi g q",
            "xyzguess x(g)          0.5",
            "xyzguess x(bi)         0.4",
            "ptguess extra line before markers",
            "more stuff",
        ]
    )
    dgm = Dogmin(output=output, resic="")
    guess = dgm.ptguess()
    assert any(ln.startswith("xyzguess") for ln in guess)


# --------------------------------------------------------------------------
# TCResult
# --------------------------------------------------------------------------


def test_tcresult_construction_and_defaults():
    r1 = TCResult(500.0, 10.0, variance=3, c=0.1)
    r2 = TCResult(510.0, 11.0)
    # mutable-default regression check: distinct instances must not share
    # the same underlying data/ptguess objects
    r1.data["g"] = {"mode": 0.1}
    assert r2.data == {}
    assert r1.ptguess is not r2.ptguess
    assert r2.ptguess == [""]


def test_tcresult_phases_and_getitem():
    r = TCResult(500.0, 10.0, data={"g": {"mode": 0.2}, "bi": {"mode": 0.3}})
    assert r.phases == {"g", "bi"}
    assert r["g"] == {"mode": 0.2}
    with pytest.raises(IndexError):
        r["missing"]
    with pytest.raises(TypeError):
        r[0]


def test_tcresult_rename_phase():
    r = TCResult(
        500.0,
        10.0,
        data={"mu": {"mode": 0.2}},
        ptguess=["x(mu) 0.5", "y(mu) 0.2"],
    )
    r.rename_phase("mu", "pa")
    assert r.phases == {"pa"}
    assert r.data["pa"] == {"mode": 0.2}
    assert r.ptguess == ["x(pa) 0.5", "y(pa) 0.2"]


# --------------------------------------------------------------------------
# TCResultSet
# --------------------------------------------------------------------------


def _make_result_set():
    r0 = TCResult(500.0, 10.0, variance=3, c=0.0, data={"g": {"mode": 0.1}})
    r1 = TCResult(510.0, 11.0, variance=3, c=0.1, data={"g": {"mode": 0.2}})
    r2 = TCResult(520.0, 12.0, variance=3, c=0.2, data={"g": {"mode": 0.3}})
    return TCResultSet([r0, r1, r2])


def test_tcresultset_properties():
    rs = _make_result_set()
    assert len(rs) == 3
    assert np.allclose(rs.x, [500.0, 510.0, 520.0])
    assert np.allclose(rs.y, [10.0, 11.0, 12.0])
    assert rs.variance == 3
    assert np.allclose(rs.c, [0.0, 0.1, 0.2])
    assert rs.phases == {"g"}
    assert "3 results" in repr(rs)


def test_tcresultset_getitem_variants():
    rs = _make_result_set()
    assert rs[0].T == 500.0
    assert rs[-1].T == 520.0
    with pytest.raises(IndexError):
        rs[10]
    sliced = rs[0:2]
    assert isinstance(sliced, TCResultSet)
    assert len(sliced) == 2
    listed = rs[[0, 2]]
    assert isinstance(listed, TCResultSet)
    assert len(listed) == 2
    assert listed[1].T == 520.0
    with pytest.raises(TypeError):
        rs["g"]


def test_tcresultset_ptguess_and_insert():
    rs = _make_result_set()
    assert rs.ptguess(0) == [""]
    assert rs.ptguess(99) is None  # out-of-range -> caught, returns None
    extra = TCResult(530.0, 13.0, variance=3, c=0.3, data={"g": {"mode": 0.4}})
    rs.insert(0, extra)
    assert len(rs) == 4
    assert rs[0].T == 530.0


def test_tcresultset_rename_phase():
    rs = _make_result_set()
    rs.rename_phase("g", "gt")
    assert rs.phases == {"gt"}
    for r in rs.results:
        assert r.phases == {"gt"}


# --------------------------------------------------------------------------
# PseudoBase (via InvPoint/UniLine)
# --------------------------------------------------------------------------


def test_pseudobase_label_annotation_ptguess_datakeys():
    rs = _make_result_set()
    inv = InvPoint(
        phases={"g", "bi", "q"},
        out={"bi"},
        x=[500.0],
        y=[10.0],
        results=rs,
        manual=False,
    )
    assert inv.label() == "bi g q - bi"
    assert inv.label(excess={"q"}) == "bi g - bi"
    assert inv.annotation(state=0) == "0"
    assert inv.annotation(state=1) == "bi"
    assert inv.annotation(state=2) == "0 bi"
    assert inv.ptguess() == [""]
    assert inv.datakeys() == ["g"]
    assert inv.datakeys(phase="g") == ["mode"]


# --------------------------------------------------------------------------
# SectionBase gaps: add_dogmin, cleanup_data, range_shapes, show
# --------------------------------------------------------------------------


def test_section_add_dogmin():
    ps = PTsection(trange=(400.0, 700.0), prange=(7.0, 16.0))
    dgm = Dogmin(output="assemblage bi g q\n", resic="", x=500.0, y=10.0)
    ps.add_dogmin(1, dgm)
    assert ps.dogmins[1] is dgm
    assert ps.dogmins[1].id == 1


def test_section_cleanup_data_manual_line():
    ps = PTsection(trange=(400.0, 700.0), prange=(7.0, 16.0))
    uni = UniLine(
        phases={"a", "b"},
        out={"a"},
        manual=True,
        x=np.array([1.0, 2.0]),
        y=np.array([1.0, 2.0]),
    )
    ps.add_uni(1, uni)
    ps.cleanup_data()
    assert uni.cmd == ""
    assert uni.variance == 0
    assert uni._x.size == 0
    assert uni._y.size == 0
    assert uni.used == slice(0, 0)
    assert uni.output == "User-defined"


def test_section_cleanup_data_calculated_line():
    ps = PTsection(trange=(400.0, 700.0), prange=(7.0, 16.0))
    rs = TCResultSet(
        [TCResult(500.0 + i, 10.0 + i, data={"g": {"mode": 0.1}}) for i in range(5)]
    )
    uni = UniLine(
        phases={"a", "b"},
        out={"a"},
        manual=False,
        x=np.arange(5.0),
        y=np.arange(5.0),
        results=rs,
    )
    uni.used = slice(1, 4)
    ps.add_uni(1, uni)
    ps.cleanup_data()
    # keep = slice(max(1-1,0), min(4+1,5)) = slice(0, 5) -> whole array kept
    assert uni._x.size == 5
    assert len(uni.results) == 5


def test_section_range_shapes():
    ps = PTsection(trange=(400.0, 700.0), prange=(7.0, 16.0))
    bnd, poly = ps.range_shapes
    assert len(bnd) == 4
    assert poly.contains(Point(500.0, 10.0))
    assert not poly.contains(Point(0.0, 0.0))


def test_section_show_smoke():
    ps = PTsection(trange=(400.0, 700.0), prange=(7.0, 16.0))
    plt.show = lambda *a, **k: None  # avoid any backend interaction
    ps.show()
    plt.close("all")


def test_txsection_pxsection_construct():
    tx = TXsection(trange=(400.0, 700.0))
    px = PXsection(prange=(2.0, 10.0))
    assert tx.x_var == "T"
    assert tx.yrange == (0.0, 1.0)
    assert px.y_var == "p"
    assert px.xrange == (0.0, 1.0)


# --------------------------------------------------------------------------
# Polygon / PolygonPath / PolygonPatch
# --------------------------------------------------------------------------


def test_identity_indexed_dict_edge_methods():
    ps = PTsection(trange=(400.0, 700.0), prange=(7.0, 16.0))
    inv1 = InvPoint(phases={"a", "b"}, out={"a"}, x=[1], y=[1], manual=True)
    inv2 = InvPoint(phases={"c", "d"}, out={"c"}, x=[2], y=[2], manual=True)
    ps.add_inv(1, inv1)
    ps.add_inv(2, inv2)

    # pop
    popped = ps.invpoints.pop(1)
    assert popped is inv1
    assert 1 not in ps.invpoints
    is_new, _ = ps.getidinv(InvPoint(phases={"a", "b"}, out={"a"}, x=[0], y=[0]))
    assert is_new is True  # popped identity no longer found

    # setdefault
    inv3 = InvPoint(phases={"e", "f"}, out={"e"}, x=[3], y=[3], manual=True)
    result = ps.invpoints.setdefault(3, inv3)
    assert result is inv3
    assert ps.invpoints[3] is inv3
    # existing key -> returns existing value, doesn't overwrite
    assert ps.invpoints.setdefault(3, "ignored") is inv3

    # update
    inv4 = InvPoint(phases={"g", "h"}, out={"g"}, x=[4], y=[4], manual=True)
    ps.invpoints.update({4: inv4})
    assert ps.invpoints[4] is inv4
    is_new, _ = ps.getidinv(InvPoint(phases={"g", "h"}, out={"g"}, x=[0], y=[0]))
    assert is_new is False

    # popitem
    key, obj = ps.invpoints.popitem()
    assert key not in ps.invpoints

    # clear
    ps.invpoints.clear()
    assert len(ps.invpoints) == 0
    assert ps.invpoints.max_id == 0


def test_section_read_file_and_from_file(tmp_path):
    import gzip
    import pickle

    ps = PTsection(trange=(400.0, 700.0), prange=(7.0, 16.0))
    inv = InvPoint(phases={"a", "b"}, out={"a"}, x=[1], y=[1], manual=True)
    ps.add_inv(1, inv)

    projfile = tmp_path / "section_test.ptb"
    with gzip.open(projfile, "wb") as stream:
        pickle.dump({"section": ps, "workdir": str(tmp_path)}, stream)

    data = PTsection.read_file(projfile)
    assert data["workdir"] == str(tmp_path)
    assert set(data["section"].invpoints) == {1}

    loaded_section = PTsection.from_file(projfile)
    assert isinstance(loaded_section, PTsection)
    assert set(loaded_section.invpoints) == {1}


def test_polygon_adapter_and_patch():
    from shapely.geometry import Polygon as ShapelyPolygon

    shp = ShapelyPolygon([(0, 0), (2, 0), (2, 2), (0, 2)])
    adapted = PsbPolygon(shp)
    assert adapted.geom_type == "Polygon"
    assert len(list(adapted.exterior.coords)) >= 4

    path = PolygonPath(shp)
    assert path.vertices.shape[1] == 2

    patch = PolygonPatch(shp, fc="blue", ec="blue", alpha=0.5)
    assert patch is not None
