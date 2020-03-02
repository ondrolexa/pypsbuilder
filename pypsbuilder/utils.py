import sys
import os
try:
  import cPickle as pickle
except ImportError:
  import pickle
import gzip
import ast
import subprocess
import itertools
import re
from pathlib import Path
from collections import OrderedDict
import numpy as np

from shapely.geometry import LineString, Point
from shapely.ops import polygonize, linemerge, unary_union

popen_kw = dict(stdout=subprocess.PIPE, stdin=subprocess.PIPE,
                stderr=subprocess.STDOUT, universal_newlines=False)

polymorphs = [{'sill', 'and'}, {'ky', 'and'}, {'sill', 'ky'}, {'q', 'coe'}, {'diam', 'gph'}]

class InitError(Exception):
    pass


class ScriptfileError(Exception):
    pass


class TCError(Exception):
    pass


class PSBFile(object):
    def __init__(self, projfile):
        psb = Path(projfile).resolve()
        if psb.exists():
            stream = gzip.open(str(psb), 'rb')
            self.data = pickle.load(stream)
            stream.close()
            self.name = psb.name
            self.unilookup = {}
            self.invlookup = {}
            for ix, r in enumerate(self.unilist):
                self.unilookup[r[0]] = ix
            for ix, r in enumerate(self.invlist):
                self.invlookup[r[0]] = ix
        else:
            raise Exception('File {} does not exists.'.format(projfile))

    @property
    def selphases(self):
        return self.data['selphases']

    @property
    def out(self):
        return self.data['out']

    @property
    def trange(self):
        return self.data['trange']

    @property
    def prange(self):
        return self.data['prange']

    @property
    def unilist(self):
        return self.data['unilist']

    @property
    def invlist(self):
        return self.data['invlist']

    @property
    def tcversion(self):
        if 'tcversion' in self.data:
            return self.data['tcversion']
        else:
            print('Old format. No tcversion.')

    @property
    def version(self):
        if 'version' in self.data:
            return self.data['version']
        else:
            print('Old format. No version.')

    def unidata(self, fid):
        uni = self.unilist[self.unilookup[fid]]
        dt = uni[4]
        dt['begin'] = uni[2]
        dt['end'] = uni[3]
        return dt

    def invdata(self, fid):
        return self.invlist[self.invlookup[fid]][2]

    def get_trimmed_uni(self, fid):
        uni = self.unilist[self.unilookup[fid]]
        if uni[2] > 0:
            dt = self.invdata(uni[2])
            T1, p1 = dt['T'][0], dt['p'][0]
        else:
            T1, p1 = [], []
        if uni[3] > 0:
            dt = self.invdata(uni[3])
            T2, p2 = dt['T'][0], dt['p'][0]
        else:
            T2, p2 = [], []
        if not uni[4]['manual']:
            T = uni[4]['T'][uni[4]['begix']:uni[4]['endix'] + 1]
            p = uni[4]['p'][uni[4]['begix']:uni[4]['endix'] + 1]
        else:
            if uni[2] == 0 and uni[3] == 0:
                T, p = uni[4]['T'], uni[4]['p']
            else:
                T, p = [], []
        return np.hstack((T1, T, T2)), np.hstack((p1, p, p2))

    def get_bulk_composition(self):
        for inv in self.invlist:
            if not inv[2]['manual']:
                break
        bc = inv[2]['output'].split('composition (from script)\n')[1].split('\n')
        return bc[0].split(), bc[1].split()

    def construct_areas(self):
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
                b, e = self.unilist[ix][2], self.unilist[ix][3]
                if b == 0:
                    nix = max(list(inv_coords.keys())) + 1
                    inv_coords[nix] = self.unilist[ix][4]['T'][0], self.unilist[ix][4]['p'][0]
                    b = nix
                if e == 0:
                    nix = max(list(inv_coords.keys())) + 1
                    inv_coords[nix] = self.unilist[ix][4]['T'][-1], self.unilist[ix][4]['p'][-1]
                    e = nix
                if b in graph:
                    graph[b] = graph[b] + (e,)
                else:
                    graph[b] = (e,)
                if e in graph:
                    graph[e] = graph[e] + (b,)
                else:
                    graph[e] = (b,)
                uni_index[(b, e)] = self.unilist[ix][0]
                uni_index[(e, b)] = self.unilist[ix][0]
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
        uni_index = {}
        for r in self.unilist:
            uni_index[(r[2], r[3])] = r[0]
            uni_index[(r[3], r[2])] = r[0]
        inv_coords = {}
        for r in self.invlist:
            inv_coords[r[0]] = r[2]['T'][0], r[2]['p'][0]
        faces = {}
        for ix, uni in enumerate(self.unilist):
            f1 = frozenset(uni[4]['phases'])
            f2 = frozenset(uni[4]['phases'] - uni[4]['out'])
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
                if poly.issubset(uni[4]['phases']):
                    f2 = frozenset(uni[4]['phases'] - poly.difference(uni[4]['out']))
                    if f2 in faces:
                        faces[f2].append(ix)
                    else:
                        faces[f2] = [ix]
        vertices, edges, phases = [], [], []
        tedges, tphases = [], []
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
                        if (x < self.trange[0] or x > self.trange[1] or y < self.prange[0] or y > self.prange[1]):
                            x, y = vert[-1]
                            if (x < self.trange[0] or x > self.trange[1] or y < self.prange[0] or y > self.prange[1]):
                                tedges.append(edge)
                                tphases.append(f)
                        break
        return vertices, edges, phases, tedges, tphases

    def create_shapes(self):
        shapes = OrderedDict()
        shape_edges = OrderedDict()
        bad_shapes = OrderedDict()
        # traverse pseudosection
        vertices, edges, phases, tedges, tphases = self.construct_areas()
        # default p-t range boundary
        bnd = [LineString([(self.trange[0], self.prange[0]),
                          (self.trange[1], self.prange[0])]),
               LineString([(self.trange[1], self.prange[0]),
                          (self.trange[1], self.prange[1])]),
               LineString([(self.trange[1], self.prange[1]),
                          (self.trange[0], self.prange[1])]),
               LineString([(self.trange[0], self.prange[1]),
                          (self.trange[0], self.prange[0])])]
        bnda = list(polygonize(bnd))[0]
        # Create all full areas
        for ind in range(len(edges)):
            e, f = edges[ind], phases[ind]
            lns = [LineString(np.c_[self.get_trimmed_uni(fid)]) for fid in e]
            pp = polygonize(lns)
            invalid = True
            for ppp in pp:
                if not ppp.is_valid:
                    print('Area {} defined by edges {} is not valid. Trying to fix it....'.format(' '.join(f), e))
                ppok = bnda.intersection(ppp.buffer(0))  # fix topologically correct but self-intersecting shapes
                if not ppok.is_empty and ppok.geom_type == 'Polygon':
                    invalid = False
                    shape_edges[f] = e
                    if f in shapes:
                        shapes[f] = shapes[f].union(ppok)
                    else:
                        shapes[f] = ppok
            if invalid:
                bad_shapes[f] = e
        # Create all partial areas
        for ind in range(len(tedges)):
            e, f = tedges[ind], tphases[ind]
            lns = [LineString(np.c_[self.get_trimmed_uni(fid)]) for fid in e]
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
                bad_shapes[f] = e
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
        return shapes, shape_edges, bad_shapes


class TCAPI(object):
    """
    Class to access TC functionality in given working directory
    """

    def __init__(self, workdir):
        self.workdir = Path(workdir).resolve()
        self.TCenc = 'mac-roman'
        try:
            errinfo = 'Initialize project error!'
            # default exe
            if sys.platform.startswith('win'):
                tcpat = 'tc3*.exe'
                drpat = 'dr1*.exe'
            #elif sys.platform.startswith('linux'):
            #    tcpat = 'tc3*L'
            #    drpat = 'dr*L'
            else:
                tcpat = 'tc3*'
                drpat = 'dr1*'
            # THERMOCALC exe
            self.tcexe = None
            for p in self.workdir.glob(tcpat):
                if p.is_file() and os.access(str(p), os.X_OK):
                    self.tcexe = p.resolve()
                    break
            if not self.tcexe:
                raise InitError('No THERMOCALC executable in working directory.')
            # DRAWPD exe
            self.drexe = None
            for p in self.workdir.glob(drpat):
                if p.is_file() and os.access(str(p), os.X_OK):
                    self.drexe = p.resolve()
                    break
            #if not self.drexe:
            #    InitError('No drawpd executable in working directory.')
            # tc-prefs file
            if not self.workdir.joinpath('tc-prefs.txt').exists():
                raise InitError('No tc-prefs.txt file in working directory.')
            errinfo = 'tc-prefs.txt file in working directory cannot be accessed.'
            for line in self.workdir.joinpath('tc-prefs.txt').open('r', encoding=self.TCenc):
                kw = line.split()
                if kw != []:
                    if kw[0] == 'scriptfile':
                        self.name = kw[1]
                        if not self.scriptfile.exists():
                            raise InitError('tc-prefs: scriptfile tc-' + self.name + '.txt does not exists in your working directory.')
                    if kw[0] == 'calcmode':
                        if kw[1] != '1':
                            raise InitError('tc-prefs: calcmode must be 1.')

            errinfo = 'Scriptfile error!'
            self.excess = set()
            self.trange = (200., 1000.)
            self.prange = (0.1, 20.)
            check = {'axfile': False, 'setbulk': False, 'printbulkinfo': False,
                     'setexcess': False, 'printxyz': False}
            errinfo = 'Check your scriptfile.'
            with self.scriptfile.open('r', encoding=self.TCenc) as f:
                lines = f.readlines()
            gsb, gse = False, False
            dgb, dge = False, False
            for line in lines:
                kw = line.split('%')[0].split()
                if '{PSBGUESS-BEGIN}' in line:
                    gsb = True
                if '{PSBGUESS-END}' in line:
                    gse = True
                if '{PSBDOGMIN-BEGIN}' in line:
                    dgb = True
                if '{PSBDOGMIN-END}' in line:
                    dge = True
                if kw == ['*']:
                    break
                if kw:
                    if kw[0] == 'axfile':
                        errinfo = 'Wrong argument for axfile keyword in scriptfile.'
                        self.axname = kw[1]
                        if not self.axfile.exists():
                            raise ScriptfileError('Axfile ' + str(self.axfile) + ' does not exists in working directory')
                        check['axfile'] = True
                    elif kw[0] == 'setdefTwindow':
                        errinfo = 'Wrong arguments for setdefTwindow keyword in scriptfile.'
                        self.trange = (float(kw[-2]), float(kw[-1]))
                    elif kw[0] == 'setdefPwindow':
                        errinfo = 'Wrong arguments for setdefPwindow keyword in scriptfile.'
                        self.prange = (float(kw[-2]), float(kw[-1]))
                    elif kw[0] == 'setbulk':
                        errinfo = 'Wrong arguments for setbulk keyword in scriptfile.'
                        self.bulk = kw[1:]
                        if 'yes' in self.bulk:
                            self.bulk.remove('yes')
                        check['setbulk'] = True
                    elif kw[0] == 'setexcess':
                        errinfo = 'Wrong argument for setexcess keyword in scriptfile.'
                        self.excess = set(kw[1:])
                        if 'yes' in self.excess:
                            self.excess.remove('yes')
                        if 'no' in self.excess:
                            self.excess = set()
                        if 'ask' in self.excess:
                            raise ScriptfileError('Setexcess must not be set to ask.')
                        check['setexcess'] = True
                    elif kw[0] == 'calctatp':
                        errinfo = 'Wrong argument for calctatp keyword in scriptfile.'
                        if not kw[1] == 'ask':
                            raise ScriptfileError('Calctatp must be set to ask.')
                    # elif kw[0] == 'drawpd':
                    #     errinfo = 'Wrong argument for drawpd keyword in scriptfile.'
                    #     if kw[1] == 'no':
                    #         raise ScriptfileError('Drawpd must be set to yes.')
                    #     check['drawpd'] = True
                    elif kw[0] == 'printbulkinfo':
                        errinfo = 'Wrong argument for printbulkinfo keyword in scriptfile.'
                        if kw[1] == 'no':
                            raise ScriptfileError('Printbulkinfo must be set to yes.')
                        check['printbulkinfo'] = True
                    elif kw[0] == 'printxyz':
                        errinfo = 'Wrong argument for printxyz keyword in scriptfile.'
                        if kw[1] == 'no':
                            raise ScriptfileError('Printxyz must be set to yes.')
                        check['printxyz'] = True
                    elif kw[0] == 'dogmin':
                        errinfo = 'Wrong argument for dogmin keyword in scriptfile.'
                        if not kw[1] == 'no':
                            raise ScriptfileError('Dogmin must be set to no.')
                    elif kw[0] == 'fluidpresent':
                        raise ScriptfileError('Fluidpresent must be deleted from scriptfile.')
                    elif kw[0] == 'seta':
                        errinfo = 'Wrong argument for seta keyword in scriptfile.'
                        if not kw[1] == 'no':
                            raise ScriptfileError('Seta must be set to no.')
                    elif kw[0] == 'setmu':
                        errinfo = 'Wrong argument for setmu keyword in scriptfile.'
                        if not kw[1] == 'no':
                            raise ScriptfileError('Setmu must be set to no.')
                    elif kw[0] == 'usecalcq':
                        errinfo = 'Wrong argument for usecalcq keyword in scriptfile.'
                        if kw[1] == 'ask':
                            raise ScriptfileError('Usecalcq must be yes or no.')
                    elif kw[0] == 'pseudosection':
                        errinfo = 'Wrong argument for pseudosection keyword in scriptfile.'
                        if kw[1] == 'ask':
                            raise ScriptfileError('Pseudosection must be yes or no.')
                    elif kw[0] == 'zeromodeiso':
                        errinfo = 'Wrong argument for zeromodeiso keyword in scriptfile.'
                        if not kw[1] == 'yes':
                            raise ScriptfileError('Zeromodeiso must be set to yes.')
                    elif kw[0] == 'setmodeiso':
                        errinfo = 'Wrong argument for setmodeiso keyword in scriptfile.'
                        if not kw[1] == 'yes':
                            raise ScriptfileError('Setmodeiso must be set to yes.')
                    elif kw[0] == 'convliq':
                        raise ScriptfileError('Convliq not yet supported.')
                    elif kw[0] == 'setiso':
                        errinfo = 'Wrong argument for setiso keyword in scriptfile.'
                        if kw[1] != 'no':
                            raise ScriptfileError('Setiso must be set to no.')

            if not check['axfile']:
                raise ScriptfileError('Axfile name must be provided in scriptfile.')
            if not check['setbulk']:
                raise ScriptfileError('Setbulk must be provided in scriptfile.')
            if not check['setexcess']:
                raise ScriptfileError('Setexcess must not be set to ask. To suppress this error put empty setexcess keyword to your scriptfile.')
            # if not check['drawpd']:
            #     raise ScriptfileError('Drawpd must be set to yes. To suppress this error put drawpd yes keyword to your scriptfile.')
            if not check['printbulkinfo']:
                raise ScriptfileError('Printbulkinfo must be set to yes. To suppress this error put printbulkinfo yes keyword to your scriptfile.')
            if not check['printxyz']:
                raise ScriptfileError('Printxyz must be set to yes. To suppress this error put printxyz yes keyword to your scriptfile.')
            if not (gsb and gse):
                raise ScriptfileError('There are not {PSBGUESS-BEGIN} and {PSBGUESS-END} tags in your scriptfile.')
            if not (dgb and dge):
                raise ScriptfileError('There are not {PSBDOGMIN-BEGIN} and {PSBDOGMIN-END} tags in your scriptfile.')

            # TC
            self.tcout = self.runtc('\nkill\n\n')
            if 'BOMBED' in self.tcout:
                raise TCError(self.tcout.split('BOMBED')[1].split('\n')[0])
            else:
                self.phases = self.tcout.split('choose from:')[1].split('\n')[0].split()
                self.phases.sort()
                self.deftrange = self.trange
                self.defprange = self.prange
            # OK
            self.status = 'Initial check done.'
            self.OK = True
        except BaseException as e:
            if isinstance(e, InitError) or isinstance(e, ScriptfileError) or isinstance(e, TCError):
                self.status = '{}: {}'.format(type(e).__name__, str(e))
            else:
                self.status = '{}: {} {}'.format(type(e).__name__, str(e), errinfo)
            self.OK = False

    def __str__(self):
        return str(self.workdir)

    def __repr__(self):
        return '\n'.join(['THERMOCALC API',
                          '==============',
                          'Working directory: {}'.format(self.workdir),
                          'TC version: {}'.format(self.tcversion),
                          'Scriptfile: {}'.format('tc-' + self.name + '.txt'),
                          'AX file: {}'.format('tc-' + self.axname + '.txt'),
                          'Status: {}'.format(self.status)])

    @property
    def scriptfile(self):
        return self.workdir.joinpath('tc-' + self.name + '.txt')

    @property
    def drfile(self):
        return self.workdir.joinpath('tc-' + self.name + '-dr.txt')

    @property
    def logfile(self):
        return self.workdir.joinpath('tc-log.txt')

    @property
    def icfile(self):
        return self.workdir.joinpath('tc-' + self.name + '-ic.txt')

    @property
    def itfile(self):
        return self.workdir.joinpath('tc-' + self.name + '-it.txt')

    @property
    def ofile(self):
        return self.workdir.joinpath('tc-' + self.name + '-o.txt')

    @property
    def csvfile(self):
        return self.workdir.joinpath('tc-' + self.name + '-csv.txt')

    @property
    def drawpdfile(self):
        return self.workdir.joinpath('dr-' + self.name + '.txt')

    @property
    def axfile(self):
        return self.workdir.joinpath('tc-' + self.axname + '.txt')

    @property
    def prefsfile(self):
        return self.workdir.joinpath('tc-prefs.txt')

    @property
    def tcversion(self):
        return self.tcout.split('\n')[0]

    @property
    def tcnewversion(self):
        return not float(self.tcversion.split()[1]) < 3.5

    @property
    def datasetfile(self):
        return self.workdir.joinpath(self.tcout.split('using ')[1].split(' produced')[0])

    @property
    def dataset(self):
        return self.tcout.split('using ')[1].split('\n')[0]

    def parse_logfile(self, **kwargs):
        # coomon api for logfile parsing
        if self.tcnewversion:
            return self.parse_logfile_new()
        else:
            return self.parse_logfile_old(output=kwargs.get('output', None))

    def parse_logfile_new(self):
        # res is list of dicts with data and ptguess keys
        # data is dict with keys ['axvars', 'sitefractions', 'oxides', 'modes', 'factors', 'tdprops', 'mu', 'endmembers']
        # axvar and sitefractions contains keys of compound phases
        # oxides contains keys of all phases plus 'bulk'
        # modes contains keys of all phases
        # factors contains keys of all phases
        # tdprops contains keys of all phases plus 'sys'
        # mu contains keys of all phases compunds, e.g g(alm) for compund phase and q for simple phase
        # endmembers contains keys of all non-simple phases compunds, e.g. g(py)
        with self.logfile.open('r', encoding=self.TCenc) as f:
            output = f.read()
        lines = [ln for ln in output.splitlines() if ln != '']
        pts = []
        res = []
        alldata = []
        ptguesses = []
        variance = -1
        # parse p, t from something 'g ep mu pa bi chl ab q H2O sph  {4.0000, 495.601}  kbar/°C\novar = 3; var = 1 (seen)'
        ptpat = re.compile('(?<=\{)(.*?)(?=\})')
        #ovarpat = re.compile('(?<=ovar = )(.*?)(?=\;)')
        varpat = re.compile('(?<=var = )(.*?)(?=\ )')
        if not self.icfile.exists():
            if [ix for ix, ln in enumerate(lines) if 'BOMBED' in ln]:
                status = 'bombed'
            else:
                status = 'nir'
        else:
            # parse ptguesses
            bstarts = [ix for ix, ln in enumerate(lines) if ln.startswith(' P(kbar)')]
            bstarts.append(len(lines))
            for bs, be in zip(bstarts[:-1], bstarts[1:]):
                block = lines[bs:be]
                # pts.append([float(n) for n in block[1].split()[:2]])
                xyz = [ix for ix, ln in enumerate(block) if ln.startswith('xyzguess')]
                gixs = [ix for ix, ln in enumerate(block) if ln.startswith('ptguess')][0] - 3
                gixe = xyz[-1] + 2
                ptguesses.append(block[gixs:gixe])
            # parse icfile
            with self.icfile.open('r', encoding=self.TCenc) as f:
                icfile = f.read()
            for block in icfile.split('\n===========================================================\n\n')[1:]:
                sections = block.split('\n\n')
                ic = {}
                pts.append([float(n) for n in ptpat.search(sections[0]).group().split(', ')])
                variance = int(varpat.search(sections[0]).group().replace(';', ''))
                #seenvariance = int(varpat.search(sections[0]).group())
                # parse a-x variables
                ax = {}
                lns = sections[1].split('\n')
                for l1, l2 in zip(lns[::2], lns[1::2]):
                    phase, l1r = l1.split(maxsplit=1)
                    axp = {}
                    for cc, vv in zip(l1r.split(), l2.split()):
                        axp[cc] = float(vv)
                    ax[phase] = axp
                # parse site fractions
                sf = {}
                lns = sections[2].split('\n')[1:]
                for l1, l2 in zip(lns[::2], lns[1::2]):
                    phase, l1r = l1.split(maxsplit=1)
                    sfp = {}
                    for cc, vv in zip(l1r.split(), l2.split()):
                        sfp[cc] = float(vv)
                    sf[phase] = sfp
                # parse oxides
                ox = {}
                l1, l2 = sections[3].split('\n')[1:]
                ccs = l1.split()
                nccs = len(ccs)
                bulk = {}
                for cc, vv in zip(ccs, l2.split()[1:nccs+1]):
                    bulk[cc] = float(vv)
                ox['bulk'] = bulk
                for ln in sections[4].split('\n'):
                    oxp = {}
                    phase, lnr = ln.split(maxsplit=1)
                    for cc, vv in zip(ccs, lnr.split()):
                        oxp[cc] = float(vv)
                    ox[phase] = oxp
                # parse mode
                mode = {}
                l1, l2 = sections[5].split('\n')
                for cc, vv in zip(l1.split()[1:], l2.split()):
                    mode[cc] = float(vv)
                # parse factor
                factor = {}
                l1, l2 = sections[6].split('\n')
                for cc, vv in zip(l1.split()[1:], l2.split()):
                    factor[cc] = float(vv)
                # parse thermodynamic properties
                tdp = {}
                props, lr = sections[7].split('\n', maxsplit=1)
                for ln in lr.split('\n'):
                    tdpp = {}
                    phase, lnr = ln.split(maxsplit=1)
                    for cc, vv in zip(props.split(), lnr.split()):
                        tdpp[cc] = float(vv)
                    tdp[phase] = tdpp
                    # sys
                    tdpp = {}
                    phase, lnr = sections[8].split(maxsplit=1)
                    for cc, vv in zip(props.split(), lnr.split()):
                        tdpp[cc] = float(vv)
                    tdp[phase] = tdpp
                # parse endmembers and chemical potential
                mu = {}
                em = {}
                props = ['ideal', 'gamma', 'activity', 'prop', 'mu', 'RTlna']
                for section in sections[9:-1]:
                    lns = [ln for ln in section.split('\n') if ln != '                    ideal       gamma    activity        prop          µ0     RT ln a']
                    phase, lnr = lns[0].split(maxsplit=1)
                    lns[0] = lnr
                    for ln in lns:
                        phase_em, lnr = ln.split(maxsplit=1)
                        emp = {}
                        for cc, vv in zip(props, lnr.split()):
                            if cc == 'mu':
                                mu['{}({})'.format(phase, phase_em)] = float(vv)
                            else:
                                emp[cc] = float(vv)
                        em['{}({})'.format(phase, phase_em)] = emp
                for ln in sections[-1].split('\n')[:-1]:
                    phase, vv = ln.split()
                    mu[phase] = float(vv)
                alldata.append(dict(axvars=ax, sitefractions=sf, oxides=ox, modes=mode,
                                 factors=factor, tdprops=tdp, mu=mu, endmembers=em))

            res = [dict(data=data, ptguess=ptguess) for data, ptguess in zip(alldata, ptguesses)]
            if res:
                status = 'ok'
            else:
                status = 'nir'
        return status, variance, np.array(pts).T, res, output

    def parse_logfile_old(self, output=None):
        # res is list of dicts with data and ptguess keys
        # data is dict with keys of phases and each contain dict of values
        # res[0]['data']['g']['mode']
        # res[0]['data']['g']['z']
        # res[0]['data']['g']['MnO']
        if output is None:
            with self.logfile.open('r', encoding=self.TCenc) as f:
                output = f.read()
        lines = [''.join([c for c in ln if ord(c) < 128]) for ln in output.splitlines() if ln != '']
        pts = []
        res = []
        variance = -1
        if [ix for ix, ln in enumerate(lines) if 'BOMBED' in ln]:
            status = 'bombed'
        else:
            for ln in lines:
                if 'variance of required equilibrium' in ln:
                    variance = int(ln[ln.index('(') + 1:ln.index('?')])
                    break
            bstarts = [ix for ix, ln in enumerate(lines) if ln.startswith(' P(kbar)')]
            bstarts.append(len(lines))
            for bs, be in zip(bstarts[:-1], bstarts[1:]):
                block = lines[bs:be]
                pts.append([float(n) for n in block[1].split()[:2]])
                xyz = [ix for ix, ln in enumerate(block) if ln.startswith('xyzguess')]
                gixs = [ix for ix, ln in enumerate(block) if ln.startswith('ptguess')][0] - 3
                gixe = xyz[-1] + 2
                ptguess = block[gixs:gixe]
                data = {}
                rbix = [ix for ix, ln in enumerate(block) if ln.startswith('rbi yes')][0]
                phases = block[rbix - 1].split()[1:]
                for phase, val in zip(phases, block[rbix].split()[2:]):
                    data[phase] = dict(mode=float(val))
                for ix in xyz:
                    lbl = block[ix].split()[1]
                    phase, comp = lbl[lbl.find('(') + 1:lbl.find(')')], lbl[:lbl.find('(')]
                    if phase not in data:
                        raise Exception('Check model {} in your ax file. Commonly liq coded as L for starting guesses.'.format(phase))
                    data[phase][comp] = float(block[ix].split()[2])
                rbiox = block[rbix + 1].split()[2:]
                for delta in range(len(phases)):
                    rbi = {c: float(v) for c, v in zip(rbiox, block[rbix + 2 + delta].split()[2:-2])}
                    rbi['H2O'] = float(block[rbix + 2 + delta].split()[1])
                    # data[phases[delta]]['rbi'] = comp
                    data[phases[delta]].update(rbi)
                res.append(dict(data=data, ptguess=ptguess))
            if res:
                status = 'ok'
            else:
                status = 'nir'
        return status, variance, np.array(pts).T, res, output

    def parse_dogmin(self):
        try:
            with self.icfile.open('r', encoding=self.TCenc) as f:
                resic = f.read()
            with self.logfile.open('r', encoding=self.TCenc) as f:
                output = f.read()
            res = output.split('##########################################################\n')[-1]
        except:
            res = None
            resic = None
        return res, resic

    def update_scriptfile(self, **kwargs):
        # Store scriptfile content and initialize dicts
        guesses = kwargs.get('guesses', None)
        get_old_guesses = kwargs.get('get_old_guesses', False)
        dogmin = kwargs.get('dogmin', None) # None or 'no' or 'yes 1'
        which = kwargs.get('which', None)
        p = kwargs.get('p', None)
        T = kwargs.get('T', None)
        with self.scriptfile.open('r', encoding=self.TCenc) as f:
            sc = f.readlines()
        changed = False
        gsb = [ix for ix, ln in enumerate(sc) if ln.startswith('%{PSBGUESS-BEGIN}')]
        gse = [ix for ix, ln in enumerate(sc) if ln.startswith('%{PSBGUESS-END}')]
        if get_old_guesses:
            if gsb and gse:
                old_guesses = sc[gsb[0] + 1:gse[0]]
        if guesses is not None:
            if gsb and gse:
                sc = sc[:gsb[0] + 1] + [gln + '\n' for gln in guesses] + sc[gse[0]:]
                changed = True
        if dogmin is not None:
            dgb = [ix for ix, ln in enumerate(sc) if ln.startswith('%{PSBDOGMIN-BEGIN}')]
            dge = [ix for ix, ln in enumerate(sc) if ln.startswith('%{PSBDOGMIN-END}')]
            dglines = []
            dglines.append('dogmin {}\n'.format(dogmin))
            if which is not None:
                dglines.append('which {}\n'.format(' '.join(which)))
                dglines.append('setPwindow {} {}\n'.format(p, p))
                dglines.append('setTwindow {} {}\n'.format(T, T))
            if dgb and dge:
                sc = sc[:dgb[0] + 1] + dglines + sc[dge[0]:]
                changed = True
        if changed:
            with self.scriptfile.open('w', encoding=self.TCenc) as f:
                for ln in sc:
                    f.write(ln)
        if get_old_guesses:
            return old_guesses
        else:
            return None

    def parse_kwargs(self, **kwargs):
        prange = kwargs.get('prange', self.prange)
        trange = kwargs.get('trange', self.trange)
        steps = kwargs.get('steps', 50)
        prec = kwargs.get('prec', max(int(2 - np.floor(np.log10(min(np.diff(trange)[0], np.diff(prange)[0])))), 0) + 1)
        return prange, trange, steps, prec

    def tc_calc_t(self, phases, out, **kwargs):
        prange, trange, steps, prec = self.parse_kwargs(**kwargs)
        step = (prange[1] - prange[0]) / steps
        tmpl = '{}\n\n{}\ny\n{:.{prec}f} {:.{prec}f}\n{:.{prec}f} {:.{prec}f}\n{:g}\nn\n\nkill\n\n'
        ans = tmpl.format(' '.join(phases), ' '.join(out), *prange, *trange, step, prec=prec)
        tcout = self.runtc(ans)
        return tcout, ans

    def tc_calc_p(self, phases, out, **kwargs):
        prange, trange, steps, prec = self.parse_kwargs(**kwargs)
        step = (trange[1] - trange[0]) / steps
        tmpl = '{}\n\n{}\nn\n{:.{prec}f} {:.{prec}f}\n{:.{prec}f} {:.{prec}f}\n{:g}\nn\n\nkill\n\n'
        ans = tmpl.format(' '.join(phases), ' '.join(out), *trange, *prange, step, prec=prec)
        tcout = self.runtc(ans)
        return tcout, ans

    def tc_calc_pt(self, phases, out, **kwargs):
        prange, trange, steps, prec = self.parse_kwargs(**kwargs)
        tmpl = '{}\n\n{}\n{:.{prec}f} {:.{prec}f} {:.{prec}f} {:.{prec}f}\nn\n\nkill\n\n'
        ans = tmpl.format(' '.join(phases), ' '.join(out), *trange, *prange, prec=prec)
        tcout = self.runtc(ans)
        return tcout, ans

    def tc_calc_assemblage(self, phases, p, t):
        tmpl = '{}\n\n\n{}\n{}\nkill\n\n'
        ans = tmpl.format(' '.join(phases), p, t)
        tcout = self.runtc(ans)
        return tcout, ans

    def tc_dogmin(self, variance):
        tmpl = '{}\nn\n\n'
        ans = tmpl.format(variance)
        tcout = self.runtc(ans)
        return tcout

    def runtc(self, instr):
        if sys.platform.startswith('win'):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags = 1
            startupinfo.wShowWindow = 0
        else:
            startupinfo = None
        p = subprocess.Popen(str(self.tcexe), cwd=str(self.workdir), startupinfo=startupinfo, **popen_kw)
        output, err = p.communicate(input=instr.encode(self.TCenc))
        if err is not None:
            print(err.decode('utf-8'))
        sys.stdout.flush()
        return output.decode(self.TCenc)

    def rundr(self):
        if self.drexe:
            instr = self.name + '\n'
            if sys.platform.startswith('win'):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags = 1
                startupinfo.wShowWindow = 0
            else:
                startupinfo = None
            p = subprocess.Popen(str(self.drexe), cwd=str(self.workdir), startupinfo=startupinfo, **popen_kw)
            p.communicate(input=instr.encode(self.TCenc))
            sys.stdout.flush()
            return True
        else:
            return False


def inv_on_uni(uphases, uout, iphases, iout):
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
        if poly.issubset(iphases) and poly !=iout and not iout.isdisjoint(poly):
            fixi = True
            if poly.issubset(uphases) and not uout.isdisjoint(poly):
                fixu = True
            break
    # check invs
    candidate = checkme(uphases, uout, iphases, iout)
    if fixi and not candidate:
        candidate = checkme(uphases, uout, iphases, iout.difference(poly).union(poly.difference(iout)))
    if fixu and not candidate:
        candidate = checkme(uphases, poly.difference(uout), iphases, iout)
    return candidate

def eval_expr(expr, dt):
    def eval_(node):
        if isinstance(node, ast.Num):  # number
            return node.n
        if isinstance(node, ast.Name):  # variable
            return dt[node.id]
        elif isinstance(node, ast.BinOp):  # <left> <operator> <right>
            return ops[type(node.op)](eval_(node.left), eval_(node.right))
        elif isinstance(node, ast.UnaryOp):  # <operator> <operand> e.g., -1
            return ops[type(node.op)](eval_(node.operand))
        else:
            raise TypeError(node)
    ops = {ast.Add: np.add, ast.Sub: np.subtract,
           ast.Mult: np.multiply, ast.Div: np.divide,
           ast.Pow: np.power}
    return eval_(ast.parse(expr, mode='eval').body)

def label_line(ax, line, label, color='0.5', fs=14, halign='left'):
    """Add an annotation to the given line with appropriate placement and rotation.
    Based on code from:
        [How to rotate matplotlib annotation to match a line?]
        (http://stackoverflow.com/a/18800233/230468)
        User: [Adam](http://stackoverflow.com/users/321772/adam)
    Arguments
    ---------
    ax : `matplotlib.axes.Axes` object
        Axes on which the label should be added.
    line : `matplotlib.lines.Line2D` object
        Line which is being labeled.
    label : str
        Text which should be drawn as the label.
    ...
    Returns
    -------
    text : `matplotlib.text.Text` object
    """
    xdata, ydata = line.get_data()
    x1 = xdata[0]
    x2 = xdata[-1]
    y1 = ydata[0]
    y2 = ydata[-1]

    if halign.startswith('l'):
        xx = x1
        halign = 'left'
    elif halign.startswith('r'):
        xx = x2
        halign = 'right'
    elif halign.startswith('c'):
        xx = 0.5*(x1 + x2)
        halign = 'center'
    else:
        raise ValueError("Unrecogznied `halign` = '{}'.".format(halign))

    yy = np.interp(xx, xdata, ydata)

    ylim = ax.get_ylim()
    # xytext = (10, 10)
    xytext = (0, 0)
    text = ax.annotate(label, xy=(xx, yy), xytext=xytext, textcoords='offset points',
                       size=fs, color=color, zorder=1,
                       horizontalalignment=halign, verticalalignment='center_baseline')

    return text
