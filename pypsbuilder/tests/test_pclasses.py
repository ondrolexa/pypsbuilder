import pytest
from pypsbuilder import TCAPI, InvPoint, UniLine, PTsection

pytest.ps = PTsection(trange=(400., 700.), prange=(7., 16.))

@pytest.fixture
def mock_tc():
	return TCAPI('./examples/outputs')

def test_parse_ini1(mock_tc):
    test = 'inv1'
    ofile = mock_tc.workdir / '{}-log.txt'.format(test)
    icfile = mock_tc.workdir / '{}-ic.txt'.format(test)

    with ofile.open('r', encoding=mock_tc.TCenc) as f:
        output = f.read()

    with icfile.open('r', encoding=mock_tc.TCenc) as f:
        resic = f.read()

    status, variance, pts, res, output = mock_tc.parse_logfile_new(output=output, resic=resic)

    inv = InvPoint(phases={'bi', 'mu', 'chl', 'H2O', 'ep', 'q', 'g', 'sph', 'pa'},
                   out={'ep', 'chl'},
                   variance=variance,
                   x=pts[1],
                   y=pts[0],
                   results=res,
                   output=output)
    pytest.ps.add_inv(1, inv)

    assert status == 'ok', 'Wromg status'
    assert variance == 4, 'Wromg variance'
    assert pts.shape == (2, 1), 'Wrong pts shape'
    assert pts[0][0] == 12.2438, 'Wrong pressure'
    assert pts[1][0] == 530.136, 'Wrong temperature'
    assert len(res) == 1, 'Wrong results length'
    assert 'data' in res[0], 'No data key in results'
    assert 'ptguess' in res[0], 'No ptguess key in results'
    assert type(res[0]['data']) == dict, 'Wrong data type data'
    assert type(res[0]['ptguess']) == list, 'Wrong data type of ptguess'


def test_parse_ini2(mock_tc):
    test = 'inv2'
    ofile = mock_tc.workdir / '{}-log.txt'.format(test)
    icfile = mock_tc.workdir / '{}-ic.txt'.format(test)

    with ofile.open('r', encoding=mock_tc.TCenc) as f:
        output = f.read()

    with icfile.open('r', encoding=mock_tc.TCenc) as f:
        resic = f.read()

    status, variance, pts, res, output = mock_tc.parse_logfile_new(output=output, resic=resic)

    inv = InvPoint(phases={'ep', 'pa', 'sph', 'q', 'H2O', 'mu', 'chl', 'g', 'ab', 'bi'},
                   out={'ab', 'chl'},
                   variance=variance,
                   x=pts[1],
                   y=pts[0],
                   results=res,
                   output=output)
    pytest.ps.add_inv(2, inv)

    assert status == 'ok', 'Wromg status'
    assert variance == 3, 'Wromg variance'
    assert pts.shape == (2, 1), 'Wrong pts shape'
    assert pts[0][0] == 7.0359, 'Wrong pressure'
    assert pts[1][0] == 504.062, 'Wrong temperature'
    assert len(res) == 1, 'Wrong results length'
    assert 'data' in res[0], 'No data key in results'
    assert 'ptguess' in res[0], 'No ptguess key in results'
    assert type(res[0]['data']) == dict, 'Wrong data type data'
    assert type(res[0]['ptguess']) == list, 'Wrong data type of ptguess'

def test_parse_ini3(mock_tc):
    test = 'inv3'
    ofile = mock_tc.workdir / '{}-log.txt'.format(test)
    icfile = mock_tc.workdir / '{}-ic.txt'.format(test)

    with ofile.open('r', encoding=mock_tc.TCenc) as f:
        output = f.read()

    with icfile.open('r', encoding=mock_tc.TCenc) as f:
        resic = f.read()

    status, variance, pts, res, output = mock_tc.parse_logfile_new(output=output, resic=resic)

    inv = InvPoint(phases={'pa', 'H2O', 'sph', 'g', 'mu', 'bi', 'q', 'ep', 'ab'},
                   out={'ab', 'ep'},
                   variance=variance,
                   x=pts[1],
                   y=pts[0],
                   results=res,
                   output=output)
    pytest.ps.add_inv(3, inv)

    assert status == 'ok', 'Wromg status'
    assert variance == 4, 'Wromg variance'
    assert pts.shape == (2, 1), 'Wrong pts shape'
    assert pts[0][0] == 11.908, 'Wrong pressure'
    assert pts[1][0] == 561.425, 'Wrong temperature'
    assert len(res) == 1, 'Wrong results length'
    assert 'data' in res[0], 'No data key in results'
    assert 'ptguess' in res[0], 'No ptguess key in results'
    assert type(res[0]['data']) == dict, 'Wrong data type data'
    assert type(res[0]['ptguess']) == list, 'Wrong data type of ptguess'

def test_parse_uni1(mock_tc):
    test = 'uni1'
    ofile = mock_tc.workdir / '{}-log.txt'.format(test)
    icfile = mock_tc.workdir / '{}-ic.txt'.format(test)

    with ofile.open('r', encoding=mock_tc.TCenc) as f:
        output = f.read()

    with icfile.open('r', encoding=mock_tc.TCenc) as f:
        resic = f.read()

    status, variance, pts, res, output = mock_tc.parse_logfile_new(output=output, resic=resic)

    uni = UniLine(phases={'bi', 'mu', 'chl', 'H2O', 'ep', 'q', 'g', 'sph', 'pa'},
                  out={'chl'},
                  variance=variance,
                  x=pts[1],
                  y=pts[0],
                  begin=2,
                  end=1,
                  results=res,
                  output=output)
    pytest.ps.add_uni(1, uni)

    assert status == 'ok', 'Wromg status'
    assert variance == 4, 'Wromg variance'
    assert pts.shape == (2, 29), 'Wrong pts shape'
    assert pts[0][15] == 9.52, 'Wrong pressure'
    assert pts[1][15] == 526.322, 'Wrong temperature'
    assert len(res) == 29, 'Wrong results length'
    assert 'data' in res[0], 'No data key in results'
    assert 'ptguess' in res[0], 'No ptguess key in results'
    assert type(res[0]['data']) == dict, 'Wrong data type data'
    assert type(res[0]['ptguess']) == list, 'Wrong data type of ptguess'

def test_parse_uni2(mock_tc):
    test = 'uni2'
    ofile = mock_tc.workdir / '{}-log.txt'.format(test)
    icfile = mock_tc.workdir / '{}-ic.txt'.format(test)

    with ofile.open('r', encoding=mock_tc.TCenc) as f:
        output = f.read()

    with icfile.open('r', encoding=mock_tc.TCenc) as f:
        resic = f.read()

    status, variance, pts, res, output = mock_tc.parse_logfile_new(output=output, resic=resic)

    uni = UniLine(phases={'pa', 'H2O', 'sph', 'g', 'mu', 'bi', 'q', 'ep'},
                  out={'ep'},
                  variance=variance,
                  x=pts[1],
                  y=pts[0],
                  begin=1,
                  end=3,
                  results=res,
                  output=output)
    pytest.ps.add_uni(2, uni)

    assert status == 'ok', 'Wromg status'
    assert variance == 5, 'Wromg variance'
    assert pts.shape == (2, 51), 'Wrong pts shape'
    assert pts[0][25] == 12.0314, 'Wrong pressure'
    assert pts[1][25] == 550.0, 'Wrong temperature'
    assert len(res) == 51, 'Wrong results length'
    assert 'data' in res[0], 'No data key in results'
    assert 'ptguess' in res[0], 'No ptguess key in results'
    assert type(res[0]['data']) == dict, 'Wrong data type data'
    assert type(res[0]['ptguess']) == list, 'Wrong data type of ptguess'

def test_parse_uni3(mock_tc):
    test = 'uni3'
    ofile = mock_tc.workdir / '{}-log.txt'.format(test)
    icfile = mock_tc.workdir / '{}-ic.txt'.format(test)

    with ofile.open('r', encoding=mock_tc.TCenc) as f:
        output = f.read()

    with icfile.open('r', encoding=mock_tc.TCenc) as f:
        resic = f.read()

    status, variance, pts, res, output = mock_tc.parse_logfile_new(output=output, resic=resic)

    uni = UniLine(phases={'pa', 'H2O', 'sph', 'g', 'mu', 'bi', 'q', 'ep', 'ab'},
                  out={'ab'},
                  variance=variance,
                  x=pts[1],
                  y=pts[0],
                  begin=2,
                  end=3,
                  results=res,
                  output=output)
    pytest.ps.add_uni(3, uni)

    assert status == 'ok', 'Wromg status'
    assert variance == 4, 'Wromg variance'
    assert pts.shape == (2, 28), 'Wrong pts shape'
    assert pts[0][14] == 9.322, 'Wrong pressure'
    assert pts[1][14] == 543.12, 'Wrong temperature'
    assert len(res) == 28, 'Wrong results length'
    assert 'data' in res[0], 'No data key in results'
    assert 'ptguess' in res[0], 'No ptguess key in results'
    assert type(res[0]['data']) == dict, 'Wrong data type data'
    assert type(res[0]['ptguess']) == list, 'Wrong data type of ptguess'

def test_contains_inv():
    for uni in pytest.ps.unilines.values():
        inv1 = pytest.ps.invpoints[uni.begin]
        inv2 = pytest.ps.invpoints[uni.end]
        assert uni.contains_inv(inv1), 'Error in UniLine.contains_inv method'
        assert uni.contains_inv(inv2), 'Error in UniLine.contains_inv method'

def test_getidinv():
    for key, inv in pytest.ps.invpoints.items():
        is_new, id_found = pytest.ps.getidinv(inv)
        assert is_new == False, 'Error chcecking existing invariant point'
        assert key == id_found, 'Error chcecking existing inv id'

def test_getiduni():
    for key, uni in pytest.ps.unilines.items():
        is_new, id_found = pytest.ps.getiduni(uni)
        assert is_new == False, 'Error chcecking existing univariant line'
        assert key == id_found, 'Error chcecking existing uni id'

def test_auto_connect():
    for uni in pytest.ps.unilines.values():
        candidates = [inv for inv in pytest.ps.invpoints.values() if uni.contains_inv(inv)]
        assert len(candidates) == 2, 'Error to detect auto_connect possibility'

def test_remaining_uni():
    for key, inv in pytest.ps.invpoints.items():
        n = 0
        for phases, out in inv.all_unilines():
            tmp_uni = UniLine(phases=phases, out=out)
            is_new, id_found = pytest.ps.getiduni(tmp_uni)
            if is_new:
                n += 1
        assert n == 2, 'Error in detection of remaining univariant lines'

def test_trim_uni():
    uni = pytest.ps.unilines[1]
    assert uni.used == slice(0, 29), 'Wrong used slice before trimming uni 1'
    pytest.ps.trim_uni(1)
    assert uni.used == slice(3, 29), 'Wrong used slice after trimming uni 1'
    #
    uni = pytest.ps.unilines[2]
    assert uni.used == slice(0, 51), 'Wrong used slice before trimming uni 2'
    pytest.ps.trim_uni(2)
    assert uni.used == slice(22, 27), 'Wrong used slice after trimming uni 2'
    #
    uni = pytest.ps.unilines[3]
    assert uni.used == slice(0, 28), 'Wrong used slice before trimming uni 3'
    pytest.ps.trim_uni(3)
    assert uni.used == slice(3, 28), 'Wrong used slice after trimming uni 3'

def test_create_shapes():
    shapes, shape_edges, log = pytest.ps.create_shapes()
    akey = frozenset({'pa', 'ep', 'g', 'q', 'bi', 'mu', 'H2O', 'sph'})
    assert len(shapes) == 1, 'Wrong number of areas created'
    assert akey in shapes, 'Wrong key for constructed area'
