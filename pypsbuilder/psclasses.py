"""
Base classes of pypsbuilder
"""
# author: Ondrej Lexa
# website: petrol.natur.cuni.cz/~ondro

import sys
import os
try:
    import cPickle as pickle
except ImportError:
    import pickle
import gzip
import subprocess
import itertools
import re
from pathlib import Path
from collections import OrderedDict

import numpy as np
import matplotlib.pyplot as plt
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


class TCAPI(object):
    """Class to access TC functionality in given working directory.

    Retrieves rows pertaining to the given keys from the Table instance
    represented by big_table.  Silly things may happen if
    other_silly_variable is not None.

    Args:
        big_table: An open Bigtable Table instance.
        keys: A sequence of strings representing the key of each table row
            to fetch.
        other_silly_variable: Another optional variable, that has a much
            longer name than the other args, and which does nothing.

    Returns:
        A dict mapping keys to the corresponding table row data
        fetched. Each row is represented as a tuple of strings. For
        example:

        {'Serak': ('Rigel VII', 'Preparer'),
         'Zim': ('Irk', 'Invader'),
         'Lrrr': ('Omicron Persei 8', 'Emperor')}

        If a key from the keys argument is missing from the dictionary,
        then that row was not found in the table.

    Raises:
        InitError: An error occurred accessing the bigtable.Table object.
        ScriptfileError: sdsdsdsd.
        TCError: wdwdwd.

    """
    def __init__(self, workdir, tcexe=None, drexe=None):
        self.workdir = Path(workdir).resolve()
        self.TCenc = 'mac-roman'
        try:
            errinfo = 'Initialize project error!'
            self.tcexe = None
            self.drexe = None
            if tcexe is not None:
                self.tcexe = self.workdir / tcexe
            if drexe is not None:
                self.drexe = self.workdir / drexe
            if self.tcexe is None:
                # default exe
                if sys.platform.startswith('win'):
                    tcpat = 'tc3*.exe'
                else:
                    tcpat = 'tc3*'
                # THERMOCALC exe
                for p in self.workdir.glob(tcpat):
                    if p.is_file() and os.access(str(p), os.X_OK):
                        self.tcexe = p.resolve()
                        break
            if self.drexe is None:
                # default exe
                if sys.platform.startswith('win'):
                    drpat = 'dr1*.exe'
                else:
                    drpat = 'dr1*'
                # DRAWPD exe
                for p in self.workdir.glob(drpat):
                    if p.is_file() and os.access(str(p), os.X_OK):
                        self.drexe = p.resolve()
                        break
            if not self.tcexe:
                raise InitError('No THERMOCALC executable in working directory.')
            #if not self.drexe:
                #InitError('No drawpd executable in working directory.')
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
            self.bulk = []
            self.ptx_steps = 20
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
                        bulk = kw[1:]
                        if 'yes' in bulk:
                            bulk.remove('yes')
                        if len(self.bulk) == 1:
                            if len(self.bulk[0]) < len(bulk):
                                self.ptx_steps = int(bulk[-1]) - 1
                                bulk = bulk[:-1]
                        self.bulk.append(bulk)
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
        return '\n'.join(['{}'.format(self.tcversion),
                          'Working directory: {}'.format(self.workdir),
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
        # common api for logfile parsing
        if self.tcnewversion:
            return self.parse_logfile_new(**kwargs)
        else:
            return self.parse_logfile_old(output=kwargs.get('output', None))

    def parse_logfile_new(self, **kwargs):
        # res is list of dicts with data and ptguess keys
        # data is dict with keys ['axvars', 'sitefractions', 'oxides', 'modes', 'factors', 'tdprops', 'mu', 'endmembers']
        # axvar and sitefractions contains keys of compound phases
        # oxides contains keys of all phases plus 'bulk'
        # modes contains keys of all phases
        # factors contains keys of all phases
        # tdprops contains keys of all phases plus 'sys'
        # mu contains keys of all phases compunds, e.g g(alm) for compund phase and q for simple phase
        # endmembers contains keys of all non-simple phases compunds, e.g. g(py)
        tx = kwargs.get('tx', False)
        with self.logfile.open('r', encoding=self.TCenc) as f:
            output = f.read()
        lines = [ln for ln in output.splitlines() if ln != '']
        pts = []
        res = []
        headers = []
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
            ptguesses = []
            for bs, be in zip(bstarts[:-1], bstarts[1:]):
                block = lines[bs:be]
                # pts.append([float(n) for n in block[1].split()[:2]])
                xyz = [ix for ix, ln in enumerate(block) if ln.startswith('xyzguess')]
                gixs = [ix for ix, ln in enumerate(block) if ln.startswith('ptguess')][0] - 3
                gixe = xyz[-1] + 2
                ptguesses.append(block[gixs:gixe])
            # parse icfile
            alldata = []
            with self.icfile.open('r', encoding=self.TCenc) as f:
                icfile = f.read()
            for block in icfile.split('\n===========================================================\n\n')[1:]:
                sections = block.split('\n\n')
                data = {}
                pts.append([float(n) for n in ptpat.search(sections[0]).group().split(', ')])
                variance = int(varpat.search(sections[0]).group().replace(';', ''))
                #seenvariance = int(varpat.search(sections[0]).group())
                # parse mode
                l1, l2 = sections[5].split('\n')
                if tx:
                    for phase, vv in zip(l1.split()[1:], l2.split()[1:]):
                        dt = data.get(phase, {})
                        dt['mode'] = float(vv)
                        data[phase] = dt
                else:
                    for phase, vv in zip(l1.split()[1:], l2.split()):
                        dt = data.get(phase, {})
                        dt['mode'] = float(vv)
                        data[phase] = dt
                # parse a-x variables
                lns = sections[1].split('\n')
                for l1, l2 in zip(lns[::2], lns[1::2]):
                    phase, l1r = l1.split(maxsplit=1)
                    axp = {}
                    for cc, vv in zip(l1r.split(), l2.split()):
                        axp[cc.replace('({})'.format(phase), '')] = float(vv)
                    dt = data.get(phase, {})
                    dt.update(axp)
                    data[phase] = dt
                # parse site fractions
                lns = sections[2].split('\n')[1:]
                for l1, l2 in zip(lns[::2], lns[1::2]):
                    phase, l1r = l1.split(maxsplit=1)
                    sfp = {}
                    for cc, vv in zip(l1r.split(), l2.split()):
                        sfp[cc] = float(vv)
                    dt = data.get(phase, {})
                    dt.update(sfp)
                    data[phase] = dt
                # parse oxides
                l1, l2 = sections[3].split('\n')[1:]
                ccs = l1.split()
                nccs = len(ccs)
                bulk = {}
                for cc, vv in zip(ccs, l2.split()[1:nccs+1]):
                    bulk[cc] = float(vv)
                data['bulk'] = bulk
                for ln in sections[4].split('\n'):
                    oxp = {}
                    phase, lnr = ln.split(maxsplit=1)
                    for cc, vv in zip(ccs, lnr.split()):
                        oxp[cc] = float(vv)
                    dt = data.get(phase, {})
                    dt.update(oxp)
                    data[phase] = dt
                # parse factor
                l1, l2 = sections[6].split('\n')
                if tx:
                    for phase, vv in zip(l1.split()[1:], l2.split()[1:]):
                        dt = data.get(phase, {})
                        dt.update(dict(factor=float(vv)))
                        data[phase] = dt
                else:
                    for phase, vv in zip(l1.split()[1:], l2.split()):
                        dt = data.get(phase, {})
                        dt.update(dict(factor=float(vv)))
                        data[phase] = dt
                # parse thermodynamic properties
                props, lr = sections[7].split('\n', maxsplit=1)
                for ln in lr.split('\n'):
                    tdpp = {}
                    phase, lnr = ln.split(maxsplit=1)
                    for cc, vv in zip(props.split(), lnr.split()):
                        tdpp[cc] = float(vv)
                    dt = data.get(phase, {})
                    dt.update(tdpp)
                    data[phase] = dt
                # sys
                tdps = {}
                header, lnr = sections[8].split(maxsplit=1)
                for cc, vv in zip(props.split(), lnr.split()):
                    tdps[cc] = float(vv)
                dt = data.get('sys', {})
                dt.update(tdps)
                data['sys'] = dt
                if tx:
                    headers.append(float(header))
                # parse endmembers and chemical potential
                props = ['ideal', 'gamma', 'activity', 'prop', 'mu', 'RTlna']
                for section in sections[9:-1]:
                    lns = [ln for ln in section.split('\n') if ln != '                    ideal       gamma    activity        prop          µ0     RT ln a']
                    phase, lnr = lns[0].split(maxsplit=1)
                    lns[0] = lnr
                    for ln in lns:
                        phase_em, lnr = ln.split(maxsplit=1)
                        emp = {}
                        for cc, vv in zip(props, lnr.split()):
                            emp[cc] = float(vv)
                        phase_comb = '{}({})'.format(phase, phase_em)
                        dt = data.get(phase_comb, {})
                        dt.update(emp)
                        data[phase_comb] = dt
                for ln in sections[-1].split('\n')[:-1]:
                    phase, vv = ln.split()
                    dt = data.get(phase, {})
                    dt.update(dict(mu=float(vv)))
                    data[phase] = dt
                alldata.append(data)
            res = [dict(data=data, ptguess=ptguess) for data, ptguess in zip(alldata, ptguesses)]
            if res:
                status = 'ok'
            else:
                status = 'nir'
        if tx:
            if status == 'ok':
                comps = [ix for ix, ln in enumerate(lines) if ln.startswith('composition (from script)')][0]
                steps = int(lines[comps + 1].split()[-1]) - 1
                txcoords = np.array(((np.array(headers) - 1) / steps, np.array(pts).T[1]))
            else:
                txcoords = None
            return status, variance, txcoords, np.array(pts).T, res, output
        else:
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
                old_guesses = [ln.strip() for ln in sc[gsb[0] + 1:gse[0]]]
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

    def update_ptxsteps(self, steps=None):
        with self.scriptfile.open('r', encoding=self.TCenc) as f:
            sc = f.readlines()
        bix = [ix for ix, ln in enumerate(sc) if ln.strip().startswith('setbulk')]
        changed = False
        if len(bix) == 2:
            bulk1 = sc[bix[0]].split('%')[0].split()[1:]
            nox1 = len(bulk1)
            if 'yes' in bulk1:
                nox1 -= 1
            oparts = sc[bix[1]].split('%')
            bulk2 = oparts[0].split()[1:]
            nox2 = len(bulk2)
            if 'yes' in bulk2:
                nox2 -= 1
            if nox2 > nox1:
                old_steps = int(bulk2[-1])
                if steps is not None:
                    oparts[0] = oparts[0][::-1].split(maxsplit=1)[1][::-1] + ' ' + str(steps) + ' '
                else:
                    oparts[0] = oparts[0][::-1].split(maxsplit=1)[1][::-1] + ' '
            else:
                old_steps = 20
                if steps is not None:
                    oparts[0] = oparts[0] + str(steps) + ' '
            sc[bix[1]] = '%'.join(oparts)
            if steps is not None:
                if steps != old_steps:
                    with self.scriptfile.open('w', encoding=self.TCenc) as f:
                        for ln in sc:
                            f.write(ln)
                    changed = True
            return old_steps, changed
        else:
            return None, changed

    def parse_kwargs(self, **kwargs):
        prange = kwargs.get('prange', self.prange)
        trange = kwargs.get('trange', self.trange)
        steps = kwargs.get('steps', 50)
        if np.diff(prange)[0] < 0.001:
            prec = kwargs.get('prec', max(int(2 - np.floor(np.log10(np.diff(trange)[0]))), 0) + 1)
        elif np.diff(trange)[0] < 0.001:
            prec = kwargs.get('prec', max(int(2 - np.floor(np.log10(np.diff(prange)[0]))), 0) + 1)
        else:
            prec = kwargs.get('prec', max(int(2 - np.floor(np.log10(min(np.diff(trange)[0], np.diff(prange)[0])))), 0) + 1)
        return prange, trange, steps, prec

    def calc_t(self, phases, out, **kwargs):
        prange, trange, steps, prec = self.parse_kwargs(**kwargs)
        step = (prange[1] - prange[0]) / steps
        tmpl = '{}\n\n{}\ny\n{:.{prec}f} {:.{prec}f}\n{:.{prec}f} {:.{prec}f}\n{:g}\nn\n\nkill\n\n'
        ans = tmpl.format(' '.join(phases), ' '.join(out), *prange, *trange, step, prec=prec)
        tcout = self.runtc(ans)
        return tcout, ans

    def calc_p(self, phases, out, **kwargs):
        prange, trange, steps, prec = self.parse_kwargs(**kwargs)
        step = (trange[1] - trange[0]) / steps
        tmpl = '{}\n\n{}\nn\n{:.{prec}f} {:.{prec}f}\n{:.{prec}f} {:.{prec}f}\n{:g}\nn\n\nkill\n\n'
        ans = tmpl.format(' '.join(phases), ' '.join(out), *trange, *prange, step, prec=prec)
        tcout = self.runtc(ans)
        return tcout, ans

    def calc_pt(self, phases, out, **kwargs):
        prange, trange, steps, prec = self.parse_kwargs(**kwargs)
        tmpl = '{}\n\n{}\n{:.{prec}f} {:.{prec}f} {:.{prec}f} {:.{prec}f}\nn\n\nkill\n\n'
        ans = tmpl.format(' '.join(phases), ' '.join(out), *trange, *prange, prec=prec)
        tcout = self.runtc(ans)
        return tcout, ans

    def calc_tx(self, phases, out, **kwargs):
        prange, trange, steps, prec = self.parse_kwargs(**kwargs)
        if len(out) > 1:
            tmpl = '{}\n\n{}\n{:.{prec}f} {:.{prec}f} {:.{prec}f} {:.{prec}f}\nn\n\nkill\n\n'
        else:
            tmpl = '{}\n\n{}\ny\n\n{:.{prec}f} {:.{prec}f}\nn\nkill\n\n'
        ans = tmpl.format(' '.join(phases), ' '.join(out), *trange, *prange, prec=prec)
        tcout = self.runtc(ans)
        return tcout, ans

    def calc_assemblage(self, phases, p, t):
        tmpl = '{}\n\n\n{}\n{}\nkill\n\n'
        ans = tmpl.format(' '.join(phases), p, t)
        tcout = self.runtc(ans)
        return tcout, ans

    def dogmin(self, variance):
        tmpl = '{}\nn\n\n'
        ans = tmpl.format(variance)
        tcout = self.runtc(ans)
        return tcout

    def calc_variance(self, phases):
        variance = None
        tcout = self.tc.runtc('{}\nkill\n\n'.format(' '.join(phases)))
        for ln in tcout.splitlines():
            if 'variance of required equilibrium' in ln:
                variance = int(ln[ln.index('(') + 1:ln.index('?')])
                break
        return variance

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
            print('No drawpd executable identified in working directory.')
            return False


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
        log = []
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
                        log.append('Topology error in path {}. Edges {}'.format(path, edge))
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
        return vertices, edges, phases, tedges, tphases, log

    def create_shapes(self):
        if not isinstance(self, PTsection):
            shrink = 0.0001
        else:
            shrink = 0
        shapes = OrderedDict()
        shape_edges = OrderedDict()
        bad_shapes = OrderedDict()
        ignored_shapes = OrderedDict()
        # traverse pseudosection
        vertices, edges, phases, tedges, tphases, log = self.construct_areas(shrink)
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
                for e1, e2 in itertools.combinations(e, 2):
                    l1 = LineString(np.c_[self.unilines[e1].x, self.unilines[e1].y])
                    l2 = LineString(np.c_[self.unilines[e2].x, self.unilines[e2].y])
                    if l1.crosses(l2):
                        log.append('   - Uniline {} crosses uniline {}'.format(e1, e2))
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
