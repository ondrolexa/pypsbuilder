"""Coverage-extension tests for psexplorer.py.

PS/PTPS/TXPS/PXPS.__init__ requires a real THERMOCALC working directory
(via get_tcapi), so most tests here build bare instances via
`PTPS.__new__(PTPS)` and set only the attributes the method under test
actually needs - the same technique used (as throwaway scripts, not
committed) to verify the STRtree/vectorization/consolidation work earlier
in this session. Where useful, results are cross-checked against a naive
reference implementation rather than just asserting "it doesn't crash".
"""

from types import SimpleNamespace

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest
from shapely.geometry import Polygon
from shapely.prepared import prep
from shapely.strtree import STRtree

from pypsbuilder import InvPoint, PTsection, UniLine
from pypsbuilder.psexplorer import GridData, PTpath, PTPS, PXPS, TXPS, eval_expr

# ---------------------------------------------------------------------
# eval_expr
# ---------------------------------------------------------------------


def test_eval_expr_basic_arithmetic():
    assert eval_expr("mode", {"mode": 0.25}) == 0.25
    assert eval_expr("xMgX/(xFeX+xMgX)", {"xMgX": 1.0, "xFeX": 3.0}) == 0.25
    assert eval_expr("2 * mode + 1", {"mode": 0.5}) == 2.0


def test_eval_expr_rejects_unsupported_node():
    with pytest.raises(TypeError):
        eval_expr("__import__('os')", {})


def test_eval_expr_unary_operators():
    assert eval_expr("-mode", {"mode": 0.5}) == -0.5
    assert eval_expr("+mode", {"mode": 0.5}) == 0.5
    assert eval_expr("-(mode + 1)", {"mode": 0.5}) == -1.5


# ---------------------------------------------------------------------
# GridData / PTpath
# ---------------------------------------------------------------------


def test_griddata_construction_and_helpers():
    ps = PTsection(trange=(400.0, 700.0), prange=(7.0, 16.0))
    grid = GridData(ps, nx=10, ny=5)
    assert grid.xg.shape == (5, 10)
    assert grid.status.shape == (5, 10)
    assert np.all(np.isnan(grid.status))
    assert "Grid 10x5" in repr(grid)

    r, c = grid.get_indexes(550.0, 10.0)
    assert 0 <= r < 5
    assert 0 <= c < 10
    assert grid.contains(550.0, 10.0)
    assert not grid.contains(0.0, 0.0)
    assert grid.xstep == pytest.approx(grid.xspace[1] - grid.xspace[0])

    neighbors = list(grid.neighs(0, 0))
    assert (0, 1) in neighbors
    assert (1, 0) in neighbors
    assert (-1, -1) not in neighbors  # out-of-range never yielded

    center_neighbors = list(grid.neighs(2, 5))
    assert len(center_neighbors) == 8  # full interior point has 8 neighbors


def test_ptpath_get_path_data():
    class FakeResult:
        def __init__(self, phases, data):
            self.phases = phases
            self.data = data

        def __getitem__(self, key):
            return self.data[key]

    results = [
        FakeResult({"g"}, {"g": {"mode": 0.1}}),
        FakeResult({"bi"}, {"bi": {"mode": 0.2}}),  # "g" not present -> nan
    ]
    path = PTpath([(500.0, 10.0), (510.0, 11.0)], results)
    assert np.allclose(path.t, [500.0, 510.0])
    assert np.allclose(path.p, [10.0, 11.0])
    data = path.get_path_data("g", "mode")
    assert data[0] == 0.1
    assert np.isnan(data[1])


# ---------------------------------------------------------------------
# identify / create_masks / common_grid_and_masks, cross-checked against
# a naive linear-scan reference
# ---------------------------------------------------------------------


def _make_two_field_ps():
    ps = PTPS.__new__(PTPS)
    shapes = {
        frozenset({"a", "b"}): Polygon([(0, 0), (2, 0), (2, 2), (0, 2)]),
        frozenset({"c", "d"}): Polygon([(3, 0), (5, 0), (5, 2), (3, 2)]),
    }
    ps.shapes = shapes
    ps._shapes = {0: shapes}
    shape_keys = list(shapes.keys())
    ps._shape_tree_keys = shape_keys
    ps._shape_tree = STRtree([shapes[k] for k in shape_keys])
    ps._prepared_shapes = {k: prep(v) for k, v in shapes.items()}
    ps._prepared_ix_shapes = {0: {k: prep(v) for k, v in shapes.items()}}
    return ps, shapes


def test_identify_matches_naive_reference():
    ps, shapes = _make_two_field_ps()

    def naive_identify(x, y):
        from shapely.geometry import Point

        point = Point(x, y)
        for k, shape in shapes.items():
            if shape.contains(point):
                return k
        return None

    rng = np.random.default_rng(0)
    for x, y in rng.uniform(-1, 6, size=(200, 2)):
        assert ps.identify(x, y) == naive_identify(x, y)


def test_identify_no_shapes_returns_none():
    ps = PTPS.__new__(PTPS)
    ps.shapes = {}
    ps._shape_tree_keys = []
    ps._shape_tree = None
    ps._prepared_shapes = {}
    assert ps.identify(0, 0) is None


def test_common_grid_and_masks_matches_naive_reference():
    ps, shapes = _make_two_field_ps()
    ps.sections = {0: SimpleNamespace(xrange=(-1, 6), yrange=(-1, 3))}
    ps.grids = {}

    ps.common_grid_and_masks(nx=30, ny=15)

    from shapely.geometry import MultiPoint

    points = MultiPoint(list(zip(ps.xg.flatten(), ps.yg.flatten())))
    for key, shape in shapes.items():
        expected = np.array(list(map(shape.contains, points.geoms))).reshape(
            ps.xg.shape
        )
        assert np.array_equal(expected, ps.masks[key])


def test_create_masks_matches_naive_reference():
    ps, shapes = _make_two_field_ps()
    from shapely.geometry import MultiPoint

    grid = SimpleNamespace(
        xg=np.linspace(-1, 6, 30).reshape(6, 5),
        yg=np.linspace(-1, 3, 30).reshape(6, 5),
        masks={},
    )
    ps.grids = {0: grid}
    ps.sections = {0: None}

    ps.create_masks()

    points = MultiPoint(list(zip(grid.xg.flatten(), grid.yg.flatten())))
    for key, shape in shapes.items():
        expected = np.array(list(map(shape.contains, points.geoms))).reshape(
            grid.xg.shape
        )
        assert np.array_equal(expected, grid.masks[key])


# ---------------------------------------------------------------------
# _inv_point_arrays / _uni_point_arrays, cross-checked against a naive
# reference
# ---------------------------------------------------------------------


def _make_ps_with_points():
    ps = PTsection(trange=(400.0, 700.0), prange=(7.0, 16.0))
    inv1 = InvPoint(phases={"a", "b", "c"}, out={"a"}, x=[500], y=[10], manual=True)
    ps.add_inv(1, inv1)
    inv2 = InvPoint(phases={"a", "b", "d"}, out={"b"}, x=[550], y=[11], manual=True)
    ps.add_inv(2, inv2)
    uni1 = UniLine(
        phases={"a", "b", "c"},
        out={"a"},
        manual=False,
        x=np.linspace(450, 650, 50),
        y=np.linspace(9, 12, 50),
        results=[{"data": {}, "ptguess": [""]} for _ in range(50)],
    )
    uni1.used = slice(5, 45)
    ps.add_uni(1, uni1)
    return ps


def test_inv_point_arrays_matches_naive_reference():
    ps = _make_ps_with_points()
    explorer = PTPS.__new__(PTPS)
    inv_ids, inv_x, inv_y = explorer._inv_point_arrays(ps)

    def naive_closest(x, y):
        dst = float("inf")
        for id_inv, inv in ps.invpoints.items():
            d2 = (inv._x - x) ** 2 + (inv._y - y) ** 2
            if d2 < dst:
                dst = d2
                id_close = id_inv
        return id_close

    rng = np.random.default_rng(1)
    for x, y in rng.uniform([400, 7], [700, 16], size=(100, 2)):
        d2 = (inv_x - x) ** 2 + (inv_y - y) ** 2
        got = int(inv_ids[np.argmin(d2)])
        assert got == naive_closest(x, y)


def test_uni_point_arrays_matches_naive_reference():
    ps = _make_ps_with_points()
    explorer = PTPS.__new__(PTPS)
    explorer.unilists = {0: {frozenset({"a", "b", "c"}): [1]}}

    def naive_closest(x, y):
        dst = float("inf")
        id_close = vix_close = None
        uni = ps.unilines[1]
        for vix in list(range(len(uni._x))[uni.used]):
            d2 = (uni._x[vix] - x) ** 2 + (uni._y[vix] - y) ** 2
            if d2 < dst:
                dst = d2
                id_close, vix_close = 1, vix
        return id_close, vix_close

    cache = {}
    k = frozenset({"a", "b", "c"})
    rng = np.random.default_rng(2)
    for x, y in rng.uniform([400, 7], [700, 16], size=(100, 2)):
        uni_ids_arr, vixs_arr, xs_arr, ys_arr = explorer._uni_point_arrays(
            ps, 0, k, cache
        )
        d2 = (xs_arr - x) ** 2 + (ys_arr - y) ** 2
        idx = np.argmin(d2)
        got = (int(uni_ids_arr[idx]), int(vixs_arr[idx]))
        assert got == naive_closest(x, y)


def test_uni_point_arrays_empty_when_all_manual():
    ps = _make_ps_with_points()
    ps.unilines[1].manual = True
    explorer = PTPS.__new__(PTPS)
    explorer.unilists = {0: {frozenset({"a", "b", "c"}): [1]}}
    result = explorer._uni_point_arrays(ps, 0, frozenset({"a", "b", "c"}), {})
    assert result is None


# ---------------------------------------------------------------------
# calculate_composition / fix_solutions with a fake THERMOCALC backend
# ---------------------------------------------------------------------


class _FakeTC:
    def __init__(self, **attrs):
        self.excess = frozenset()
        self.calls = []
        for k, v in attrs.items():
            setattr(self, k, v)

    def update_scriptfile(self, **kw):
        self.calls.append(("update_scriptfile", kw))

    def calc_assemblage(self, phases, p, t, onebulk=None):
        self.calls.append(("calc_assemblage", phases, p, t, onebulk))
        return "tcout", "ans"

    def parse_logfile(self):
        return "ok", [SimpleNamespace(ptguess=["guess"])], "output"


def _build_explorer(cls, section_class, ps, shape, tc):
    explorer = cls.__new__(cls)
    explorer.section_class = section_class
    explorer.sections = {0: ps}
    explorer.projfiles = {0: "/tmp/fake.ptb"}
    explorer._projdata = {0: {}}
    key = frozenset(next(iter(ps.invpoints.values())).phases)
    explorer.unilists = {0: {key: []}}
    explorer.shapes = {key: shape}
    explorer._shapes = {0: {key: shape}}
    shape_keys = [key]
    explorer._shape_tree_keys = shape_keys
    explorer._shape_tree = STRtree([shape])
    explorer._prepared_shapes = {key: prep(shape)}
    explorer._prepared_ix_shapes = {0: {key: prep(shape)}}
    explorer.tc = tc
    explorer.grids = {}
    explorer._variance = {}
    explorer.save = lambda: None
    explorer.create_masks = lambda: None
    explorer.collect_all_data_keys = lambda: None
    return explorer


def test_calculate_composition_ptps_all_success():
    ps = PTsection(trange=(400.0, 700.0), prange=(7.0, 16.0))
    inv = InvPoint(phases={"a", "b", "c"}, out={"a"}, x=[500], y=[10], manual=True)
    ps.add_inv(1, inv)
    shape = Polygon([(400, 7), (700, 7), (700, 16), (400, 16)])
    tc = _FakeTC()
    explorer = _build_explorer(PTPS, PTsection, ps, shape, tc)

    explorer.calculate_composition(nx=4, ny=4)

    n_calc = sum(1 for c in tc.calls if c[0] == "calc_assemblage")
    assert n_calc == 16
    assert np.count_nonzero(explorer.grids[0].status == 1) == 16


def test_calculate_composition_txps_uses_onebulk():
    from pypsbuilder import TXsection

    ps = TXsection(trange=(400.0, 700.0))
    inv = InvPoint(phases={"a", "b", "c"}, out={"a"}, x=[500], y=[0.5], manual=True)
    ps.add_inv(1, inv)
    shape = Polygon([(400, 0), (700, 0), (700, 1), (400, 1)])
    tc = _FakeTC(prange=(7.0, 16.0))
    explorer = _build_explorer(TXPS, TXsection, ps, shape, tc)

    explorer.calculate_composition(nx=4, ny=4)

    calc_calls = [c for c in tc.calls if c[0] == "calc_assemblage"]
    assert len(calc_calls) == 16
    assert all(c[4] is not None for c in calc_calls)  # onebulk was passed


def test_calculate_composition_pxps_uses_onebulk():
    from pypsbuilder import PXsection

    ps = PXsection(prange=(2.0, 10.0))
    inv = InvPoint(phases={"a", "b", "c"}, out={"a"}, x=[0.5], y=[5.0], manual=True)
    ps.add_inv(1, inv)
    shape = Polygon([(0, 2), (1, 2), (1, 10), (0, 10)])
    tc = _FakeTC(trange=(400.0, 700.0))
    explorer = _build_explorer(PXPS, PXsection, ps, shape, tc)

    explorer.calculate_composition(nx=4, ny=4)

    calc_calls = [c for c in tc.calls if c[0] == "calc_assemblage"]
    assert len(calc_calls) == 16
    assert all(c[4] is not None for c in calc_calls)


def test_fix_solutions_seeds_guesses_from_neighbor():
    ps = PTsection(trange=(400.0, 700.0), prange=(7.0, 16.0))
    inv = InvPoint(phases={"a", "b"}, out={"a"}, x=[500], y=[10], manual=True)
    ps.add_inv(1, inv)
    explorer = PTPS.__new__(PTPS)
    explorer.tc = _FakeTC()
    explorer.sections = {0: ps}

    grid = SimpleNamespace(
        xg=np.array([[500.0, 500.0]]),
        yg=np.array([[10.0, 11.0]]),
        status=np.array([[1, 0]]),
        gridcalcs=np.empty((1, 2), dtype=object),
        delta=np.zeros((1, 2)),
    )
    grid.gridcalcs[0, 0] = SimpleNamespace(ptguess=["seed"])
    explorer.grids = {0: grid}
    explorer.identify = lambda x, y: frozenset({"a", "b"})

    def neighs(r, c):
        return [(0, 0)]

    grid.neighs = neighs

    explorer.fix_solutions()

    assert ("update_scriptfile", {"guesses": ["seed"]}) in explorer.tc.calls
    assert grid.status[0, 1] == 1


# ---------------------------------------------------------------------
# save / collect_all_data_keys
# ---------------------------------------------------------------------


def test_save_writes_variance_and_grid(tmp_path):
    import gzip
    import pickle

    ps = PTsection(trange=(400.0, 700.0), prange=(7.0, 16.0))
    projfile = tmp_path / "test.ptb"
    with gzip.open(projfile, "wb") as f:
        pickle.dump({"section": ps}, f)

    explorer = PTPS.__new__(PTPS)
    explorer.projfiles = {0: projfile}
    explorer._projdata = {0: {"section": ps}}
    explorer.grids = {0: GridData(ps, nx=2, ny=2)}
    explorer._variance = {0: {"key": 2}}
    explorer.sections = {0: ps}

    explorer.save()

    with gzip.open(projfile, "rb") as f:
        saved = pickle.load(f)
    assert saved["variance"] == {"key": 2}
    assert isinstance(saved["grid"], GridData)


def test_save_not_gridded_noop(capsys):
    explorer = PTPS.__new__(PTPS)
    explorer.sections = {0: None}
    explorer.grids = {}
    explorer.save()
    assert "Not yet gridded" in capsys.readouterr().out


def test_collect_all_data_keys():
    ps = PTsection(trange=(400.0, 700.0), prange=(7.0, 16.0))
    from pypsbuilder.psclasses import TCResult, TCResultSet

    result = TCResult(500.0, 10.0, data={"g": {"mode": 0.1, "x": 0.2}})
    inv = InvPoint(
        phases={"a", "g"},
        out={"a"},
        x=[500],
        y=[10],
        results=TCResultSet([result]),
        manual=False,
    )
    ps.add_inv(1, inv)

    explorer = PTPS.__new__(PTPS)
    explorer.sections = {0: ps}
    explorer._shapes = {0: {frozenset({"a", "g"}): None}}
    explorer.grids = {}

    explorer.collect_all_data_keys()

    assert "g" in explorer.all_data_keys
    assert set(explorer.all_data_keys["g"]) == {"mode", "x"}


# ---------------------------------------------------------------------
# isopleths / isopleths_vector / gendrawpd / save_tab - smoke tests
# ---------------------------------------------------------------------


def test_isopleths_smoke():
    from pypsbuilder.psclasses import TCResult

    ps = PTsection(trange=(400.0, 700.0), prange=(7.0, 16.0))
    shape = Polygon([(400, 7), (700, 7), (700, 16), (400, 16)])
    key = frozenset({"a", "b"})
    grid = GridData(ps, nx=6, ny=6)
    grid.status[:] = 1
    for r in range(6):
        for c in range(6):
            grid.gridcalcs[r, c] = TCResult(
                500.0, 10.0, data={"a": {"mode": 0.1 + 0.01 * r}}
            )
    grid.masks[key] = np.ones((6, 6), dtype=bool)

    explorer = PTPS.__new__(PTPS)
    explorer.section_class = PTsection
    explorer.sections = {0: ps}
    explorer.shapes = {key: shape}
    explorer.grids = {0: grid}
    explorer.tc = _FakeTC()
    explorer.abbr = {}
    explorer.show_errors = False
    explorer.all_data_keys = {"a": ["mode"]}
    explorer.unilists = {0: {}}

    result = explorer.isopleths("a", "mode", show=False)
    assert result is not None
    plt.close("all")


def test_isopleths_vector_smoke():
    from pypsbuilder.psclasses import TCResult

    ps = PTsection(trange=(400.0, 700.0), prange=(7.0, 16.0))
    shape = Polygon([(400, 7), (700, 7), (700, 16), (400, 16)])
    key = frozenset({"a", "b"})
    grid = GridData(ps, nx=6, ny=6)
    grid.status[:] = 1
    for r in range(6):
        for c in range(6):
            grid.gridcalcs[r, c] = TCResult(
                500.0, 10.0, data={"a": {"mode": 0.1 + 0.01 * r}}
            )
    grid.masks[key] = np.ones((6, 6), dtype=bool)

    explorer = PTPS.__new__(PTPS)
    explorer.section_class = PTsection
    explorer.sections = {0: ps}
    explorer.shapes = {key: shape}
    explorer.grids = {0: grid}
    explorer.tc = _FakeTC()
    explorer.abbr = {}
    explorer.show_errors = False
    explorer.all_data_keys = {"a": ["mode"]}
    explorer.unilists = {0: {}}

    result = explorer.isopleths_vector("a", "mode", show=False)
    assert result is not None
    plt.close("all")


def test_gendrawpd_smoke(tmp_path):
    ps = PTsection(trange=(400.0, 700.0), prange=(7.0, 16.0))
    inv = InvPoint(phases={"a", "b", "c"}, out={"a"}, x=[500], y=[10], manual=True)
    ps.add_inv(1, inv)
    uni = UniLine(
        phases={"a", "b", "c"},
        out={"a"},
        manual=True,
        x=np.array([490.0, 510.0]),
        y=np.array([9.0, 11.0]),
    )
    ps.add_uni(1, uni)
    shape = Polygon([(400, 7), (700, 7), (700, 16), (400, 16)])
    key = frozenset({"a", "b"})

    explorer = PTPS.__new__(PTPS)
    explorer.section_class = PTsection
    explorer.sections = {0: ps}
    explorer._shapes = {0: {key: shape}}
    tc = _FakeTC()
    tc.drawpdfile = tmp_path / "dr-test.txt"
    tc.TCenc = "mac-roman"
    tc.drexe = None
    explorer.tc = tc

    explorer.gendrawpd(export_areas=False)

    content = tc.drawpdfile.read_text()
    assert "Generated by pypsbuilder" in content
    assert "% Points" in content
    assert "% Lines" in content


def test_save_tab_smoke(tmp_path):
    from pypsbuilder.psclasses import TCResult
    from shapely.prepared import prep

    ps = PTsection(trange=(400.0, 700.0), prange=(7.0, 16.0))
    shape = Polygon([(400, 7), (700, 7), (700, 16), (400, 16)])
    key = frozenset({"a", "b"})
    grid = GridData(ps, nx=6, ny=6)
    grid.status[:] = 1
    for r in range(6):
        for c in range(6):
            grid.gridcalcs[r, c] = TCResult(
                500.0, 10.0, data={"a": {"mode": 0.1 + 0.01 * r}}
            )
    grid.masks[key] = np.ones((6, 6), dtype=bool)

    explorer = PTPS.__new__(PTPS)
    explorer.section_class = PTsection
    explorer.sections = {0: ps}
    explorer.shapes = {key: shape}
    explorer._prepared_shapes = {key: prep(shape)}
    explorer.grids = {0: grid}
    explorer.tc = _FakeTC()
    explorer.abbr = {}
    explorer.show_errors = False
    explorer.all_data_keys = {"a": ["mode"]}
    explorer.unilists = {0: {}}
    explorer.projfiles = {0: tmp_path / "test.ptb"}

    tabfile = tmp_path / "out.tab"
    explorer.save_tab([("a", "mode")], tabfile=str(tabfile))

    content = tabfile.read_bytes()
    assert content.startswith(b"ptbuilder")
