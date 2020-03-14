from collections import OrderedDict
import itertools

import numpy as np
import matplotlib.pyplot as plt
from shapely.geometry import LineString, Point
from shapely.ops import polygonize, linemerge, unary_union

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
        self.x = kwargs.get('x', [])
        self.y = kwargs.get('y', [])
        self.results = kwargs.get('results', [dict(data=None, ptguess=None)])
        self.output = kwargs.get('output', 'User-defined')
        self.manual = kwargs.get('manual', False)

    def __repr__(self):
        return 'Inv: {}'.format(self.label())

    @property
    def midix(self):
        return 0

    @property
    def _x(self):
        return self.x[0]

    @property
    def _y(self):
        return self.y[0]

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
        self._x = kwargs.get('x', [])
        self._y = kwargs.get('y', [])
        self.results = kwargs.get('results', [dict(data=None, ptguess=None)])
        self.output = kwargs.get('output', 'User-defined')
        self.manual = kwargs.get('manual', False)
        self.begin = kwargs.get('begin', 0)
        self.end = kwargs.get('end', 0)
        self.used = slice(0, len(self._x))
        self.x = self._x.copy()
        self.y = self._y.copy()

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
        if len(self.x) > 1:
            dx = np.diff(self.x)
            dy = np.diff(self.y)
            d = np.sqrt(dx**2 + dy**2)
            sd = np.sum(d)
            if sd > 0:
                cl = np.append([0], np.cumsum(d))
                ix = np.interp(sd / 2, cl, range(len(cl)))
                cix = int(ix)
                return self.x[cix] + (ix - cix) * dx[cix], self.y[cix] + (ix - cix) * dy[cix]
            else:
                return self.x[0], self.y[0]
        else:
            return self.x[0], self.y[0]


class SectionBase:
    def __init__(self, **kwargs):
        self.excess = kwargs.get('excess', set())
        self.invpoints = {}
        self.unilines = {}

    def __repr__(self):
        return '\n'.join(['{}'.format(type(self).__name__),
                          'Univariant lines: {}'.format(len(self.unilines)),
                          'Invariant points: {}'.format(len(self.invpoints)),
                          '{} range: {} {}'.format(self.x_var, *self.xrange),
                          '{} range: {} {}'.format(self.y_var, *self.yrange)])
    @property
    def ratio(self):
        return (self.xrange[1] - self.xrange[0]) / (self.yrange[1] - self.yrange[0])

    def add_inv(self, id, inv):
        self.invpoints[id] = inv
        self.invpoints[id].id = id

    def add_uni(self, id, uni):
        self.unilines[id] = uni
        self.unilines[id].id = id

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
            p1 = Point(self.invpoints[uni.begin].x,
                       self.ratio * self.invpoints[uni.begin].y)
        else:
            p1 = Point(uni._x[0], self.ratio * uni._y[0])
        if uni.end > 0:
            p2 = Point(self.invpoints[uni.end].x,
                       self.ratio * self.invpoints[uni.end].y)
        else:
            p2 = Point(uni._x[-1], self.ratio * uni._y[-1])
        if not uni.manual:
            xy = np.array([uni._x, self.ratio * uni._y]).T
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
            uni.used = slice(np.flatnonzero(vdst >= d1)[0],
                             np.flatnonzero(vdst <= d2)[-1] + 1)

        # concatenate begin, keep, end
        if uni.begin > 0:
            x1, y1 = self.invpoints[uni.begin].x, self.invpoints[uni.begin].y
        else:
            x1, y1 = [], []
        if uni.end > 0:
            x2, y2 = self.invpoints[uni.end].x, self.invpoints[uni.end].y
        else:
            x2, y2 = [], []
        if not uni.manual:
            xx = uni._x[uni.used]
            yy = uni._y[uni.used]
        else:
            xx, yy = [], []

        # store trimmed
        uni.x = np.hstack((x1, xx, x2))
        uni.y = np.hstack((y1, yy, y2))

    def construct_areas(self, shrink=0):
        def area_exists(indexes):
            def dfs_visit(graph, u, found_cycle, pred_node, marked, path):
                if found_cycle[0]:
                    return
                marked[u] = True
                path.append(u)
                for v in graph[u]:
                    if marked[v] and v != pred_node:
                        found_cycle[0] = True
                        return
                    if not marked[v]:
                        dfs_visit(graph, v, found_cycle, u, marked, path)
            # create graph
            graph = {}
            for ix in indexes:
                b, e = self.unilines[ix].begin, self.unilines[ix].end
                if b == 0:
                    nix = max(list(inv_coords.keys())) + 1
                    inv_coords[nix] = self.unilines[ix].x[0], self.unilines[ix].y[0]
                    b = nix
                if e == 0:
                    nix = max(list(inv_coords.keys())) + 1
                    inv_coords[nix] = self.unilines[ix].x[-1], self.unilines[ix].y[-1]
                    e = nix
                if b in graph:
                    graph[b] = graph[b] + (e,)
                else:
                    graph[b] = (e,)
                if e in graph:
                    graph[e] = graph[e] + (b,)
                else:
                    graph[e] = (b,)
                uni_index[(b, e)] = self.unilines[ix].id
                uni_index[(e, b)] = self.unilines[ix].id
            # do search
            path = []
            marked = {u: False for u in graph}
            found_cycle = [False]
            for u in graph:
                if not marked[u]:
                    dfs_visit(graph, u, found_cycle, u, marked, path)
                if found_cycle[0]:
                    break
            return found_cycle[0], path
        # starts here
        vertices, edges, phases = [], [], []
        tedges, tphases = [], []
        uni_index = {}
        for uni in self.unilines.values():
            uni_index[(uni.begin, uni.end)] = uni.id
            uni_index[(uni.end, uni.begin)] = uni.id
        inv_coords = {}
        for inv in self.invpoints.values():
            inv_coords[inv.id] = inv._x, inv._y
        faces = {}
        for ix, uni in self.unilines.items():
            f1 = frozenset(uni.phases)
            f2 = frozenset(uni.phases.difference(uni.out))
            if f1 in faces:
                faces[f1].append(ix)
            else:
                faces[f1] = [ix]
            if f2 in faces:
                faces[f2].append(ix)
            else:
                faces[f2] = [ix]
            # topology of polymorphs is degenerated
            for poly in polymorphs:
                if poly.issubset(uni.phases):
                    f2 = frozenset(uni.phases.difference(poly.difference(uni.out)))
                    if f2 in faces:
                        faces[f2].append(ix)
                    else:
                        faces[f2] = [ix]
        if uni_index and inv_coords and faces:
            for f in faces:
                exists, path = area_exists(faces[f])
                if exists:
                    edge = []
                    vert = []
                    for b, e in zip(path, path[1:] + path[:1]):
                        edge.append(uni_index.get((b, e), None))
                        vert.append(inv_coords[b])
                    # check for bad topology
                    if None not in edge:
                        edges.append(edge)
                        vertices.append(vert)
                        phases.append(f)
                    else:
                        #raise Exception('Topology error in path {}. Edges {}'.format(path, edge))
                        print('Topology error in path {}. Edges {}'.format(path, edge))
                else:
                    # loop not found, search for range crossing chain
                    for ppath in itertools.permutations(path):
                        edge = []
                        vert = []
                        for b, e in zip(ppath[:-1], ppath[1:]):
                            edge.append(uni_index.get((b, e), None))
                            vert.append(inv_coords[b])
                        vert.append(inv_coords[e])
                        if None not in edge:
                            x, y = vert[0]
                            if x < self.xrange[0] + shrink or x > self.xrange[1] - shrink or y < self.yrange[0] + shrink or y > self.yrange[1] - shrink:
                                x, y = vert[-1]
                                if x < self.xrange[0] + shrink or x > self.xrange[1] - shrink or y < self.yrange[0] + shrink or y > self.yrange[1] - shrink:
                                    tedges.append(edge)
                                    tphases.append(f)
                            break
        return vertices, edges, phases, tedges, tphases

    def create_shapes(self):
        if not isinstance(self, PTsection):
            shrink = 0.0001
        else:
            shrink = 0
        shapes = OrderedDict()
        shape_edges = OrderedDict()
        bad_shapes = OrderedDict()
        ignored_shapes = OrderedDict()
        log = []
        # traverse pseudosection
        vertices, edges, phases, tedges, tphases = self.construct_areas(shrink)
        # default p-t range boundary
        bnd = [LineString([(self.xrange[0] + shrink, self.yrange[0] + shrink),
                          (self.xrange[1] - shrink, self.yrange[0] + shrink)]),
               LineString([(self.xrange[1] - shrink, self.yrange[0] + shrink),
                          (self.xrange[1] - shrink, self.yrange[1] - shrink)]),
               LineString([(self.xrange[1] - shrink, self.yrange[1] - shrink),
                          (self.xrange[0] + shrink, self.yrange[1] - shrink)]),
               LineString([(self.xrange[0] + shrink, self.yrange[1] - shrink),
                          (self.xrange[0] + shrink, self.yrange[0] + shrink)])]
        bnda = list(polygonize(bnd))[0]
        # Create all full areas
        for ind in range(len(edges)):
            e, f = edges[ind], phases[ind]
            lns = [LineString(np.c_[self.unilines[fid].x, self.unilines[fid].y]) for fid in e]
            pp = polygonize(lns)
            invalid = True
            for ppp in pp:
                if not ppp.is_valid:
                    log.append('WARNING: Area {} defined by edges {} is not valid. Trying to fix it....'.format(' '.join(f), e))
                ppok = bnda.intersection(ppp.buffer(0))  # fix topologically correct but self-intersecting shapes
                if not ppok.is_empty and ppok.geom_type == 'Polygon':
                    invalid = False
                    shape_edges[f] = e
                    if f in shapes:
                        shapes[f] = shapes[f].union(ppok)
                    else:
                        shapes[f] = ppok
            if invalid:
                log.append('ERROR: Area defined by edges {} is not valid.'.format(e))
                bad_shapes[f] = e
        # Create all partial areas
        for ind in range(len(tedges)):
            e, f = tedges[ind], tphases[ind]
            lns = [LineString(np.c_[self.unilines[fid].x, self.unilines[fid].y]) for fid in e]
            pp = linemerge(lns)
            invalid = True
            if pp.geom_type == 'LineString':
                bndu = unary_union([s for s in bnd if pp.crosses(s)])
                if not bndu.is_empty:
                    pps = pp.difference(bndu)
                    bnds = bndu.difference(pp)
                    pp = polygonize(pps.union(bnds))
                    for ppp in pp:
                        ppok = bnda.intersection(ppp)
                        if ppok.geom_type == 'Polygon':
                            invalid = False
                            shape_edges[f] = e
                            if f in shapes:
                                shapes[f] = shapes[f].union(ppok)
                            else:
                                shapes[f] = ppok
            if invalid:
                ignored_shapes[f] = e
        # Fix possible overlaps of partial areas
        todel = set()
        for k1, k2 in itertools.combinations(shapes, 2):
            if shapes[k1].within(shapes[k2]):
                shapes[k2] = shapes[k2].difference(shapes[k1])
                if shapes[k2].is_empty:
                    todel.add(k2)
            if shapes[k2].within(shapes[k1]):
                shapes[k1] = shapes[k1].difference(shapes[k2])
                if shapes[k1].is_empty:
                    todel.add(k1)
        # remove degenerated polygons
        for k in todel:
            shapes.pop(k)
        return shapes, shape_edges, bad_shapes, ignored_shapes, log

    def show(self):
        for ln in self.unilines.values():
            plt.plot(ln.x, ln.y, 'k-')

        for ln in self.invpoints.values():
            plt.plot(ln.x, ln.y, 'ro')

        plt.xlim(self.xrange)
        plt.ylim(self.yrange)
        plt.xlabel(self.x_var_label)
        plt.xlabel(self.y_var_label)
        plt.show()


class PTsection(SectionBase):
    def __init__(self, **kwargs):
        self.xrange = kwargs.get('trange', (200., 1000.))
        self.yrange = kwargs.get('prange', (0.1, 20.))
        self.x_var = 'T'
        self.x_var_label = 'Temperature [C]'
        self.x_var_res = 0.01
        self.y_var = 'p'
        self.y_var_label = 'Pressure [kbar]'
        self.y_var_res = 0.001
        super(PTsection, self).__init__(**kwargs)

    def get_bulk_composition(self):
        for inv in self.invpoints.values():
            if not inv.manual:
                break
        bc = ['', '']
        if 'composition (from setbulk script)\n' in inv.output:
            bc = inv.output.split('composition (from setbulk script)\n')[1].split('\n')
        if 'composition (from script)\n' in inv.output:
            bc = inv.output.split('composition (from script)\n')[1].split('\n')
        return bc[0].split(), bc[1].split()

class TXsection(SectionBase):
    def __init__(self, **kwargs):
        self.xrange = kwargs.get('trange', (200., 1000.))
        self.yrange = (0., 1.)
        self.x_var = 'T'
        self.x_var_label = 'Temperature [C]'
        self.x_var_res = 0.01
        self.y_var = 'C'
        self.y_var_label = 'Composition'
        self.y_var_res = 0.001
        super(TXsection, self).__init__(**kwargs)

    def get_bulk_composition(self):
        for inv in self.invpoints.values():
            if not inv.manual:
                break
        bc = [[], []]
        if 'composition (from script)\n' in inv.output:
            tb = inv.output.split('composition (from script)\n')[1].split('<==================================================>')[0]
            nested = [r.split() for r in tb.split('\n')[2:-1]]
            bc = [[r[0] for r in nested],
                  [r[1] for r in nested],
                  [r[-1] for r in nested]]
        return bc
