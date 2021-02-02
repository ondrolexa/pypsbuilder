"""pypsbuilder classes used by builders.

This module contains classes and tools providing API to THERMOCALC, parsing of
outputs and storage of calculated invariant points and univariant lines.

Todo:
    * Implement own class for divariant fields

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
# import itertools
# import re
from pathlib import Path
# from collections import OrderedDict

import numpy as np
import matplotlib.pyplot as plt
from shapely.geometry import LineString, Point
from shapely.ops import polygonize, linemerge   # unary_union

popen_kw = dict(stdout=subprocess.PIPE, stdin=subprocess.PIPE,
                stderr=subprocess.STDOUT, universal_newlines=False)

polymorphs = [{'sill', 'and'}, {'ky', 'and'}, {'sill', 'ky'}, {'q', 'coe'}, {'diam', 'gph'}]
"""list: List of two-element sets containing polymorphs."""


class InitError(Exception):
    pass


class ScriptfileError(Exception):
    pass


class TCError(Exception):
    pass


class TCAPI(object):
    """THERMOCALC working directory API.

    Attributes:
        workdir (pathlib.Path): Path instance pointing to working directory.
        tcexe (pathlib.Path): Path instance pointing to *THERMOCALC* executable.
        drexe (pathlib.Path): Path instance pointing to *dawpd* executable
        name (str): Basename of the project.
        axname (str): Name of a-x file in use.
        OK (bool): Boolean value. True when all settings are correct and
            THERMOCALC is ready to be used by builders.
        excess (set): Set of excess phases from scriptfile.
        trange (tuple): Tuple of temperature window from setdefTwindow
        prange (tuple): Tuple of pressure window from setdefPwindow
        bulk (list): List of bulk composition(s).
        ptx_steps (int): Number of compositional steps for T-X and P-X sections.
        phases (list): List of names of available phases.
        TCenc (str): Encoding used for THERMOCALC output text files.
            Default 'mac-roman'.

    Raises:
        InitError: An error occurred during initialization of working dir.
        ScriptfileError: Error or problem in scriptfile.
        TCError: THERMOCALC bombed.

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
            # if not self.drexe:
            #     InitError('No drawpd executable in working directory.')
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
                    if kw[0] == 'dontwrap':
                        if kw[1] != 'no':
                            raise InitError('tc-prefs: dontwrap must be no.')

            # defaults
            self.ptx_steps = 20  # IS IT NEEDED ????
            # Checks various settings
            errinfo = 'Scriptfile error!'
            with self.scriptfile.open('r', encoding=self.TCenc) as f:
                r = f.read()
            lines = [ln.strip() for ln in r.splitlines() if ln.strip() != '']
            lines = lines[:lines.index('*')]  # remove part not used by TC
            # Check pypsbuilder blocks
            if not ('%{PSBCALC-BEGIN}' in lines and '%{PSBCALC-END}' in lines):
                raise ScriptfileError('There are not {PSBCALC-BEGIN} and {PSBCALC-END} tags in your scriptfile.')
            if not ('%{PSBGUESS-BEGIN}' in lines and '%{PSBGUESS-END}' in lines):
                raise ScriptfileError('There are not {PSBGUESS-BEGIN} and {PSBGUESS-END} tags in your scriptfile.')
            if not ('%{PSBBULK-BEGIN}' in lines and '%{PSBBULK-END}' in lines):
                raise ScriptfileError('There are not {PSBBULK-BEGIN} and {PSBBULK-END} tags in your scriptfile.')
            # Create scripts directory
            scripts = {}
            for ln in lines:
                ln_clean = ln.split('%')[0].strip()
                if ln_clean != '':
                    tokens = ln_clean.split(maxsplit=1)
                    if len(tokens) > 1:
                        if tokens[0] in scripts:
                            scripts[tokens[0]].append(tokens[1].strip())
                        else:
                            scripts[tokens[0]] = [tokens[1].strip()]
                    else:
                        scripts[tokens[0]] = []
            # axfile
            if 'axfile' not in scripts:
                raise ScriptfileError('No axfile script, axfile is mandatory script.')
            errinfo = 'Missing argument for axfile script in scriptfile.'
            self.axname = scripts['axfile'][0]
            if not self.axfile.exists():
                raise ScriptfileError('axfile ' + str(self.axfile) + ' does not exists in working directory')
            # diagramPT
            if 'diagramPT' not in scripts:
                raise ScriptfileError('No diagramPT script, diagramPT is mandatory script.')
            errinfo = 'Wrong arguments for diagramPT script in scriptfile.'
            pmin, pmax, tmin, tmax = scripts['diagramPT'][0].split()
            self.prange = float(pmin), float(pmax)
            self.trange = float(tmin), float(tmax)
            # bulk
            errinfo = 'Wrong bulk in scriptfile.'
            if 'bulk' not in scripts:
                raise ScriptfileError('No bulk script, bulk must be provided.')
            if not (1 < len(scripts['bulk']) < 4):
                raise ScriptfileError('Bulk script must have 2 or 3 lines.')
            self.bulk = []
            self.bulk.append(scripts['bulk'][0].split())
            self.bulk.append(scripts['bulk'][1].split())
            if len(scripts['bulk']) == 3:
                self.bulk.append(scripts['bulk'][2].split()[:len(self.bulk[0])])  # remove possible number of steps
            # inexcess
            if 'setexcess' in scripts:
                raise ScriptfileError('setexcess script depreceated, use inexcess instead.')
            if 'inexcess' in scripts:
                self.excess = set(scripts['inexcess'][0].split()) - set(['no'])
            else:
                raise ScriptfileError('In case of no excess phases, use setexcess no')
            # omit
            if 'omit' in scripts:
                self.omit = set(scripts['omit'][0].split())
            else:
                self.omit = set()
            # samecoding
            if 'samecoding' in scripts:
                self.samecoding = [set(sc.split()) for sc in scripts['samecoding']]
            # pseudosection
            if 'pseudosection' not in scripts:
                raise ScriptfileError('No pseudosection script, pseudosection is mandatory script.')
            # autoexit
            if 'autoexit' not in scripts:
                raise ScriptfileError('No autoexit script, autoexit must be provided.')
            # dogmin
            if 'dogmin' in scripts:
                raise ScriptfileError('Dogmin script should be removed from scriptfile.')
            # TC
            errinfo = 'Error during initial TC run.'
            calcs = ['calcP {}'.format(sum(self.prange) / 2),
                     'calcT {}'.format(sum(self.trange) / 2),
                     'with xxx']
            old_calcs = self.update_scriptfile(get_old_calcs=True, calcs=calcs)
            output = self.runtc()
            self.update_scriptfile(calcs=old_calcs)
            if '-- run bombed in whichphases' not in output:
                raise TCError(output)
            self.tcout = output.split('-- run bombed in whichphases')[0].strip()
            ax_phases = set(self.tcout.split('reading ax:')[1].split('\n\n')[0].split())
            # which
            if 'with' in scripts:
                if scripts['with'][0].split()[0] == 'someof':
                    raise ScriptfileError('Pypsbuilder does not support with sameof <phase list>. Use omit {}'.format(' '.join(ax_phases.union(*self.samecoding) - set(scripts['with'][0].split()[1:]))))
            # union ax phases and samecoding and diff omit
            self.phases = ax_phases.union(*self.samecoding) - self.omit
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
        if self.OK:
            return '\n'.join(['{}'.format(self.tcversion),
                              'Working directory: {}'.format(self.workdir),
                              'Scriptfile: {}'.format('tc-' + self.name + '.txt'),
                              'AX file: {}'.format('tc-' + self.axname + '.txt'),
                              'Status: {}'.format(self.status)])
        else:
            return '\n'.join(['Uninitialized working directory {}'.format(self.workdir),
                              'Status: {}'.format(self.status)])

    @property
    def scriptfile(self):
        """pathlib.Path: Path to scriptfile."""
        return self.workdir.joinpath('tc-' + self.name + '.txt')

    def read_scriptfile(self):
        with self.scriptfile.open('r', encoding=self.TCenc) as f:
            r = f.read()
        return r

    @property
    def drfile(self):
        """pathlib.Path: Path to -dr output file."""
        return self.workdir.joinpath('tc-' + self.name + '-dr.txt')

    @property
    def logfile(self):
        """pathlib.Path: Path to THERMOCALC log file."""
        return self.workdir.joinpath('tc-log.txt')

    @property
    def icfile(self):
        """pathlib.Path: Path to ic file."""
        return self.workdir.joinpath('tc-' + self.name + '-ic.txt')

    @property
    def itfile(self):
        """pathlib.Path: Path to it file."""
        return self.workdir.joinpath('tc-' + self.name + '-it.txt')

    @property
    def ofile(self):
        """pathlib.Path: Path to project output file."""
        return self.workdir.joinpath('tc-' + self.name + '-o.txt')

    @property
    def csvfile(self):
        """pathlib.Path: Path to csv file."""
        return self.workdir.joinpath('tc-' + self.name + '-csv.txt')

    @property
    def drawpdfile(self):
        """pathlib.Path: Path to drawpd file."""
        return self.workdir.joinpath('dr-' + self.name + '.txt')

    @property
    def axfile(self):
        """pathlib.Path: Path to used a-x file."""
        return self.workdir.joinpath('tc-' + self.axname + '.txt')

    @property
    def prefsfile(self):
        """pathlib.Path: Path to THERMOCALC prefs file."""
        return self.workdir.joinpath('tc-prefs.txt')

    def read_prefsfile(self):
        with self.prefsfile.open('r', encoding=self.TCenc) as f:
            r = f.read()
        return r

    @property
    def tcversion(self):
        """str: Version identification of THERMCALC executable."""
        return self.tcout.split('\n')[0]

    @property
    def tcnewversion(self):
        """bool: False for THERMOCALC older than 3.5."""
        return not float(self.tcversion.split()[1]) < 3.5

    @property
    def datasetfile(self):
        """pathlib.Path: Path to dataset file."""
        return self.workdir.joinpath(self.dataset.split(' produced')[0])

    @property
    def dataset(self):
        """str: Version identification of thermodynamic dataset in use."""
        return self.tcout.split('using ')[1].split('\n')[0]

    def parse_logfile(self, **kwargs):
        """Parser for THERMOCALC output.

        It parses the outputs of THERMOCALC after calculation.

        Args:
            tx (bool): True for T-X and P-X calculations. Default False.
            output (str): When not None, used as content of logfile. Default None.
            resic (str): When not None, used as content of icfile. Default None.

        Returns:
            status (str): Result of parsing. 'ok', 'nir' (nothing in range) or 'bombed'.
            results (TCResultSet): Results of TC calculation.
            output (str): Full nonparsed THERMOCALC output.

        Example:
            Parse output after univariant line calculation in P-T pseudosection::

                >>> tc = TCAPI('pat/to/dir')
                >>> status, variance, pts, res, output = tc.parse_logfile()
        """
        if self.tcnewversion:
            return self.parse_logfile_new(**kwargs)
        else:
            return self.parse_logfile_old(**kwargs)

    def parse_logfile_new(self, **kwargs):
        output = kwargs.get('output', None)
        resic = kwargs.get('resic', None)
        try:
            if output is None:
                with self.logfile.open('r', encoding=self.TCenc) as f:
                    output = f.read().split('^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n\n')[1]
            lines = [ln for ln in output.splitlines() if ln != '']
            results = None
            do_parse = True
            if resic is None:
                if not self.icfile.exists():
                    if [ix for ix, ln in enumerate(lines) if 'BOMBED' in ln]:
                        status = 'bombed'
                    else:
                        status = 'nir'
                    do_parse = False
                else:
                    with self.icfile.open('r', encoding=self.TCenc) as f:
                        resic = f.read()
            if do_parse:
                lines = [ln for ln in output.splitlines() if ln != '']
                # parse ptguesses
                bstarts = [ix for ix, ln in enumerate(lines) if ln.startswith('------------------------------------------------------------')]
                bstarts.append(len(lines))
                ptguesses = []
                corrects = []
                for bs, be in zip(bstarts[:-1], bstarts[1:]):
                    block = lines[bs:be]
                    if block[2].startswith('#'):
                        corrects.append(False)
                    else:
                        corrects.append(True)
                    xyz = [ix for ix, ln in enumerate(block) if ln.startswith('xyzguess')]
                    gixs = [ix for ix, ln in enumerate(block) if ln.startswith('ptguess')][0] - 3
                    gixe = xyz[-1] + 2
                    ptguesses.append(block[gixs:gixe])
                # parse icfile
                blocks = resic.split('\n===========================================================\n\n')[1:]
                # done
                if len(blocks) > 0:
                    rlist = [TCResult.from_block(block, ptguess) for block, ptguess, correct in zip(blocks, ptguesses, corrects) if correct]
                    if len(rlist) > 0:
                        status = 'ok'
                        results = TCResultSet(rlist)
                    else:
                        status = 'nir'
                else:
                    status = 'nir'
            return status, results, output
        except Exception:
            return 'bombed', None, None

    def parse_logfile_new_backup(self, **kwargs):
        output = kwargs.get('output', None)
        resic = kwargs.get('resic', None)
        if output is None:
            with self.logfile.open('r', encoding=self.TCenc) as f:
                output = f.read()
        lines = [ln for ln in output.splitlines() if ln != '']
        results = None
        do_parse = True
        if resic is None:
            if not self.icfile.exists():
                if [ix for ix, ln in enumerate(lines) if 'BOMBED' in ln]:
                    status = 'bombed'
                else:
                    status = 'nir'
                do_parse = False
            else:
                with self.icfile.open('r', encoding=self.TCenc) as f:
                    resic = f.read()
        if do_parse:
            lines = [ln for ln in output.splitlines() if ln != '']
            # parse ptguesses
            bstarts = [ix for ix, ln in enumerate(lines) if ln.startswith('--------------------------------------------------------------------')]
            bstarts.append(len(lines))
            ptguesses = []
            corrects = []
            for bs, be in zip(bstarts[:-1], bstarts[1:]):
                block = lines[bs:be]
                if block[2].startswith('#'):
                    corrects.append(False)
                else:
                    corrects.append(True)
                xyz = [ix for ix, ln in enumerate(block) if ln.startswith('xyzguess')]
                gixs = [ix for ix, ln in enumerate(block) if ln.startswith('ptguess')][0] - 3
                gixe = xyz[-1] + 2
                ptguesses.append(block[gixs:gixe])
            # parse icfile
            blocks = resic.split('\n===========================================================\n\n')[1:]
            # done
            if len(blocks) > 0:
                rlist = [TCResult.from_block(block, ptguess) for block, ptguess, correct in zip(blocks, ptguesses, corrects) if correct]
                if len(rlist) > 0:
                    status = 'ok'
                    results = TCResultSet(rlist)
                else:
                    status = 'nir'
            else:
                status = 'nir'
        return status, results, output

    def parse_logfile_old(self, **kwargs):
        # res is list of dicts with data and ptguess keys
        # data is dict with keys of phases and each contain dict of values
        # res[0]['data']['g']['mode']
        # res[0]['data']['g']['z']
        # res[0]['data']['g']['MnO']
        output = kwargs.get('output', None)
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
                pp, TT = np.array(pts).T
                results = TCResultSet([TCResult(T, p, variance=variance, step=0.0, data=r['data'], ptguess=r['ptguess']) for (r, p, T) in zip(res, pp, TT)])
            else:
                status = 'nir'
                results = None
        return status, results, output

    def parse_dogmin_old(self):
        """Dogmin parser."""
        try:
            with self.icfile.open('r', encoding=self.TCenc) as f:
                resic = f.read()
            with self.logfile.open('r', encoding=self.TCenc) as f:
                output = f.read()
            res = output.split('##########################################################\n')[-1]
        except Exception:
            res = None
            resic = None
        return res, resic

    def parse_dogmin(self):
        """Dogmin parser."""
        try:
            with self.icfile.open('r', encoding=self.TCenc) as f:
                resic = f.read()
            with self.logfile.open('r', encoding=self.TCenc) as f:
                output = f.read()
        except Exception:
            output = None
            resic = None
        return output, resic

    def update_scriptfile(self, **kwargs):
        """Method to update scriptfile.

        This method is used to programatically edit scriptfile.

        Kwargs:
            calcs: List of lines defining fully hands-off calculations. Default None.
            get_old_calcs: When True method returns existing calcs lines
                before possible modification. Default False.
            guesses: List of lines defining ptguesses. If None guesses
                are not modified. Default None.
            get_old_guesses: When True method returns existing ptguess lines
                before possible modification. Default False.
            bulk: List of lines defining bulk composition. Default None.
            xsteps: Number of compositional steps between two bulks.
                Default 20.
        """
        calcs = kwargs.get('calcs', None)
        get_old_calcs = kwargs.get('get_old_calcs', False)
        guesses = kwargs.get('guesses', None)
        get_old_guesses = kwargs.get('get_old_guesses', False)
        bulk = kwargs.get('bulk', None)
        xsteps = kwargs.get('xsteps', None)
        with self.scriptfile.open('r', encoding=self.TCenc) as f:
            scf = f.read()
        changed = False
        scf_1, rem = scf.split('%{PSBCALC-BEGIN}')
        old, scf_2 = rem.split('%{PSBCALC-END}')
        old_calcs = old.strip().splitlines()
        if calcs is not None:
            scf = scf_1 + '%{PSBCALC-BEGIN}\n' + '\n'.join(calcs) + '\n%{PSBCALC-END}' + scf_2
            changed = True
        scf_1, rem = scf.split('%{PSBGUESS-BEGIN}')
        old, scf_2 = rem.split('%{PSBGUESS-END}')
        old_guesses = old.strip().splitlines()
        if guesses is not None:
            scf = scf_1 + '%{PSBGUESS-BEGIN}\n' + '\n'.join(guesses) + '\n%{PSBGUESS-END}' + scf_2
            changed = True
        if bulk is not None:
            scf_1, rem = scf.split('%{PSBBULK-BEGIN}')
            old, scf_2 = rem.split('%{PSBBULK-END}')
            bulk_lines = []
            if len(bulk) == 2:
                bulk_lines.append('bulk {}'.format(' '.join(bulk[0])))
                bulk_lines.append('bulk {}'.format(' '.join(bulk[1])))
            else:
                bulk_lines.append('bulk {}'.format(' '.join(bulk[0])))
                bulk_lines.append('bulk {}'.format(' '.join(bulk[1])))
                bulk_lines.append('bulk {} {}'.format(' '.join(bulk[2]), xsteps))
            scf = scf_1 + '%{PSBBULK-BEGIN}\n' + '\n'.join(bulk_lines) + '\n%{PSBBULK-END}' + scf_2
            changed = True
        if xsteps is not None:
            bulk_lines = []
            scf_1, rem = scf.split('%{PSBBULK-BEGIN}')
            old, scf_2 = rem.split('%{PSBBULK-END}')
            if len(self.bulk) == 3:
                bulk_lines.append('bulk {}'.format(' '.join(self.bulk[0])))
                bulk_lines.append('bulk {}'.format(' '.join(self.bulk[1])))
                bulk_lines.append('bulk {} {}'.format(' '.join(self.bulk[2]), xsteps))
            scf = scf_1 + '%{PSBBULK-BEGIN}\n' + '\n'.join(bulk_lines) + '\n%{PSBBULK-END}' + scf_2
            changed = True
        if changed:
            with self.scriptfile.open('w', encoding=self.TCenc) as f:
                f.write(scf)
        if get_old_calcs and get_old_guesses:
            return old_calcs, old_guesses
        elif get_old_calcs:
            return old_calcs
        elif get_old_guesses:
            return old_guesses
        else:
            return None

    def interpolate_bulk(self, x):
        if len(self.bulk) == 2:
            new_bulk = []
            try:
                _ = (e for e in x)
            except TypeError:
                b1 = np.array([float(v) for v in self.bulk[0]])
                b2 = np.array([float(v) for v in self.bulk[1]])
                db = b2 - b1
                bi = b1 + x * db
                new_bulk.append(['{:g}'.format(v) for v in bi])
            else:
                for x_val in x:
                    b1 = np.array([float(v) for v in self.bulk[0]])
                    b2 = np.array([float(v) for v in self.bulk[1]])
                    db = b2 - b1
                    bi = b1 + x_val * db
                    new_bulk.append(['{:g}'.format(v) for v in bi])
        else:
            new_bulk = self.bulk[0]
        return new_bulk

    def calc_t(self, phases, out, **kwargs):
        """Method to run THERMOCALC to find univariant line using Calc T at P strategy.

        Args:
            phases (set): Set of present phases
            out (set): Set of single zero mode phase
            prange (tuple): Temperature range for calculation
            trange (tuple): Pressure range for calculation
            steps (int): Number of steps

        Returns:
            tuple: (tcout, ans) standard output and input for THERMOCALC run.
            Input ans could be used to reproduce calculation.
        """
        prange = kwargs.get('prange', self.prange)
        trange = kwargs.get('trange', self.trange)
        steps = kwargs.get('steps', 50)
        step = (prange[1] - prange[0]) / steps
        calcs = ['calcP {:g} {:g} {:g}'.format(*prange, step),
                 'calcT {:g} {:g}'.format(*trange),
                 'calctatp yes',
                 'with  {}'.format(' '.join(phases - self.excess)),
                 'zeromodeisopleth {}'.format(' '.join(out))]
        self.update_scriptfile(calcs=calcs)
        tcout = self.runtc()
        return tcout, calcs

    def calc_p(self, phases, out, **kwargs):
        """Method to run THERMOCALC to find univariant line using Calc P at T strategy.

        Args:
            phases (set): Set of present phases
            out (set): Set of single zero mode phase
            prange (tuple): Temperature range for calculation
            trange (tuple): Pressure range for calculation
            steps (int): Number of steps

        Returns:
            tuple: (tcout, ans) standard output and input for THERMOCALC run.
            Input ans could be used to reproduce calculation.
        """
        prange = kwargs.get('prange', self.prange)
        trange = kwargs.get('trange', self.trange)
        steps = kwargs.get('steps', 50)
        step = (trange[1] - trange[0]) / steps
        calcs = ['calcP {:g} {:g}'.format(*prange),
                 'calcT {:g} {:g} {:g}'.format(*trange, step),
                 'calctatp no',
                 'with  {}'.format(' '.join(phases - self.excess)),
                 'zeromodeisopleth {}'.format(' '.join(out))]
        self.update_scriptfile(calcs=calcs)
        tcout = self.runtc()
        return tcout, calcs

    def calc_pt(self, phases, out, **kwargs):
        """Method to run THERMOCALC to find invariant point.

        Args:
            phases (set): Set of present phases
            out (set): Set of two zero mode phases
            prange (tuple): Temperature range for calculation
            trange (tuple): Pressure range for calculation

        Returns:
            tuple: (tcout, ans) standard output and input for THERMOCALC run.
            Input ans could be used to reproduce calculation.
        """
        prange = kwargs.get('prange', self.prange)
        trange = kwargs.get('trange', self.trange)
        calcs = ['calcP {:g} {:g}'.format(*prange),
                 'calcT {:g} {:g}'.format(*trange),
                 'with  {}'.format(' '.join(phases - self.excess)),
                 'zeromodeisopleth {}'.format(' '.join(out))]
        self.update_scriptfile(calcs=calcs)
        tcout = self.runtc()
        return tcout, calcs

    def calc_tx(self, phases, out, **kwargs):
        """Method to run THERMOCALC for T-X pseudosection calculations.

        Args:
            phases (set): Set of present phases
            out (set): Set of zero mode phases
            prange (tuple): Temperature range for calculation
            trange (tuple): Pressure range for calculation
            xvals (tuple): range for X variable
            steps (int): Number of steps

        Returns:
            tuple: (tcout, ans) standard output and input for THERMOCALC run.
            Input ans could be used to reproduce calculation.
        """
        prange = kwargs.get('prange', self.prange)
        trange = kwargs.get('trange', self.trange)
        xvals = kwargs.get('xvals', (0, 1))
        steps = kwargs.get('steps', 20)
        step = (prange[1] - prange[0]) / steps
        if prange[0] == prange[1]:
            calcs = ['calcP {:g} {:g}'.format(*prange),
                     'calcT {:g} {:g}'.format(*trange),
                     'calctatp yes',
                     'with  {}'.format(' '.join(phases - self.excess)),
                     'zeromodeisopleth {}'.format(' '.join(out)),
                     'bulksubrange {:g} {:g}'.format(*xvals)]
        else:
            calcs = ['calcP {:g} {:g} {:g}'.format(*prange, step),
                     'calcT {:g} {:g}'.format(*trange),
                     'calctatp yes',
                     'with  {}'.format(' '.join(phases - self.excess)),
                     'zeromodeisopleth {}'.format(' '.join(out)),
                     'bulksubrange {:g} {:g}'.format(*xvals)]
        self.update_scriptfile(calcs=calcs, xsteps=steps)
        tcout = self.runtc()
        return tcout, calcs

    def calc_px(self, phases, out, **kwargs):
        """Method to run THERMOCALC for p-X pseudosection calculations.

        Args:
            phases (set): Set of present phases
            out (set): Set of zero mode phases
            prange (tuple): Temperature range for calculation
            trange (tuple): Pressure range for calculation
            xvals (tuple): range for X variable
            steps (int): Number of steps

        Returns:
            tuple: (tcout, ans) standard output and input for THERMOCALC run.
            Input ans could be used to reproduce calculation.
        """
        prange = kwargs.get('prange', self.prange)
        trange = kwargs.get('trange', self.trange)
        xvals = kwargs.get('xvals', (0, 1))
        steps = kwargs.get('steps', 20)
        step = (trange[1] - trange[0]) / steps
        if trange[0] == trange[1]:
            calcs = ['calcP {:g} {:g}'.format(*prange),
                     'calcT {:g} {:g}'.format(*trange),
                     'calctatp no',
                     'with  {}'.format(' '.join(phases - self.excess)),
                     'zeromodeisopleth {}'.format(' '.join(out)),
                     'bulksubrange {:g} {:g}'.format(*xvals)]
        else:
            calcs = ['calcP {:g} {:g}'.format(*prange),
                     'calcT {:g} {:g} {:g}'.format(*trange, step),
                     'calctatp no',
                     'with  {}'.format(' '.join(phases - self.excess)),
                     'zeromodeisopleth {}'.format(' '.join(out)),
                     'bulksubrange {:g} {:g}'.format(*xvals)]
        self.update_scriptfile(calcs=calcs, xsteps=steps)
        tcout = self.runtc()
        return tcout, calcs

    def calc_assemblage(self, phases, p, t, onebulk=None):
        """Method to run THERMOCALC to calculate compositions of stable assemblage.

        Args:
            phases (set): Set of present phases
            p (float): Temperature for calculation
            t (float): Pressure for calculation

        Returns:
            tuple: (tcout, ans) standard output and input for THERMOCALC run.
            Input ans could be used to reproduce calculation.
        """
        calcs = ['calcP {}'.format(p),
                 'calcT {}'.format(t),
                 'with  {}'.format(' '.join(phases - self.excess))]
        if onebulk is not None:
            calcs.append('onebulk {}'.format(onebulk))
        self.update_scriptfile(calcs=calcs)
        tcout = self.runtc('\nkill\n\n')
        return tcout, calcs

    def dogmin(self, phases, p, t, variance, doglevel=1, onebulk=None):
        """Run THERMOCALC dogmin session.

        Args:
            variance (int): Maximum variance to be considered

        Returns:
            str: THERMOCALC standard output
        """
        calcs = ['calcP {}'.format(p),
                 'calcT {}'.format(t),
                 'dogmin yes {}'.format(doglevel),
                 'with  {}'.format(' '.join(phases - self.excess)),
                 'maxvar {}'.format(variance)]
        if onebulk is not None:
            calcs.append('onebulk {}'.format(onebulk))
        old_calcs = self.update_scriptfile(get_old_calcs=True, calcs=calcs)
        tcout = self.runtc('\nkill\n\n')
        self.update_scriptfile(calcs=old_calcs)
        return tcout

    def calc_variance(self, phases):
        """Get variance of assemblage.

        Args:
            phases (set): Set of present phases

        Returns:
            int: variance
        """
        variance = None
        calcs = ['calcP {} {}'.format(*self.prange),
                 'calcT {} {}'.format(*self.trange),
                 'with  {}'.format(' '.join(phases - self.excess)),
                 'acceptvar no']
        old_calcs = self.update_scriptfile(get_old_calcs=True, calcs=calcs)
        tcout = self.runtc('kill\n\n')
        self.update_scriptfile(calcs=old_calcs)
        for ln in tcout.splitlines():
            if 'variance of required equilibrium' in ln:
                variance = int(ln[ln.index('(') + 1:ln.index('?')])
                break
        return variance

    def runtc(self, instr='kill\n\n'):
        """Low-level method to actually run THERMOCALC.

        Args:
            instr (str): String to be passed to standard input for session.

        Returns:
            str: THERMOCALC standard output
        """
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
        """Method to run drawpd."""
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


class TCResult():

    def __init__(self, T, p, variance=0, c=0, data={}, ptguess=['']):
        self.data = data
        self.ptguess = ptguess
        self.T = T
        self.p = p
        self.variance = variance
        self.c = c

    @classmethod
    def from_block(cls, block, ptguess):
        info, ax, sf, bulk, rbi, mode, factor, td, sys, *mems, pems = block.split('\n\n')
        if 'var = 2; seen' in info:
            # no step in bulk
            info, ax, sf, rbi, mode, factor, td, sys, *mems, pems = block.split('\n\n')
            bulk = '\n'.join(rbi.split('\n')[:3])
            rbi = '\n'.join(rbi.split('\n')[3:])
        # heading
        data = {phase: {} for phase in info.split('{')[0].split()}
        p, T = (float(v.strip()) for v in info.split('{')[1].split('}')[0].split(','))
        # var or ovar?
        variance = int(info.split('var = ')[1].split(' ')[0].replace(';', ''))
        # a-x variables
        for head, vals in zip(ax.split('\n')[::2], ax.split('\n')[1::2]):
            phase, *names = head.split()
            data[phase].update({name.replace('({})'.format(phase), ''): float(val) for name, val in zip(names, vals.split())})
        # site fractions
        for head, vals in zip(sf.split('\n')[1::2], sf.split('\n')[2::2]):  # skip site fractions row
            phase, *names = head.split()
            data[phase].update({name: float(val) for name, val in zip(names, vals.split())})
        # bulk composition
        bulk_vals = {}
        oxhead, vals = bulk.split('\n')[1:]  # skip oxide compositions row
        for ox, val in zip(oxhead.split(), vals.split()[1:]):
            bulk_vals[ox] = float(val)
        data['bulk'] = bulk_vals
        # x for TX and pX
        if 'step' in vals:
            c = float(vals.split('step')[1].split(', x =')[1])
        else:
            c = 0
        # rbi
        for row in rbi.split('\n'):
            phase, *vals = row.split()
            data[phase].update({ox: float(val) for ox, val in zip(oxhead.split(), vals)})
        # modes (zero mode is empty field in tc350 !!!)
        head, vals = mode.split('\n')
        phases = head.split()[1:]
        # fixed width parsing !!!
        valsf = [float(vals[6:][12 * i:12 * (i + 1)].strip()) if vals[6:][12 * i:12 * (i + 1)].strip() != '' else 0.0 for i in range(len(phases))]
        for phase, val in zip(phases, valsf):
            data[phase].update({'mode': float(val)})
        # factors
        head, vals = factor.split('\n')
        phases = head.split()[1:]
        valsf = [float(vals[6:][12 * i:12 * (i + 1)].strip()) if vals[6:][12 * i:12 * (i + 1)].strip() != '' else 0.0 for i in range(len(phases))]
        for phase, val in zip(phases, valsf):
            data[phase].update({'factor': float(val)})
        # thermodynamic state
        head, *rows = td.split('\n')
        for row in rows:
            phase, *vals = row.split()
            data[phase].update({name: float(val) for name, val in zip(head.split(), vals)})
        # bulk thermodynamics
        sys = {}
        for name, val in zip(head.split(), row.split()[1:]):
            sys[name] = float(val)
        data['sys'] = sys
        # model end-members
        if len(mems) > 0:
            _, mem0 = mems[0].split('\n', maxsplit=1)
            head = ['ideal', 'gamma', 'activity', 'prop', 'mu', 'RTlna']
            mems[0] = mem0
            for mem in mems:
                ems = mem.split('\n')
                phase, ems0 = ems[0].split(maxsplit=1)
                ems[0] = ems0
                for row in ems:
                    em, *vals = row.split()
                    phase_em = '{}({})'.format(phase, em)
                    data[phase_em] = {name: float(val) for name, val in zip(head, vals)}
        # pure end-members
        for row in pems.split('\n')[:-1]:
            pem, val = row.split()
            data[pem].update({'mu': float(val)})
        # Finally
        return cls(T, p, variance=variance, c=c, data=data, ptguess=ptguess)

    def __repr__(self):
        return 'p:{:g} T:{:g} V:{} c:{:g}, Phases: {}'.format(self.p, self.T, self.variance, self.c, ' '.join(self.phases))

    def __getitem__(self, key):
        if isinstance(key, str):
            if key not in self.phases:
                raise IndexError('The index ({}) do not exists.'.format(key))
            return self.data[key]
        else:
            raise TypeError('Invalid argument type.')

    @property
    def phases(self):
        return set(self.data.keys())

    def rename_phase(self, old, new):
        self.data[new] = self.data.pop(old)
        for ix, ln in enumerate(self.ptguess):
            self.ptguess[ix] = ln.replace('({})'.format(old), '({})'.format(new))


class TCResultSet:

    def __init__(self, results):
        self.results = results

    def __repr__(self):
        return '{} results'.format(len(self.results))

    def __len__(self):
        return len(self.results)

    def __getitem__(self, key):
        if isinstance(key, slice):
            # Get the start, stop, and step from the slice
            return TCResultSet(self.results[key])
        elif isinstance(key, int):
            if key < 0:  # Handle negative indices
                key += len(self.results)
            if key < 0 or key >= len(self.results):
                raise IndexError('The index ({}) is out of range.'.format(key))
            return self.results[key]
        elif isinstance(key, list):
            return TCResultSet([self.results[ix] for ix in key])
        else:
            raise TypeError('Invalid argument type.')

    @property
    def x(self):
        return np.array([res.T for res in self.results])

    @property
    def y(self):
        return np.array([res.p for res in self.results])

    @property
    def variance(self):
        return self.results[0].variance

    @property
    def c(self):
        return np.array([res.c for res in self.results])

    @property
    def phases(self):
        return self.results[0].phases

    def ptguess(self, ix):
        try:
            return self.results[ix].ptguess
        except Exception:
            return None

    def rename_phase(self, old, new):
        for r in self.results:
            r.rename_phase(old, new)

    def insert(self, ix, result):
        self.results.insert(ix, result)


class Dogmin:
    def __init__(self, **kwargs):
        assert 'output' in kwargs, 'Dogmin output must be provided'
        assert 'resic' in kwargs, 'ic file content must be provided'
        self.id = kwargs.get('id', 0)
        self._output = kwargs.get('output')
        self.resic = kwargs.get('resic')
        self.x = kwargs.get('x', None)
        self.y = kwargs.get('y', None)

    @property
    def output(self):
        return self._output.split('##########################################################\n')[-1]

    @property
    def phases(self):
        return set(self.output.split('assemblage')[1].split('\n')[0].split())

    @property
    def out(self):
        return set()

    def label(self, excess={}):
        """str: full label with space delimeted phases."""
        return ' '.join(sorted(list(self.phases.difference(excess))))

    def annotation(self, show_out=False, excess={}):
        """str: String representation of ID with possible zermo mode phase."""
        if show_out:
            return self.label(excess=excess)
        else:
            return '{:d}'.format(self.id)

    def ptguess(self):
        block = [ln for ln in self.output.splitlines() if ln != '']
        xyz = [ix for ix, ln in enumerate(block) if ln.startswith('xyzguess')]
        gixs = [ix for ix, ln in enumerate(block) if ln.startswith('ptguess')][0] - 1
        gixe = xyz[-1] + 2
        return block[gixs:gixe]


class PseudoBase:
    """Base class with common methods for InvPoint and UniLine.

    """
    def label(self, excess={}):
        """str: full label with space delimeted phases - zero mode phase."""
        phases_lbl = ' '.join(sorted(list(self.phases.difference(excess))))
        out_lbl = ' '.join(sorted(list(self.out)))
        return '{} - {}'.format(phases_lbl, out_lbl)

    def annotation(self, show_out=False):
        """str: String representation of ID with possible zermo mode phase."""
        if show_out:
            return '{:d} {}'.format(self.id, ' '.join(self.out))
        else:
            return '{:d}'.format(self.id)

    def ptguess(self, **kwargs):
        """list: Get stored ptguesses.

        InvPoint has just single ptguess, but for UniLine idx need to be
        specified. If omitted, the middle point from calculated ones is used.

        Args:
            idx (int): index which guesses to get.
        """
        idx = kwargs.get('idx', self.midix)
        return self.results[idx].ptguess

    def datakeys(self, phase=None):
        """list: Get list of variables for phase.

        Args:
            phase (str): name of phase
        """
        if phase is None:
            return list(self.results[self.midix].data.keys())
        else:
            return list(self.results[self.midix].data[phase].keys())


class InvPoint(PseudoBase):
    """Class to store invariant point

    Attributes:
        id (int): Invariant point identification
        phases (set): set of present phases
        out (set): set of zero mode phases
        cmd (str): THERMOCALC standard input to calculate this point
        variance (int): variance
        x (numpy.array): Array of x coordinates
            (even if only one, it is stored as array)
        y (numpy.array): Array of x coordinates
            (even if only one, it is stored as array)
        results (list): List of results dicts with data and ptgues keys.
        output (str): Full THERMOCALC output
        manual (bool): True when inavariant point is user-defined and not
            calculated
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
        self.results = kwargs.get('results', None)
        self.output = kwargs.get('output', 'User-defined')
        self.manual = kwargs.get('manual', False)

    def __repr__(self):
        return 'Inv: {}'.format(self.label())

    @property
    def midix(self):
        return 0

    @property
    def _x(self):
        """X coordinate as float"""
        return self.x[0]

    @property
    def _y(self):
        """Y coordinate as float"""
        return self.y[0]

    def shape(self):
        """Return shapely Point representing invariant point."""
        return Point(self._x, self._y)

    def all_unilines(self):
        """Return four tuples (phases, out) indicating possible four
        univariant lines passing trough this invariant point"""
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

    Attributes:
        id (int): Invariant point identification
        phases (set): set of present phases
        out (set): set of zero mode phase
        cmd (str): THERMOCALC standard input to calculate this point
        variance (int): variance
        _x (numpy.array): Array of x coordinates (all calculated)
        _y (numpy.array): Array of x coordinates (all calculated)
        results (list): List of results dicts with data and ptgues keys.
        output (str): Full THERMOCALC output
        manual (bool): True when inavariant point is user-defined and not
            calculated
        begin (int): id of invariant point defining begining of the line.
            0 for no begin
        end (int): id of invariant point defining end of the line.
            0 for no end
        used (slice): slice indicating which point on calculated line are
            between begin and end
    """
    def __init__(self, **kwargs):
        assert 'phases' in kwargs, 'Set of phases must be provided'
        assert 'out' in kwargs, 'Set of zero phase must be provided'
        self.id = kwargs.get('id', 0)
        self.phases = kwargs.get('phases')
        self.out = kwargs.get('out')
        self.cmd = kwargs.get('cmd', '')
        self.variance = kwargs.get('variance', 0)
        self._x = kwargs.get('x', np.array([]))
        self._y = kwargs.get('y', np.array([]))
        self.results = kwargs.get('results', None)
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
        return int((self.used.start + self.used.stop) // 2)

    @property
    def connected(self):
        return 2 - [self.begin, self.end].count(0)

    def _shape(self, ratio=None, tolerance=None):
        """Return shapely LineString representing univariant line.

        This method is using all calculated points.

        Args:
            ratio: y-coordinate multiplier to scale coordinates. Default None
            tolerance: tolerance x coordinates. Simplified object will be within
            the tolerance distance of the original geometry. Default None
        """
        if ratio is None:
            return LineString(np.array([self._x, self._y]).T)
        else:
            if tolerance is None:
                return LineString(np.array([self._x, self._y]).T)
            else:
                ln = LineString(np.array([self._x, ratio * self._y]).T).simplify(tolerance)
                x, y = np.array(ln.coords).T
                return LineString(np.array([x, y / ratio]).T)

    def shape(self, ratio=None, tolerance=None):
        """Return shapely LineString representing univariant line.

        This method is using trimmed points.

        Args:
            ratio: y-coordinate multiplier to scale coordinates. Default None
            tolerance: tolerance x coordinates. Simplified object will be within
            the tolerance distance of the original geometry. Default None
        """
        if ratio is None:
            return LineString(np.array([self.x, self.y]).T)
        else:
            if tolerance is None:
                return LineString(np.array([self.x, self.y]).T)
            else:
                ln = LineString(np.array([self.x, ratio * self.y]).T).simplify(tolerance)
                x, y = np.array(ln.coords).T
                return LineString(np.array([x, y / ratio]).T)

    def contains_inv(self, ip):
        """Check whether invariant point theoretically belong to univariant line.

        Args:
            ip (InvPoint): Invariant point

        Returns:
            bool: True for yes, False for no. Note that metastability is not checked.
        """
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
        """Returns coordinate tuple of labeling point for univariant line."""
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
    """Base class for PTsection, TXsection and PX section

    """
    def __init__(self, **kwargs):
        self.excess = kwargs.get('excess', set())
        self.invpoints = {}
        self.unilines = {}
        self.dogmins = {}

    def __repr__(self):
        return '\n'.join(['{}'.format(type(self).__name__),
                          'Univariant lines: {}'.format(len(self.unilines)),
                          'Invariant points: {}'.format(len(self.invpoints)),
                          '{} range: {} {}'.format(self.x_var, *self.xrange),
                          '{} range: {} {}'.format(self.y_var, *self.yrange)])

    @property
    def ratio(self):
        return (self.xrange[1] - self.xrange[0]) / (self.yrange[1] - self.yrange[0])

    @property
    def range_shapes(self):
        # default p-t range boundary
        bnd = [LineString([(self.xrange[0], self.yrange[0]),
                          (self.xrange[1], self.yrange[0])]),
               LineString([(self.xrange[1], self.yrange[0]),
                          (self.xrange[1], self.yrange[1])]),
               LineString([(self.xrange[1], self.yrange[1]),
                          (self.xrange[0], self.yrange[1])]),
               LineString([(self.xrange[0], self.yrange[1]),
                          (self.xrange[0], self.yrange[0])])]
        return bnd, next(polygonize(bnd))

    def add_inv(self, id, inv):
        if inv.manual:
            inv.results = None
        else:  # temporary compatibility with 2.2.0
            if not isinstance(inv.results, TCResultSet):
                inv.results = TCResultSet([TCResult(float(x), float(y), variance=inv.variance,
                                                    data=r['data'], ptguess=r['ptguess'])
                                           for r, x, y in zip(inv.results, inv.x, inv.y)])
        self.invpoints[id] = inv
        self.invpoints[id].id = id

    def add_uni(self, id, uni):
        if uni.manual:
            uni.results = None
        else:  # temporary compatibility with 2.2.0
            if not isinstance(uni.results, TCResultSet):
                uni.results = TCResultSet([TCResult(float(x), float(y), variance=uni.variance,
                                                    data=r['data'], ptguess=r['ptguess'])
                                           for r, x, y in zip(uni.results, uni._x, uni._y)])
        self.unilines[id] = uni
        self.unilines[id].id = id

    def add_dogmin(self, id, dgm):
        self.dogmins[id] = dgm
        self.dogmins[id].id = id

    def cleanup_data(self):
        for id_uni, uni in self.unilines.items():
            if not uni.manual:
                keep = slice(max(uni.used.start - 1, 0), min(uni.used.stop + 1, len(uni._x)))
                uni._x = uni._x[keep]
                uni._y = uni._y[keep]
                uni.results = uni.results[keep]
            else:
                uni.cmd = ''
                uni.variance = 0
                uni._x = np.array([])
                uni._y = np.array([])
                uni.results = [dict(data=None, ptguess=None)]
                uni.output = 'User-defined'
                uni.used = slice(0, 0)
                uni.x = np.array([])
                uni.y = np.array([])
            self.trim_uni(id_uni)

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
                        uni.out = cuni.out  # switch to already used ??? Needed ???
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
            uni.used = slice(np.flatnonzero(vdst >= d1)[0].item(),
                             np.flatnonzero(vdst <= d2)[-1].item() + 1)

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

    def create_shapes(self, tolerance=None):
        def splitme(seg):
            '''Recursive boundary splitter'''
            s_seg = []
            for _, l in lns:
                if seg.intersects(l):
                    m = linemerge([seg, l])
                    if m.type == 'MultiLineString':
                        p = seg.intersection(l)
                        p_ok = l.interpolate(l.project(p))  # fit intersection to line
                        t_seg = LineString([Point(seg.coords[0]), p_ok])
                        if t_seg.is_valid:
                            s_seg.append(t_seg)
                        t_seg = LineString([p_ok, Point(seg.coords[-1])])
                        if t_seg.is_valid:
                            s_seg.append(t_seg)
                        break
            if len(s_seg) == 2:
                return splitme(s_seg[0]) + splitme(s_seg[1])
            else:
                return [seg]
        # define bounds and area
        bnd, area = self.range_shapes
        lns = []
        log = []
        # trim univariant lines
        for uni in self.unilines.values():
            ln = area.intersection(uni.shape(ratio=self.ratio, tolerance=tolerance))
            if ln.type == 'LineString' and not ln.is_empty:
                lns.append((uni.id, ln))
            if ln.type == 'MultiLineString':
                for ln_part in ln:
                    if ln_part.type == 'LineString' and not ln_part.is_empty:
                        lns.append((uni.id, ln_part))
        # split boundaries
        edges = splitme(bnd[0]) + splitme(bnd[1]) + splitme(bnd[2]) + splitme(bnd[3])
        # polygonize
        polys = list(polygonize(edges + [l for _, l in lns]))
        # create shapes
        shapes = {}
        unilists = {}
        for ix, poly in enumerate(polys):
            unilist = []
            for uni_id, ln in lns:
                if ln.relate_pattern(poly, '*1*F*****'):
                    unilist.append(uni_id)
            phases = set.intersection(*(self.unilines[id].phases for id in unilist))
            vd = [phases.symmetric_difference(self.unilines[id].phases) == self.unilines[id].out or not phases.symmetric_difference(self.unilines[id].phases) or phases.symmetric_difference(self.unilines[id].phases).union(self.unilines[id].out) in polymorphs for id in unilist]
            if all(vd):
                if frozenset(phases) in shapes:
                    # multivariant field crossed just by single univariant line
                    if len(unilist) == 1:
                        if self.unilines[unilist[0]].out.issubset(phases):
                            phases = phases.difference(self.unilines[unilist[0]].out)
                            shapes[frozenset(phases)] = poly
                            unilists[frozenset(phases)] = unilist
                    elif len(unilists[frozenset(phases)]) == 1:
                        if self.unilines[unilists[frozenset(phases)][0]].out.issubset(phases):
                            orig_unilist = unilists[frozenset(phases)]
                            shapes[frozenset(phases)] = poly
                            unilists[frozenset(phases)] = unilist
                            phases = phases.difference(self.unilines[orig_unilist[0]].out)
                            shapes[frozenset(phases)] = poly
                            unilists[frozenset(phases)] = orig_unilist
                    else:
                        shapes[frozenset(phases)] = shapes[frozenset(phases)].union(poly).buffer(0.00001)
                        log.append('Area defined by unilines {} is self-intersecting with {}.'.format(' '.join([str(id) for id in unilist]), ' '.join([str(id) for id in unilists[frozenset(phases)]])))
                        unilists[frozenset(phases)] = list(set(unilists[frozenset(phases)] + unilist))
                else:
                    shapes[frozenset(phases)] = poly
                    unilists[frozenset(phases)] = unilist
            else:
                log.append('Area defined by unilines {} is not valid field.'.format(' '.join([str(id) for id in unilist])))
        return shapes, unilists, log

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

    @staticmethod
    def read_file(projfile):
        with gzip.open(str(projfile), 'rb') as stream:
            data = pickle.load(stream)
        return data

    @staticmethod
    def from_file(projfile):
        with gzip.open(str(projfile), 'rb') as stream:
            data = pickle.load(stream)
        return data['section']


class PTsection(SectionBase):
    """P-T pseudosection class

    """
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


class TXsection(SectionBase):
    """T-X pseudosection class

    """
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


class PXsection(SectionBase):
    """P-X pseudosection class

    """
    def __init__(self, **kwargs):
        self.xrange = (0., 1.)
        self.yrange = kwargs.get('prange', (0.1, 20.))
        self.x_var = 'C'
        self.x_var_label = 'Composition'
        self.x_var_res = 0.001
        self.y_var = 'p'
        self.y_var_label = 'Pressure [kbar]'
        self.y_var_res = 0.001
        super(PXsection, self).__init__(**kwargs)
