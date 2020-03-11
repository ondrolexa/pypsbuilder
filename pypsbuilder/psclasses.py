import numpy as np
import matplotlib.pyplot as plt
from shapely.geometry import LineString, Point

polymorphs = [{'sill', 'and'}, {'ky', 'and'}, {'sill', 'ky'}, {'q', 'coe'}, {'diam', 'gph'}]

class PseudoBase:
    """Base class
    """
    def label(self, excess={}):
        return (' '.join(sorted(list(self.phases.difference(excess)))) +
                ' - ' +
                ' '.join(sorted(list(self.out))))
    def annotation(self, show_out=False):
        if show_out:
            return '{:d} {}'.format(self.id, ' '.join(self.out))
        else:
            return '{:d}'.format(self.id)

    def ptguess(self, **kwargs):
        idx = kwargs.get('idx', self.midix)
        return self.results[idx]['ptguess']

    def data(self, **kwargs):
        idx = kwargs.get('idx', self.midix)
        return self.results[idx]['data']

class InvPoint(PseudoBase):
    """Class to store invariant point
    """
    def __init__(self, **kwargs):
        assert 'phases' in kwargs, 'Set of phases must be provided'
        assert 'out' in kwargs, 'Set of zero phase must be provided'
        self.id = kwargs.get('id', 0)
        self.phases = kwargs.get('phases')
        self.out = kwargs.get('out')
        self.cmd = kwargs.get('cmd', '')
        self.variance = kwargs.get('variance', 0)
        self.p = kwargs.get('p', [])
        self.T = kwargs.get('T', [])
        self.results = kwargs.get('results', [dict(data=None, ptguess=None)])
        self.output = kwargs.get('output', 'User-defined')
        self.manual = kwargs.get('manual', False)

    def __repr__(self):
        return 'Inv: {}'.format(self.label())

    @property
    def midix(self):
        return 0

    @property
    def _p(self):
        return self.p[0]

    @property
    def _T(self):
        return self.T[0]

    def all_unilines(self):
        a, b = self.out
        aset, bset = set([a]), set([b])
        aphases, bphases = self.phases.difference(aset), self.phases.difference(bset)
        # Check for polymorphs
        fix = False
        for poly in polymorphs:
            if poly.issubset(self.phases):
                fix = True
                break
        if fix and (poly != self.out):   # on boundary
                yespoly = poly.intersection(self.out)
                nopoly = self.out.difference(yespoly)
                aphases = self.phases.difference(yespoly)
                bphases = self.phases.difference(poly.difference(self.out))
                return((aphases, nopoly),
                       (bphases, nopoly),
                       (self.phases, yespoly),
                       (self.phases.difference(nopoly), yespoly))
        else:
            return((self.phases, aset),
                   (self.phases, bset),
                   (bphases, aset),
                   (aphases, bset))


class UniLine(PseudoBase):
    """Class to store univariant line
    """
    def __init__(self, **kwargs):
        assert 'phases' in kwargs, 'Set of phases must be provided'
        assert 'out' in kwargs, 'Set of zero phase must be provided'
        self.id = kwargs.get('id', 0)
        self.phases = kwargs.get('phases')
        self.out = kwargs.get('out')
        self.cmd = kwargs.get('cmd', '')
        self.variance = kwargs.get('variance', 0)
        self._p = kwargs.get('p', [])
        self._T = kwargs.get('T', [])
        self.results = kwargs.get('results', [dict(data=None, ptguess=None)])
        self.output = kwargs.get('output', 'User-defined')
        self.manual = kwargs.get('manual', False)
        self.begin = kwargs.get('begin', 0)
        self.end = kwargs.get('end', 0)
        self.p = self._p.copy()
        self.T = self._T.copy()

    def __repr__(self):
        return 'Uni: {}'.format(self.label())

    @property
    def midix(self):
        return len(self.results) // 2

    def contains_inv(self, ip):
        def checkme(uphases, uout, iphases, iout):
            a, b = iout
            aset, bset = set([a]), set([b])
            aphases, bphases = iphases.difference(aset), iphases.difference(bset)
            candidate = False
            if iphases == uphases and len(iout.difference(uout)) == 1:
                candidate = True
            if bphases == uphases and aset == uout:
                candidate = True
            if aphases == uphases and bset == uout:
                candidate = True
            return candidate
        # Check for polymorphs
        fixi, fixu = False, False
        for poly in polymorphs:
            if poly.issubset(ip.phases) and (poly != ip.out) and (not ip.out.isdisjoint(poly)):
                fixi = True
                if poly.issubset(self.phases) and not self.out.isdisjoint(poly):
                    fixu = True
                break
        # check invs
        candidate = checkme(self.phases, self.out, ip.phases, ip.out)
        if fixi and not candidate:
            candidate = checkme(self.phases, self.out, ip.phases, ip.out.difference(poly).union(poly.difference(ip.out)))
        if fixu and not candidate:
            candidate = checkme(self.phases, poly.difference(self.out), ip.phases, ip.out)
        return candidate

    def get_label_point(self):
        if len(self.T) > 1:
            dT = np.diff(self.T)
            dp = np.diff(self.p)
            d = np.sqrt(dT**2 + dp**2)
            if np.sum(d) > 0:
                cl = np.append([0], np.cumsum(d))
                ix = np.interp(np.sum(d) / 2, cl, range(len(cl)))
                cix = int(ix)
                return self.T[cix] + (ix - cix) * dT[cix], self.p[cix] + (ix - cix) * dp[cix]
            else:
                return self.T[0], self.p[0]
        else:
            return self.T[0], self.p[0]


class PTsection:
    def __init__(self, **kwargs):
        self.trange = kwargs.get('trange', (450, 700))
        self.prange = kwargs.get('prange', (7, 16))
        self.excess = kwargs.get('excess', set())
        self.invpoints = {}
        self.unilines = {}

    @property
    def ratio(self):
        return (self.trange[1] - self.trange[0]) / (self.prange[1] - self.prange[0])

    def add_inv(self, id, inv):
        self.invpoints[id] = inv

    def add_uni(self, id, uni):
        self.unilines[id] = uni

    def getidinv(self, inv=None):
        '''Return id of either new or existing invariant point'''
        ids = 0
        # collect polymorphs identities
        if inv is not None:
            outs = [inv.out]
            for poly in polymorphs:
                if poly.issubset(inv.phases):
                    switched = inv.out.difference(poly).union(poly.difference(inv.out))
                    if switched:
                        outs.append(switched)

        for iid, cinv in self.invpoints.items():
            if inv is not None:
                if cinv.phases == inv.phases:
                    if cinv.out in outs:
                        inv.out = cinv.out  # switch to already used ??? Needed ???
                        return False, iid
            ids = max(ids, iid)
        return True, ids + 1

    def getiduni(self, uni=None):
        '''Return id of either new or existing univariant line'''
        ids = 0
        # collect polymorphs identities
        if uni is not None:
            outs = [uni.out]
            for poly in polymorphs:
                if poly.issubset(uni.phases):
                    outs.append(poly.difference(uni.out))

        for uid, cuni in self.unilines.items():
            if uni is not None:
                if cuni.phases == uni.phases:
                    if cuni.out in outs:
                        uni.out = cuni.out # switch to already used ??? Needed ???
                        return False, uid
            ids = max(ids, uid)
        return True, ids + 1

    def trim_uni(self, id):
        uni = self.unilines[id]
        if uni.begin > 0:
            p1 = Point(self.invpoints[uni.begin].T,
                       self.ratio * self.invpoints[uni.begin].p)
        else:
            p1 = Point(uni._T[0], self.ratio * uni._p[0])
        if uni.end > 0:
            p2 = Point(self.invpoints[uni.end].T,
                       self.ratio * self.invpoints[uni.end].p)
        else:
            p2 = Point(uni._T[-1], self.ratio * uni._p[-1])
        if not uni.manual:
            xy = np.array([uni._T, self.ratio * uni._p]).T
            line = LineString(xy)
            # vertex distances
            vdst = np.array([line.project(Point(*v)) for v in xy])
            d1 = line.project(p1)
            d2 = line.project(p2)
            # switch if needed
            if d1 > d2:
                d1, d2 = d2, d1
                uni.begin, uni.end = uni.end, uni.begin
            # get slice of points to keep
            keep = slice(np.flatnonzero(vdst >= d1)[0], np.flatnonzero(vdst <= d2)[-1] + 1)

        # concatenate begin, keep, end
        if uni.begin > 0:
            T1, p1 = self.invpoints[uni.begin].T, self.invpoints[uni.begin].p
        else:
            T1, p1 = [], []
        if uni.end > 0:
            T2, p2 = self.invpoints[uni.end].T, self.invpoints[uni.end].p
        else:
            T2, p2 = [], []
        if not uni.manual:
            T = uni._T[keep]
            p = uni._p[keep]
        else:
            if uni.begin == 0 and uni.end == 0:
                T, p = uni._T, uni._p
            else:
                T, p = [], []

        # store trimmed
        uni.T = np.hstack((T1, T, T2))
        uni.p = np.hstack((p1, p, p2))


    def show(self):
        for ln in pt.unilines.values():
            plt.plot(ln.T, ln.p, 'k-')

        for ln in pt.invpoints.values():
            plt.plot(ln.T, ln.p, 'ro')

        plt.xlim(self.trange)
        plt.ylim(self.prange)
        plt.show()
