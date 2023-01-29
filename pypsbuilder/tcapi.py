"""THERMOCALC API classes.

This module contains classes and tools providing API to THERMOCALC, parsing of
outputs and storage of calculated invariant points and univariant lines.

Todo:
    * Implement own class for divariant fields

"""
# author: Ondrej Lexa
# website: petrol.natur.cuni.cz/~ondro

import sys
import os
import subprocess

# import itertools
# import re
from pathlib import Path

# from collections import OrderedDict
import numpy as np
from .psclasses import TCResult, TCResultSet

popen_kw = dict(stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=False)


def get_tcapi(workdir='.', TCenc='mac-roman'):
    workdir = Path(workdir).resolve()
    try:
        errinfo = 'Initialize project error!'
        tcexe = None
        drexe = None
        # default exe
        if sys.platform.startswith('win'):
            tcpat = 'tc3*.exe'
        else:
            tcpat = 'tc3*'
        # THERMOCALC exe
        for p in workdir.glob(tcpat):
            if p.is_file() and os.access(str(p), os.X_OK):
                tcexe = p.resolve()
                break
        # default exe
        if sys.platform.startswith('win'):
            drpat = 'dr1*.exe'
        else:
            drpat = 'dr1*'
        # DRAWPD exe
        for p in workdir.glob(drpat):
            if p.is_file() and os.access(str(p), os.X_OK):
                drexe = p.resolve()
                break
        if not tcexe:
            raise InitError('No THERMOCALC executable in {} directory.'.format(workdir))
        # TC version
        errinfo = 'THERMOCALC executable test.'
        if sys.platform.startswith('win'):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags = 1
            startupinfo.wShowWindow = 0
        else:
            startupinfo = None
        p = subprocess.Popen(str(tcexe), cwd=str(workdir), startupinfo=startupinfo, **popen_kw)
        out, err = p.communicate(input='kill\n\n'.encode(TCenc))
        if err is not None:
            print(err.decode('utf-8'))
        sys.stdout.flush()
        output = out.decode(TCenc)
        if float(output.split('\n')[0].split()[1]) < 3.5:
            api = TC34API(workdir, tcexe, drexe)
            if api.OK:
                return api, True
            else:
                return api.status, False
        else:
            api = TC35API(workdir, tcexe, drexe)
            if api.OK:
                return api, True
            else:
                return api.status, False
    except BaseException as e:
        if isinstance(e, InitError) or isinstance(e, ScriptfileError) or isinstance(e, TCError):
            status = '{}: {}'.format(type(e).__name__, str(e))
        else:
            status = '{}: {} {}'.format(type(e).__name__, str(e), errinfo)
        return status, False


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

    def __str__(self):
        return str(self.workdir)

    def __repr__(self):
        if self.OK:
            return '\n'.join(
                [
                    '{}'.format(self.tcversion),
                    'Working directory: {}'.format(self.workdir),
                    'Scriptfile: {}'.format('tc-' + self.name + '.txt'),
                    'AX file: {}'.format('tc-' + self.axname + '.txt'),
                    'Status: {}'.format(self.status),
                ]
            )
        else:
            return '\n'.join(
                ['Uninitialized working directory {}'.format(self.workdir), 'Status: {}'.format(self.status)]
            )

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
        """str: THERMOCALC version string"""
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

    def parse_dogmin(self):
        """Dogmin parser."""
        try:
            with self.icfile.open('r', encoding=self.TCenc) as f:
                resic = f.read()
        except Exception:
            resic = None
        try:
            with self.logfile.open('r', encoding=self.TCenc) as f:
                output = f.read().split('##########################################################\n')[-1]
        except Exception:
            output = None
        return output, resic

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


class TC35API(TCAPI):
    def __init__(self, workdir, tcexe, drexe, encoding='mac-roman'):
        self.workdir = Path(workdir).resolve()
        self.tcexe = tcexe
        self.drexe = drexe
        self.TCenc = encoding
        try:
            # TC version
            errinfo = 'THERMOCALC executable test.'
            self.tcout = self.runtc('\nkill\n\n')
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
                            raise InitError(
                                'tc-prefs: scriptfile tc-'
                                + self.name
                                + '.txt does not exists in your working directory.'
                            )
                        if len(self.name) > 15:
                            raise InitError(
                                'tc-prefs: scriptfile name is longer than 15 characters. It cause troubles for THERMOCALC. Please rename scriptfile to shorter name.'
                            )
                    if kw[0] == 'calcmode':
                        if kw[1] != '1':
                            raise InitError('tc-prefs: calcmode must be 1.')
                    if kw[0] == 'dontwrap':
                        if kw[1] != 'no':
                            raise InitError('tc-prefs: dontwrap must be no.')
            # defaults
            self.ptx_steps = 20  # IS IT NEEDED ????
            # Checks run output
            if 'exit, and correct the scriptfile ?' in self.tcout:
                raise ScriptfileError(self.tcout.split('exit, and correct the scriptfile ?')[0].split('\n')[-4])
            # Checks various settings
            errinfo = 'Scriptfile error!'
            with self.scriptfile.open('r', encoding=self.TCenc) as f:
                r = f.read()
            lines = [ln.strip() for ln in r.splitlines() if ln.strip() != '']
            lines = lines[: lines.index('*')]  # remove part not used by TC
            # Check pypsbuilder blocks
            if not ('%{PSBGUESS-BEGIN}' in lines and '%{PSBGUESS-END}' in lines):
                raise ScriptfileError('There are not {PSBGUESS-BEGIN} and {PSBGUESS-END} tags in your scriptfile.')
            if not ('%{PSBCALC-BEGIN}' in lines and '%{PSBCALC-END}' in lines):
                raise ScriptfileError('There are not {PSBCALC-BEGIN} and {PSBCALC-END} tags in your scriptfile.')
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
                self.bulk.append(scripts['bulk'][2].split()[: len(self.bulk[0])])  # remove possible number of steps
            # try to get actual bulk from output
            self.usedbulk = None
            if 'specification of bulk composition' in self.tcout:
                try:
                    part = self.tcout.split('specification of bulk composition')[1].split(
                        '<==========================================================>'
                    )[0]
                    lns = [ln for ln in part.split(os.linesep) if ln.startswith(' ')]
                    self.usedbulk = []
                    self.usedbulk.append(lns[0].split())
                    self.usedbulk.append(lns[1].split())
                    if len(lns) == 3:
                        self.usedbulk.append(lns[2].split()[: len(self.usedbulk[0])])
                except BaseException as e:
                    self.usedbulk = None
            # inexcess
            errinfo = 'Wrong inexcess in scriptfile.'
            if 'setexcess' in scripts:
                raise ScriptfileError('setexcess script depreceated, use inexcess instead.')
            if 'inexcess' in scripts:
                if scripts['inexcess']:
                    self.excess = set(scripts['inexcess'][0].split()) - set(['no'])
                else:
                    raise ScriptfileError('In case of no excess phases, use inexcess no')
            # omit
            errinfo = 'Wrong omit in scriptfile.'
            if 'omit' in scripts:
                self.omit = set(scripts['omit'][0].split())
            else:
                self.omit = set()
            # autoexit
            if 'autoexit' not in scripts:
                raise ScriptfileError('No autoexit script, autoexit must be provided.')
            # whith
            if 'with' in scripts:
                if scripts['with'][0].split()[0] == 'someof':
                    raise ScriptfileError(
                        'Pypsbuilder does not support with sameof <phase list>. Use omit with and omit.'
                    )
            # samecoding
            if 'samecoding' in scripts:
                self.samecoding = [set(sc.split()) for sc in scripts['samecoding']]
            # pseudosection
            if 'pseudosection' not in scripts:
                raise ScriptfileError('No pseudosection script, pseudosection is mandatory script.')
            # dogmin
            if 'dogmin' in scripts:
                raise ScriptfileError('Dogmin script should be removed from scriptfile.')
            # union ax phases and samecoding and diff omit
            if 'BOMBED' in self.tcout:
                raise TCError(self.tcout.split('BOMBED')[1].split(os.linesep)[0])
            else:
                ax_phases = set(self.tcout.split('reading ax:')[1].split(2 * os.linesep)[0].split())
                self.phases = ax_phases.union(*self.samecoding) - self.omit
            # OK
            self.status = 'Initial check done.'
            self.OK = True
        except BaseException as e:
            if isinstance(e, InitError) or isinstance(e, ScriptfileError) or isinstance(e, TCError):
                self.status = '{}: {}'.format(type(e).__name__, str(e))
            else:
                exc_type, exc_obj, exc_tb = sys.exc_info()
                self.status = '{}: {} on line {}'.format(type(e).__name__, str(e), exc_tb.tb_lineno)
            self.OK = False

    def parse_logfile(self, **kwargs):
        """Parser for THERMOCALC 3.50beta output.

        It parses the outputs of THERMOCALC after calculation.

        Args:
            output (str): When not None, used as content of logfile. Default None.
            resic (str): When not None, used as content of icfile. Default None.
            get_phases (bool): When true returns also tuple (phases, out, calcs). Default False

        Returns:
            status (str): Result of parsing. 'ok', 'nir' (nothing in range) or 'bombed'.
            results (TCResultSet): Results of TC calculation.
            output (str): Full nonparsed THERMOCALC output.

        Example:
            Parse output after univariant line calculation in P-T pseudosection::

                >>> tc = TCAPI('pat/to/dir')
                >>> status, result, output = tc.parse_logfile()
        """
        output = kwargs.get('output', None)
        resic = kwargs.get('resic', None)
        get_phases = kwargs.get('get_phases', False)
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
                bstarts = [
                    ix
                    for ix, ln in enumerate(lines)
                    if ln.startswith('------------------------------------------------------------')
                ]
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
                    rlist = [
                        TCResult.from_block(block, ptguess)
                        for block, ptguess, correct in zip(blocks, ptguesses, corrects)
                        if correct
                    ]
                    if len(rlist) > 0:
                        status = 'ok'
                        results = TCResultSet(rlist)
                    else:
                        status = 'nir'
                else:
                    status = 'nir'
            if get_phases:
                phases, out = None, None
                with self.scriptfile.open('r', encoding=self.TCenc) as f:
                    scf = f.read()
                _, rem = scf.split('%{PSBCALC-BEGIN}')
                calc, _ = rem.split('%{PSBCALC-END}')
                calcs = calc.splitlines()
                for ln in calcs:
                    script = ln.split('%')[0].strip()
                    if script.startswith('with'):
                        phases = set(script.split('with', 1)[1].split()).union(self.excess)
                    if script.startswith('zeromodeisopleth'):
                        out = set(script.split('zeromodeisopleth', 1)[1].split())
                return status, results, output, (phases, out, calcs)
            else:
                return status, results, output
        except Exception:
            if get_phases:
                return 'bombed', None, None, (None, None, [])
            else:
                return 'bombed', None, None

    def parse_logfile_backup(self, **kwargs):
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
            bstarts = [
                ix
                for ix, ln in enumerate(lines)
                if ln.startswith('--------------------------------------------------------------------')
            ]
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
                rlist = [
                    TCResult.from_block(block, ptguess)
                    for block, ptguess, correct in zip(blocks, ptguesses, corrects)
                    if correct
                ]
                if len(rlist) > 0:
                    status = 'ok'
                    results = TCResultSet(rlist)
                else:
                    status = 'nir'
            else:
                status = 'nir'
        return status, results, output

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
        calcs = [
            'calcP {:g} {:g} {:g}'.format(*prange, step),
            'calcT {:g} {:g}'.format(*trange),
            'calctatp yes',
            'with {}'.format(' '.join(phases - self.excess)),
            'zeromodeisopleth {}'.format(' '.join(out)),
        ]
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
        calcs = [
            'calcP {:g} {:g}'.format(*prange),
            'calcT {:g} {:g} {:g}'.format(*trange, step),
            'calctatp no',
            'with {}'.format(' '.join(phases - self.excess)),
            'zeromodeisopleth {}'.format(' '.join(out)),
        ]
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
        calcs = [
            'calcP {:g} {:g}'.format(*prange),
            'calcT {:g} {:g}'.format(*trange),
            'with {}'.format(' '.join(phases - self.excess)),
            'zeromodeisopleth {}'.format(' '.join(out)),
        ]
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
            calcs = [
                'calcP {:g} {:g}'.format(*prange),
                'calcT {:g} {:g}'.format(*trange),
                'calctatp yes',
                'with {}'.format(' '.join(phases - self.excess)),
                'zeromodeisopleth {}'.format(' '.join(out)),
                'bulksubrange {:g} {:g}'.format(*xvals),
            ]
        else:
            calcs = [
                'calcP {:g} {:g} {:g}'.format(*prange, step),
                'calcT {:g} {:g}'.format(*trange),
                'calctatp yes',
                'with {}'.format(' '.join(phases - self.excess)),
                'zeromodeisopleth {}'.format(' '.join(out)),
                'bulksubrange {:g} {:g}'.format(*xvals),
            ]
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
            calcs = [
                'calcP {:g} {:g}'.format(*prange),
                'calcT {:g} {:g}'.format(*trange),
                'calctatp no',
                'with {}'.format(' '.join(phases - self.excess)),
                'zeromodeisopleth {}'.format(' '.join(out)),
                'bulksubrange {:g} {:g}'.format(*xvals),
            ]
        else:
            calcs = [
                'calcP {:g} {:g}'.format(*prange),
                'calcT {:g} {:g} {:g}'.format(*trange, step),
                'calctatp no',
                'with {}'.format(' '.join(phases - self.excess)),
                'zeromodeisopleth {}'.format(' '.join(out)),
                'bulksubrange {:g} {:g}'.format(*xvals),
            ]
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
        calcs = ['calcP {}'.format(p), 'calcT {}'.format(t), 'with {}'.format(' '.join(phases - self.excess))]
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
        calcs = [
            'calcP {}'.format(p),
            'calcT {}'.format(t),
            'dogmin yes {}'.format(doglevel),
            'with {}'.format(' '.join(phases - self.excess)),
            'maxvar {}'.format(variance),
        ]
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
        calcs = [
            'calcP {} {}'.format(*self.prange),
            'calcT {} {}'.format(*self.trange),
            'with {}'.format(' '.join(phases - self.excess)),
            'acceptvar no',
        ]
        old_calcs = self.update_scriptfile(get_old_calcs=True, calcs=calcs)
        tcout = self.runtc('kill\n\n')
        self.update_scriptfile(calcs=old_calcs)
        for ln in tcout.splitlines():
            if 'variance of required equilibrium' in ln:
                variance = int(ln[ln.index('(') + 1 : ln.index('?')])
                break
        return variance


class TC34API(TCAPI):
    def __init__(self, workdir, tcexe, drexe, encoding='mac-roman'):
        self.workdir = Path(workdir).resolve()
        self.tcexe = tcexe
        self.drexe = drexe
        self.TCenc = encoding
        try:
            # TC version
            errinfo = 'THERMOCALC executable test.'
            self.tcout = self.runtc()
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
                            raise InitError(
                                'tc-prefs: scriptfile tc-'
                                + self.name
                                + '.txt does not exists in your working directory.'
                            )
                    if kw[0] == 'calcmode':
                        if kw[1] != '1':
                            raise InitError('tc-prefs: calcmode must be 1.')

            errinfo = 'Scriptfile error!'
            self.excess = set()
            self.trange = (200.0, 1000.0)
            self.prange = (0.1, 20.0)
            self.bulk = []
            self.ptx_steps = 20
            check = {'axfile': False, 'setbulk': False, 'printbulkinfo': False, 'setexcess': False, 'printxyz': False}
            errinfo = 'Check your scriptfile.'
            with self.scriptfile.open('r', encoding=self.TCenc) as f:
                lines = f.readlines()
            gsb, gse = False, False
            dgb, dge = False, False
            bub, bue = False, False
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
                if '{PSBBULK-BEGIN}' in line:
                    bub = True
                if '{PSBBULK-END}' in line:
                    bue = True
                if kw == ['*']:
                    break
                if kw:
                    if kw[0] == 'axfile':
                        errinfo = 'Wrong argument for axfile keyword in scriptfile.'
                        self.axname = kw[1]
                        if not self.axfile.exists():
                            raise ScriptfileError(
                                'Axfile ' + str(self.axfile) + ' does not exists in working directory'
                            )
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
                        if 'ask' in bulk:
                            raise ScriptfileError('Setbulk must not be set to ask.')
                        if 'yes' in bulk:
                            bulk.remove('yes')
                        if 'no' not in bulk:
                            if len(self.bulk) == 1:
                                if len(self.bulk[0]) < len(bulk):
                                    self.ptx_steps = int(bulk[-1])
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
                raise ScriptfileError(
                    'Setexcess must not be set to ask. To suppress this error put empty setexcess keyword to your scriptfile.'
                )
            # if not check['drawpd']:
            #     raise ScriptfileError('Drawpd must be set to yes. To suppress this error put drawpd yes keyword to your scriptfile.')
            if not check['printbulkinfo']:
                raise ScriptfileError(
                    'Printbulkinfo must be set to yes. To suppress this error put printbulkinfo yes keyword to your scriptfile.'
                )
            if not check['printxyz']:
                raise ScriptfileError(
                    'Printxyz must be set to yes. To suppress this error put printxyz yes keyword to your scriptfile.'
                )
            if not (gsb and gse):
                raise ScriptfileError('There are not {PSBGUESS-BEGIN} and {PSBGUESS-END} tags in your scriptfile.')
            if not (dgb and dge):
                raise ScriptfileError('There are not {PSBDOGMIN-BEGIN} and {PSBDOGMIN-END} tags in your scriptfile.')
            if not (bub and bue):
                raise ScriptfileError('There are not {PSBBULK-BEGIN} and {PSBBULK-END} tags in your scriptfile.')

            # TC
            if 'BOMBED' in self.tcout:
                raise TCError(self.tcout.split('BOMBED')[1].split('\n')[0])
            else:
                self.phases = set(self.tcout.split('choose from:')[1].split('\n')[0].split())
            # OK
            self.status = 'Initial check done.'
            self.OK = True
        except BaseException as e:
            if isinstance(e, InitError) or isinstance(e, ScriptfileError) or isinstance(e, TCError):
                self.status = '{}: {}'.format(type(e).__name__, str(e))
            else:
                self.status = '{}: {} {}'.format(type(e).__name__, str(e), errinfo)
            self.OK = False

    def parse_logfile(self, **kwargs):
        """Parser for THERMOCALC 3.4x output.

        It parses the outputs of THERMOCALC after calculation.

        Args:
            output (str): When not None, used as content of logfile. Default None.
            resic (str): When not None, used as content of icfile. Default None.
            get_phases (bool): When true returns also tuple (phases, out, calcs). Default False

        Returns:
            status (str): Result of parsing. 'ok', 'nir' (nothing in range) or 'bombed'.
            results (TCResultSet): Results of TC calculation.
            output (str): Full nonparsed THERMOCALC output.

        Example:
            Parse output after univariant line calculation in P-T pseudosection::

                >>> tc = TCAPI('pat/to/dir')
                >>> status, result, output = tc.parse_logfile()
        """
        output = kwargs.get('output', None)
        get_phases = kwargs.get('get_phases', False)
        try:
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
                        variance = int(ln[ln.index('(') + 1 : ln.index('?')])
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
                        phase, comp = lbl[lbl.find('(') + 1 : lbl.find(')')], lbl[: lbl.find('(')]
                        if phase not in data:
                            raise Exception(
                                'Check model {} in your ax file. Commonly liq coded as L for starting guesses.'.format(
                                    phase
                                )
                            )
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
                    results = TCResultSet(
                        [
                            TCResult(T, p, variance=variance, c=0.0, data=r['data'], ptguess=r['ptguess'])
                            for (r, p, T) in zip(res, pp, TT)
                        ]
                    )
                else:
                    status = 'nir'
                    results = None
            if get_phases:
                phases, out = None, None
                for ln in output.splitlines():
                    if ln.startswith('which phases'):
                        phases = set(ln.split(':', 1)[1].split())
                    if ln.startswith('which to set'):
                        out = set(ln.split(':', 1)[1].split())
                return status, results, output, (phases, out, [])
            else:
                return status, results, output
        except Exception:
            if get_phases:
                return 'bombed', None, None, (None, None, '')
            else:
                return 'bombed', None, None

    def update_scriptfile(self, **kwargs):
        """Method to update scriptfile.

        This methodcould be used to read or update ptguess or dogmin settings.

        Args:
            guesses (list): List of lines defining ptguesses. If None guesses
                are not modified. Default None.
            get_old_guesses (bool): When True method returns existing ptguess
                before possible modification. Default False.
            dogmin (str): Argument of dogmin script. Could be 'no' or 'yes' or
                'yes X', where X is log level. When None no modification is
                done. Default None.
            which (set): Set of phases used for dogmin.
            bulk (list): Bulk composition. Default None.
            xvals (tuple): x values for compositions. Default (0, 1)
            xsteps (int): Number of compositional steps between two bulks.
                Default 20.
            p (float): Pressure for dogmin calculation
            T (float): Temperature for dogmin calculation
        """
        guesses = kwargs.get('guesses', None)
        get_old_guesses = kwargs.get('get_old_guesses', False)
        dogmin = kwargs.get('dogmin', None)  # None or 'no' or 'yes 1'
        which = kwargs.get('which', None)
        bulk = kwargs.get('bulk', None)
        xvals = kwargs.get('xvals', (0, 1))
        xsteps = kwargs.get('xsteps', 20)
        p = kwargs.get('p', None)
        T = kwargs.get('T', None)
        with self.scriptfile.open('r', encoding=self.TCenc) as f:
            sc = f.readlines()
        changed = False
        gsb = [ix for ix, ln in enumerate(sc) if ln.startswith('%{PSBGUESS-BEGIN}')]
        gse = [ix for ix, ln in enumerate(sc) if ln.startswith('%{PSBGUESS-END}')]
        if get_old_guesses:
            if gsb and gse:
                old_guesses = [ln.strip() for ln in sc[gsb[0] + 1 : gse[0]]]
        if guesses is not None:
            if gsb and gse:
                sc = sc[: gsb[0] + 1] + [gln + '\n' for gln in guesses] + sc[gse[0] :]
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
                sc = sc[: dgb[0] + 1] + dglines + sc[dge[0] :]
                changed = True
        if bulk is not None:
            bub = [ix for ix, ln in enumerate(sc) if ln.startswith('%{PSBBULK-BEGIN}')]
            bue = [ix for ix, ln in enumerate(sc) if ln.startswith('%{PSBBULK-END}')]
            bulines = []
            if len(bulk) == 2:
                bulines.append('setbulk yes {} % x={:g}\n'.format(' '.join(bulk[0]), xvals[0]))
                bulines.append('setbulk yes {} {:d} % x={:g}\n'.format(' '.join(bulk[1]), xsteps, xvals[1]))
            else:
                bulines.append('setbulk yes {}\n'.format(' '.join(bulk[0])))
            if bub and bue:
                sc = sc[: bub[0] + 1] + bulines + sc[bue[0] :]
                changed = True
        if changed:
            with self.scriptfile.open('w', encoding=self.TCenc) as f:
                for ln in sc:
                    f.write(ln)
        if get_old_guesses:
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

    def parse_kwargs(self, **kwargs):
        prange = kwargs.get('prange', self.prange)
        trange = kwargs.get('trange', self.trange)
        steps = kwargs.get('steps', 50)
        if np.diff(prange)[0] < 0.001:
            prec = kwargs.get('prec', max(int(2 - np.floor(np.log10(np.diff(trange)[0]))), 0) + 1)
        elif np.diff(trange)[0] < 0.001:
            prec = kwargs.get('prec', max(int(2 - np.floor(np.log10(np.diff(prange)[0]))), 0) + 1)
        else:
            prec = kwargs.get(
                'prec', max(int(2 - np.floor(np.log10(min(np.diff(trange)[0], np.diff(prange)[0])))), 0) + 1
            )
        return prange, trange, steps, prec

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
        prange, trange, steps, prec = self.parse_kwargs(**kwargs)
        step = (prange[1] - prange[0]) / steps
        tmpl = '{}\n\n{}\ny\n{:.{prec}f} {:.{prec}f}\n{:.{prec}f} {:.{prec}f}\n{:g}\nn\n\nkill\n\n'
        ans = tmpl.format(' '.join(phases), ' '.join(out), *prange, *trange, step, prec=prec)
        tcout = self.runtc(ans)
        return tcout, ans

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
        prange, trange, steps, prec = self.parse_kwargs(**kwargs)
        step = (trange[1] - trange[0]) / steps
        tmpl = '{}\n\n{}\nn\n{:.{prec}f} {:.{prec}f}\n{:.{prec}f} {:.{prec}f}\n{:g}\nn\n\nkill\n\n'
        ans = tmpl.format(' '.join(phases), ' '.join(out), *trange, *prange, step, prec=prec)
        tcout = self.runtc(ans)
        return tcout, ans

    def calc_pt(self, phases, out, **kwargs):
        """Method to run THERMOCALC to find invariant point.

        Args:
            phases (set): Set of present phases
            out (set): Set of two zero mode phases
            prange (tuple): Temperature range for calculation
            trange (tuple): Pressure range for calculation
            steps (int): Number of steps

        Returns:
            tuple: (tcout, ans) standard output and input for THERMOCALC run.
            Input ans could be used to reproduce calculation.
        """
        prange, trange, steps, prec = self.parse_kwargs(**kwargs)
        tmpl = '{}\n\n{}\n{:.{prec}f} {:.{prec}f} {:.{prec}f} {:.{prec}f}\nn\n\nkill\n\n'
        ans = tmpl.format(' '.join(phases), ' '.join(out), *trange, *prange, prec=prec)
        tcout = self.runtc(ans)
        return tcout, ans

    def calc_tx(self, phases, out, **kwargs):
        """Method to run THERMOCALC for T-X pseudosection calculations.

        Args:
            phases (set): Set of present phases
            out (set): Set of zero mode phases
            prange (tuple): Temperature range for calculation
            trange (tuple): Pressure range for calculation
            steps (int): Number of steps

        Returns:
            tuple: (tcout, ans) standard output and input for THERMOCALC run.
            Input ans could be used to reproduce calculation.
        """
        prange, trange, steps, prec = self.parse_kwargs(**kwargs)
        if len(out) > 1:
            tmpl = '{}\n\n{}\n{:.{prec}f} {:.{prec}f} {:.{prec}f} {:.{prec}f}\nn\n\nkill\n\n'
            ans = tmpl.format(' '.join(phases), ' '.join(out), *trange, *prange, prec=prec)
        else:
            tmpl = '{}\n\n{}\ny\n\n{:.{prec}f} {:.{prec}f}\nn\nkill\n\n'
            ans = tmpl.format(' '.join(phases), ' '.join(out), *trange, prec=prec)
        tcout = self.runtc(ans)
        return tcout, ans

    def calc_px(self, phases, out, **kwargs):
        """Method to run THERMOCALC for P-X pseudosection calculations.

        Args:
            phases (set): Set of present phases
            out (set): Set of zero mode phases
            prange (tuple): Temperature range for calculation
            trange (tuple): Pressure range for calculation
            steps (int): Number of steps

        Returns:
            tuple: (tcout, ans) standard output and input for THERMOCALC run.
            Input ans could be used to reproduce calculation.
        """
        prange, trange, steps, prec = self.parse_kwargs(**kwargs)
        if len(out) > 1:
            tmpl = '{}\n\n{}\n{:.{prec}f} {:.{prec}f} {:.{prec}f} {:.{prec}f}\nn\n\nkill\n\n'
            ans = tmpl.format(' '.join(phases), ' '.join(out), *trange, *prange, prec=prec)
        else:
            tmpl = '{}\n\n{}\nn\n\n{:.{prec}f} {:.{prec}f}\nn\nkill\n\n'
            ans = tmpl.format(' '.join(phases), ' '.join(out), *prange, prec=prec)
        tcout = self.runtc(ans)
        return tcout, ans

    def calc_assemblage(self, phases, p, t):
        """Method to run THERMOCALC to calculate compositions of stable assemblage.

        Args:
            phases (set): Set of present phases
            p (float): Temperature for calculation
            t (float): Pressure for calculation

        Returns:
            tuple: (tcout, ans) standard output and input for THERMOCALC run.
            Input ans could be used to reproduce calculation.
        """
        tmpl = '{}\n\n\n{}\n{}\nkill\n\n'
        ans = tmpl.format(' '.join(phases), p, t)
        tcout = self.runtc(ans)
        return tcout, ans

    def dogmin(self, phases, p, t, variance, doglevel=1, onebulk=None):
        """Run THERMOCALC dogmin session.

        Args:
            variance (int): Maximum variance to be considered

        Returns:
            str: THERMOCALC standard output
        """
        self.update_scriptfile(
            dogmin='yes {}'.format(doglevel), which=phases, T='{:.3f}'.format(t), p='{:.3f}'.format(p)
        )
        tmpl = '{}\n\nn\n\n'
        ans = tmpl.format(variance)
        tcout = self.runtc(ans)
        self.update_scriptfile(dogmin='no')
        return tcout

    def calc_variance(self, phases):
        """Get variance of assemblage.

        Args:
            phases (set): Set of present phases

        Returns:
            int: variance
        """
        variance = None
        tcout = self.tc.runtc('{}\nkill\n\n'.format(' '.join(phases)))
        for ln in tcout.splitlines():
            if 'variance of required equilibrium' in ln:
                variance = int(ln[ln.index('(') + 1 : ln.index('?')])
                break
        return variance
