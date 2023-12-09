"""THERMOCALC API classes.

This module contain function to initialize working directory. It will
download the latest 3.5 version of THERMOCALC and appropriate dataset
and ax file according to user selection

"""
# author: Ondrej Lexa
# website: https://github.com/ondrolexa/pypsbuilder

from pathlib import Path
import platform
from io import BytesIO
import shutil
from urllib.request import urlopen
from zipfile import ZipFile
import unicodedata
import string

# recent files
set_urls = {
    'metapelite': 'https://hpxeosandthermocalc.files.wordpress.com/2022/01/tc-thermoinput-metapelite-2022-01-23.zip',
    'metabasite': 'https://hpxeosandthermocalc.files.wordpress.com/2022/01/tc-thermoinput-metabasite-2022-01-30.zip',
    'igneous': 'https://hpxeosandthermocalc.files.wordpress.com/2022/01/tc-thermoinput-igneous-2022-01-23.zip',
}

exe_urls = {
    'linux': 'https://hpxeosandthermocalc.files.wordpress.com/2020/12/tc350beta-linux-bundle.zip',
    'win': 'https://hpxeosandthermocalc.files.wordpress.com/2020/12/tc350-win-bundle.zip',
    'mac': 'https://hpxeosandthermocalc.files.wordpress.com/2020/12/tc350beta-mac-bundle.zip',
    'macasi': 'https://hpxeosandthermocalc.files.wordpress.com/2020/12/tc350beta-macasi-bundle.zip',
}


def tcprojinit():
    cwd = Path.cwd()
    dir_needed = True
    while dir_needed:
        dest_tmp = input(f'Enter project directory [{cwd}]: ')
        if dest_tmp == '':
            dest = cwd
        else:
            dest = Path(dest_tmp)
        if dest.is_dir():
            if not any(dest.iterdir()):
                dir_needed = False
            else:
                print(f'ERROR: {dest} is not empty...')
        else:
            print(f'ERROR: {dest} is not valid directory...')

    projname_needed = True
    whitelist = f'_{string.ascii_letters}{string.digits}'
    while projname_needed:
        projname = input('Enter name of the project (max 8 chars) [project]: ')
        if projname == '':
            projname = 'project'
        # replace spaces
        projname = projname.replace(' ', '_')
        # keep only valid ascii chars
        projname = unicodedata.normalize('NFKD', projname).encode('ASCII', 'ignore').decode()
        # keep only whitelisted chars
        projname = ''.join(c for c in projname if c in whitelist)
        if len(projname) < 1:
            print('ERROR: project name may not be empty')
        elif len(projname) > 8:
            print('ERROR: project name may not be longer than 8 characters')
        else:
            projname_needed = False

    set_needed = True
    sets = {1: 'metapelite', 2: 'metabasite', 3: 'igneous'}
    while set_needed:
        print('Choose THEMOCALC input set')
        for k in sets:
            print(f' {k}. {sets[k]} set')
        try:
            n = input('Which set? [1]: ')
            if n == '':
                n = '1'
            if int(n) in [1, 2, 3]:
                set_needed = False
        except ValueError:
            print('ERROR: enter 1, 2 or 3')
    tcset = sets[int(n)]

    if tcset == 'metapelite':
        ds = '62'
        systems = {1: 'mp50MnNCKFMASHTO', 2: 'mp50NCKFMASHTO', 3: 'mp50KFMASH'}
        system_needed = True
        while system_needed:
            print('Choose system for metapelite set')
            for k in systems:
                print(f' {k}. {systems[k]}')
            try:
                v = input('Which system? [1]: ')
                if v == '':
                    v = '1'
                if int(v) in [1, 2, 3]:
                    system_needed = False
            except ValueError:
                print('ERROR: enter 1, 2 or 3')
        system = systems[int(v)]
        guesses = metapelite_guesses[system]
    elif tcset == 'metabasite':
        ds = '62'
        system = 'mb50NCKFMASHTO'
        guesses = metabasite_guesses[system]
    else:
        ds = '633'
        systems = {1: 'ig50NCKFMASHTOCr', 2: 'ig50NCKFMASTOCr'}
        system_needed = True
        while system_needed:
            print('Choose system for igneous set')
            for k in systems:
                print(f' {k}. {systems[k]}')
            try:
                v = input('Which system? [1]: ')
                if v == '':
                    v = '1'
                if int(v) in [1, 2]:
                    system_needed = False
            except ValueError:
                print('ERROR: enter 1 or 2')
        system = systems[int(v)]
        guesses = igneous_guesses[system]

    # create prefs file
    with open(dest / 'tc-prefs.txt', 'w') as f:
        content = string.Template(tcpref_tmpl).substitute(dataset=ds, project=projname)[1:]
        f.write(content)

    # download executable
    comp = platform.system()
    if comp == 'Linux':
        with urlopen(exe_urls['linux']) as zip:
            with ZipFile(BytesIO(zip.read())) as zfile:
                source = zfile.open('tc350beta-linux-bundle/tc350beta')
                target = open(dest / 'tc350beta', 'wb')
                with source, target:
                    shutil.copyfileobj(source, target)
                Path(dest / 'tc350beta').chmod(33261)
    elif comp == 'Windows':
        with urlopen(exe_urls['win']) as zip:
            with ZipFile(BytesIO(zip.read())) as zfile:
                source = zfile.open('tc350-win-bundle/tc350beta.exe')
                target = open(dest / 'tc350beta.exe', 'wb')
                with source, target:
                    shutil.copyfileobj(source, target)
                Path(dest / 'tc350beta.exe').chmod(33261)
    elif comp == 'Darwin':
        proc = platform.processor()
        if proc == 'x86_64':
            with urlopen(exe_urls['mac']) as zip:
                with ZipFile(BytesIO(zip.read())) as zfile:
                    source = zfile.open('tc350beta-bundle/tc350beta')
                    target = open(dest / 'tc350beta', 'wb')
                    with source, target:
                        shutil.copyfileobj(source, target)
                    Path(dest / 'tc350beta').chmod(33261)
        elif proc == 'arm':
            with urlopen(exe_urls['macasi']) as zip:
                with ZipFile(BytesIO(zip.read())) as zfile:
                    source = zfile.open('tc350beta-macASi-bundle/tc350si')
                    target = open(dest / 'tc350si', 'wb')
                    with source, target:
                        shutil.copyfileobj(source, target)
                    Path(dest / 'tc350si').chmod(33261)
        else:
            raise AttributeError(f'Unsupported MacOS {proc} processor')
    else:
        raise AttributeError(f'Unsupported {comp} platform')

    # download set
    tcset_url = set_urls[tcset]
    prefix = tcset_url.split('/')[-1].split('.')[0]
    with urlopen(tcset_url) as zip:
        with ZipFile(BytesIO(zip.read())) as zfile:
            with zfile.open(f'{prefix}/samecoding_and_starting_guesses.txt') as f:
                scsg = f.readlines()
            scsg = [s.decode('mac-roman') for s in scsg]
            samecoding = ''.join([ln for ln in scsg if ln.startswith('samecoding')])
            source = zfile.open(f'{prefix}/tc-ds{ds}.txt')
            target = open(dest / f'tc-ds{ds}.txt', 'wb')
            with source, target:
                shutil.copyfileobj(source, target)
            source = zfile.open(f'{prefix}/tc-{system}.txt')
            target = open(dest / f'tc-{system}.txt', 'wb')
            with source, target:
                shutil.copyfileobj(source, target)

    # create project file
    with open(dest / f'tc-{projname}.txt', 'w') as f:
        content = string.Template(tcprj_tmpl).substitute(
            system=system, project=projname, samecoding=samecoding, guesses=guesses
        )[1:]
        f.write(content)


tcpref_tmpl = """
setpagewidth 700
dataset $dataset
scriptfile $project
calcmode 1
*
"""

metapelite_guesses = {
    'mp50KFMASH': '''
% --------------------------------------------------------
%  Starting guesses in KFMASH
%  for g liq mu bi opx sa cd st chl ctd sp1
% --------------------------------------------------------

xyzguess x(g)          0.828230

xyzguess q(liq)        0.361210
xyzguess fsp(liq)      0.298204
xyzguess ol(liq)      0.0452697
xyzguess x(liq)        0.811725
xyzguess h2o(liq)      0.273973

xyzguess x(mu)         0.424480
xyzguess y(mu)         0.855215  range  0.000 2.000

xyzguess x(bi)         0.515248
xyzguess y(bi)         0.181294
xyzguess Q(bi)         0.135847

xyzguess x(opx)        0.725005
xyzguess y(opx)        0.157290  range  0.000 2.000
xyzguess Q(opx)        0.258819

xyzguess  x(sa)         0.1
xyzguess  y(sa)         0.3
xyzguess  Q(sa)         0.05 range -1 1

xyzguess x(cd)         0.529141
xyzguess h(cd)         0.259128

xyzguess x(st)         0.9

xyzguess x(chl)        0.412420
xyzguess y(chl)        0.610079
xyzguess QAl(chl)      0.389713  range -1.000 1.000
xyzguess Q1(chl)      0.0751369  range -1.000 1.000
xyzguess Q4(chl)      0.0641869  range -1.000 1.000

xyzguess x(ctd)           0.88

xyzguess x(sp1)           0.9
''',
    'mp50NCKFMASHTO': '''
% --------------------------------------------------------
%  Starting guesses in NCKFMASHTO
%  for g liq pl ksp ep ma mu pa bi opx sa cd st chl ctd sp mt ilmm hemm ilm hem mt1
% --------------------------------------------------------

xyzguess x(g)          0.833575
xyzguess z(g)         0.0735303
xyzguess f(g)         0.0524207

xyzguess q(L)          0.260829
xyzguess fsp(L)        0.332998
xyzguess na(L)         0.267890
xyzguess an(L)        0.0124108
xyzguess ol(L)       0.00460699
xyzguess x(L)          0.799969
xyzguess h2o(L)        0.376568

xyzguess ca(pl4tr)        0.410144
xyzguess k(pl4tr)        0.0182303

xyzguess na(k4tr)       0.159152
xyzguess ca(k4tr)     0.00450582

xyzguess f(ep)         0.379418
xyzguess Q(ep)         0.346850  range  0.000 0.500

xyzguess x(ma)         0.6
xyzguess y(ma)         0.96
xyzguess f(ma)         0.001
xyzguess n(ma)         0.05
xyzguess c(ma)         0.94

xyzguess x(mu)         0.501982
xyzguess y(mu)         0.839614
xyzguess f(mu)        0.0172093
xyzguess n(mu)         0.144000
xyzguess c(mu)       0.00179401

xyzguess x(pa)         0.501982
xyzguess y(pa)         0.998030
xyzguess f(pa)       0.00182412
xyzguess n(pa)         0.945628
xyzguess c(pa)        0.0116010

xyzguess x(bi)         0.698859
xyzguess y(bi)         0.268818
xyzguess f(bi)         0.158096
xyzguess t(bi)        0.0981352
xyzguess Q(bi)        0.0683120

xyzguess x(opx)        0.811609
xyzguess y(opx)        0.128377  range  0.000 2.000
xyzguess f(opx)            0.01
xyzguess c(opx)            0.01
xyzguess Q(opx)        0.216433

xyzguess  x(sa)            0.1
xyzguess  y(sa)            0.3
xyzguess  f(sa)            0.05
xyzguess  Q(sa)            0.05 range -1 1

xyzguess x(cd)         0.480790
xyzguess h(cd)         0.427693

xyzguess  x(st)            0.88
xyzguess  f(st)            0.05
xyzguess  t(st)            0.04

xyzguess x(chl)        0.551609
xyzguess y(chl)        0.328449
xyzguess f(chl)        0.418479
xyzguess QAl(chl)      0.253018  range -1.000 1.000
xyzguess Q1(chl)       0.123137  range -1.000 1.000
xyzguess Q4(chl)       0.121632  range -1.000 1.000

xyzguess x(ctd)        0.990857
xyzguess f(ctd)            0.01

xyzguess  x(sp)    0.6
xyzguess  y(sp)    0.95
xyzguess  z(sp)    0.01

xyzguess  x(mt)    0.85
xyzguess  y(mt)    0.05
xyzguess  z(mt)    0.01

xyzguess i(ilmm)       0.890349
xyzguess g(ilmm)      0.0148847
xyzguess Q(ilmm)       0.828083  range -1.000 1.000

xyzguess i(hemm)       0.380640
xyzguess g(hemm)     0.00296953
xyzguess Q(hemm)     -0.0102634  range -0.300 0.300

xyzguess  x(ilm)       0.80
xyzguess  Q(ilm)       0.8   range -0.99 0.99

xyzguess  x(hem)       0.20
xyzguess  Q(hem)       0.8   range -0.99 0.99

xyzguess x(mt1)        0.683170
xyzguess Q(mt1)        0.727847
''',
    'mp50MnNCKFMASHTO': '''
% --------------------------------------------------------
%  Starting guesses in MnNCKFMASHTO
%  for g liq pl ksp ep ma mu pa bi opx sa cd st chl ctd sp mt ilmm hemm ilm hem mt1
% --------------------------------------------------------


xyzguess x(g)          0.824169
xyzguess z(g)         0.0317199
xyzguess m(g)          0.118530
xyzguess f(g)         0.0260643

xyzguess q(L)          0.173460
xyzguess fsp(L)        0.311414
xyzguess na(L)         0.443405
xyzguess an(L)       0.00913561
xyzguess ol(L)       0.00192499
xyzguess x(L)          0.746571
xyzguess h2o(L)        0.485792

xyzguess ca(pl)        0.377110
xyzguess k(pl)        0.0370401

xyzguess na(ksp)       0.227897
xyzguess ca(ksp)      0.0114380

xyzguess f(ep)         0.379418
xyzguess Q(ep)         0.346850  range  0.000 0.500

xyzguess x(ma)         0.6
xyzguess y(ma)         0.96
xyzguess f(ma)         0.001
xyzguess n(ma)         0.05
xyzguess c(ma)         0.94

xyzguess x(mu)         0.501982
xyzguess y(mu)         0.839614
xyzguess f(mu)        0.0172093
xyzguess n(mu)         0.144000
xyzguess c(mu)       0.00179401

xyzguess x(pa)         0.501982
xyzguess y(pa)         0.998030
xyzguess f(pa)       0.00182412
xyzguess n(pa)         0.945628
xyzguess c(pa)        0.0116010

xyzguess x(bi)         0.607873
xyzguess m(bi)       0.00462747
xyzguess y(bi)         0.264120
xyzguess f(bi)         0.132141
xyzguess t(bi)         0.140166
xyzguess Q(bi)        0.0850578

xyzguess x(opx)        0.811609
xyzguess m(opx)           0.001
xyzguess y(opx)        0.128377  range  0.000 2.000
xyzguess f(opx)            0.01
xyzguess c(opx)            0.01
xyzguess Q(opx)        0.216433

xyzguess  x(sa)            0.1
xyzguess  y(sa)            0.3
xyzguess  f(sa)            0.05
xyzguess  Q(sa)            0.05 range -1 1

xyzguess x(cd)         0.407167
xyzguess m(cd)        0.0213095
xyzguess h(cd)         0.597164

xyzguess  x(st)            0.88
xyzguess  m(st)            0.02
xyzguess  f(st)            0.05
xyzguess  t(st)            0.04

xyzguess x(chl)        0.551609
xyzguess y(chl)        0.328449
xyzguess f(chl)        0.418479
xyzguess m(chl)      0.00762984
xyzguess QAl(chl)      0.253018  range -1.000 1.000
xyzguess Q1(chl)       0.123137  range -1.000 1.000
xyzguess Q4(chl)       0.121632  range -1.000 1.000

xyzguess x(ctd)        0.990857
xyzguess m(ctd)           0.001
xyzguess f(ctd)            0.01

xyzguess  x(sp)    0.6
xyzguess  y(sp)    0.95
xyzguess  z(sp)    0.01

xyzguess  x(mt)    0.85
xyzguess  y(mt)    0.05
xyzguess  z(mt)    0.01

xyzguess i(ilmm)       0.858568
xyzguess g(ilmm)      0.0294376
xyzguess m(ilmm)      0.0323075
xyzguess Q(ilmm)       0.691587  range -1.000 1.000

xyzguess i(hemm)       0.380640
xyzguess g(hemm)     0.00296953
xyzguess m(hemm)      0.0305831
xyzguess Q(hemm)     -0.0102634  range -0.300 0.300

xyzguess  x(ilm)       0.80
xyzguess  Q(ilm)       0.8   range -0.99 0.99

xyzguess  x(hem)       0.20
xyzguess  Q(hem)       0.8   range -0.99 0.99

xyzguess x(mt1)        0.632160
xyzguess Q(mt1)        0.564334
''',
}

metabasite_guesses = {
    'mb50NCKFMASHTO': '''
% -------------------
xyzguess q(L)          0.151242
xyzguess fsp(L)        0.248743
xyzguess na(L)         0.807843
xyzguess wo(L)        0.0684231
xyzguess sil(L)       0.0655694
xyzguess ol(L)        0.0316206
xyzguess x(L)          0.768652
xyzguess yan(L)       0.0528953
% -------------------
xyzguess x(hb)         0.413657
xyzguess y(hb)         0.605749
xyzguess z(hb)         0.403086
xyzguess a(hb)         0.378213
xyzguess k(hb)        0.0242954
xyzguess c(hb)         0.587566
xyzguess f(hb)        0.0973952
xyzguess t(hb)        0.0102669
xyzguess Q1(hb)      -0.0247639  range -1.000 1.000
xyzguess Q2(hb)        0.146095  range -1.000 1.000
% -------------------
xyzguess x(act)        0.326601
xyzguess y(act)        0.179241
xyzguess z(act)        0.235348
xyzguess a(act)       0.0871526
xyzguess k(act)       0.0294549
xyzguess c(act)        0.755176
xyzguess f(act)       0.0417267
xyzguess t(act)      0.00311795
xyzguess Q1(act)     -0.0378596  range -1.000 1.000
xyzguess Q2(act)      0.0801985  range -1.000 1.000
% -------------------
xyzguess x(gl)         0.429246
xyzguess y(gl)         0.754475
xyzguess z(gl)         0.884454
xyzguess a(gl)        0.0919829
xyzguess k(gl)        0.0275627
xyzguess c(gl)         0.113398
xyzguess f(gl)         0.100787
xyzguess t(gl)       0.00965433
xyzguess Q1(gl)     -0.00997847  range -1.000 1.000
xyzguess Q2(gl)        0.118435  range -1.000 1.000
% -------------------
xyzguess x(aug)         0.471978
xyzguess y(aug)        0.0971420
xyzguess f(aug)         0.102416
xyzguess z(aug)         0.832303
xyzguess j(aug)        0.0361891
xyzguess Qfm(aug)       0.523857  range  0.000 2.000
xyzguess Qal(aug)      0.0920156
% -------------------
xyzguess x(dio)        0.331989
xyzguess j(dio)        0.222852
xyzguess f(dio)        0.327043
xyzguess Q(dio)       0.0512517  range -0.500 0.500
xyzguess Qaf(dio)     0.0122242  range -0.500 0.500 % less than f j
xyzguess Qfm(dio)     -0.118441  range -0.500 0.500
% -------------------
xyzguess x(o)         0.300730
xyzguess j(o)         0.461012
xyzguess f(o)         0.377487
xyzguess Q(o)         0.336513  range -0.500 0.500
xyzguess Qaf(o)       0.113305  range -0.500 0.500 % less than f j
xyzguess Qfm(o)     -0.0578233  range -0.500 0.500
% -------------------
xyzguess x(jd)        0.45
xyzguess j(jd)        0.86
xyzguess f(jd)        0.01
xyzguess Q(jd)        0.04   range -0.500 0.500
xyzguess Qaf(jd)      0.001  range -0.500 0.500 % less than f j
xyzguess Qfm(jd)      0.1    range -0.500 0.500
% -------------------
xyzguess x(opx)        0.539535
xyzguess y(opx)        0.0502431
xyzguess f(opx)        0.0226851
xyzguess c(opx)        0.0486599
xyzguess Q(opx)        0.387159
% -------------------
xyzguess x(g)          0.790028
xyzguess z(g)          0.354536
xyzguess f(g)          0.0339621
% -------------------
xyzguess x(ol)	       0.15
% -------------------
xyzguess na(k4tr)       0.1
xyzguess ca(k4tr)       0.004
% -------------------
xyzguess ca(pl4tr)        0.557700
xyzguess k(pl4tr)         0.00702782
% -------------------
xyzguess ca(abc)       0.001
% -------------------
xyzguess x(sp)		0.4
xyzguess y(sp)		0.95
xyzguess z(sp)		0.01
% -------------------
xyzguess x(mt)		0.85
xyzguess y(mt)		0.09
xyzguess z(mt)		0.14
% -------------------
xyzguess x(ilm)         0.846768
xyzguess Q(ilm)         0.72  range -0.990 0.990
% -------------------
xyzguess x(hem)         0.1
xyzguess Q(hem)         0.01  range -0.990 0.990
% -------------------
xyzguess i(ilmm)        0.843297
xyzguess g(ilmm)        0.0194365
xyzguess Q(ilmm)        0.771192  range -0.990 0.990
% -------------------
xyzguess i(hemm)        0.489714
xyzguess g(hemm)        0.0151609
xyzguess Q(hemm)        0.000215607  range -0.050 0.050
% -------------------
xyzguess f(ep)          0.189427
xyzguess Q(ep)          0.182107  range  0.000 0.500
% -------------------
xyzguess x(bi)          0.371956
xyzguess y(bi)          0.0260159
xyzguess f(bi)          0.0131769
xyzguess t(bi)          0.0519677
xyzguess Q(bi)          0.173733   range  -1.0 1.0
% -------------------
xyzguess x(mu)          0.275719
xyzguess y(mu)          0.334730
xyzguess f(mu)          0.0164856
xyzguess n(mu)          0.00226622
xyzguess c(mu)          3.36760e-5
% -------------------
xyzguess x(chl)        0.275349
xyzguess y(chl)        0.451480
xyzguess f(chl)        0.123838
xyzguess QAl(chl)      0.424591  range -1.000 1.000
xyzguess Q1(chl)       0.0859470  range -1.000 1.000
xyzguess Q4(chl)       0.0245983  range -1.000 1.000
% -------------------
'''
}

igneous_guesses = {
    'ig50NCKFMASHTOCr': '''
% silicate melt, hydrous (NCKFMASHTOCr)
xyzguess wo(L)         0.107216
xyzguess sl(L)        0.0873506
xyzguess fo(L)        0.0142023
xyzguess fa(L)        0.0109878
xyzguess jd(L)         0.151907
xyzguess hm(L)       0.00154624
xyzguess ek(L)       9.81910e-6
xyzguess ti(L)       0.00413534
xyzguess kj(L)        0.0368694
xyzguess yct(L)       0.0885231
xyzguess h2o(L)        0.219727

% aqueous fluid with dissolved silicates
xyzguess wo(fl)     0.000103865
xyzguess sl(fl)      5.87807e-5
xyzguess fo(fl)      1.41812e-8
xyzguess fa(fl)      3.11791e-8
xyzguess jd(fl)     0.000862050
xyzguess hm(fl)     0.000159068
xyzguess ek(fl)      3.29610e-7
xyzguess ti(fl)     0.000162396
xyzguess kj(fl)      0.00562408
xyzguess h2o(fl)       0.985936

% plagioclase
xyzguess ca(pl4tr)        0.8
xyzguess k(pl4tr)        0.0116338

% olivine
xyzguess x(ol)         0.102434
xyzguess c(ol)       0.00275804
xyzguess Q(ol)      0.000156353

% orthopyroxene
xyzguess x(opx)       0.0956777
xyzguess y(opx)        0.182193  range  0.000 2.000
xyzguess c(opx)       0.0489271
xyzguess Q(opx)      -0.0475598  range -1.000 1.000
xyzguess f(opx)       0.0177886
xyzguess t(opx)      0.00823030
xyzguess cr(opx)      0.0205952
xyzguess j(opx)      0.00906326

% clinopyroxene
xyzguess x(cpx)       0.0964208
xyzguess y(cpx)       0.0825558  range  0.000 2.000
xyzguess o(cpx)        0.219892
xyzguess n(cpx)        0.118338
xyzguess Q(cpx)      -0.0282419  range -1.000 1.000
xyzguess f(cpx)       0.0209603
xyzguess cr(cpx)      0.0154784
xyzguess t(cpx)       0.0127859
xyzguess k(cpx)      0.00527429

% pigeonite
xyzguess x(pig)        0.124
xyzguess y(pig)        0.112  range  0.000 2.000
xyzguess o(pig)        0.888
xyzguess n(pig)        0.028
xyzguess Q(pig)       -0.0115  range -1.000 1.000
xyzguess f(pig)        0.004
xyzguess cr(pig)       0.001
xyzguess t(pig)        0.148
xyzguess k(pig)        0.001

% spinel
xyzguess x(spn)        0.144990
xyzguess y(spn)       0.0139965
xyzguess c(spn)       0.0451070
xyzguess t(spn)       0.0110937
xyzguess Q1(spn)       0.503697
xyzguess Q2(spn)      0.0807768
xyzguess Q3(spn)      0.0218537

% K-feldspar
xyzguess na(k4tr)       0.1
xyzguess ca(k4tr)       0.004

% muscovite
xyzguess x(mu)          0.275719
xyzguess y(mu)          0.334730
xyzguess f(mu)          0.0164856
xyzguess n(mu)          0.00226622
xyzguess c(mu)          3.36760e-5

% biotite
xyzguess x(bi)         0.457528
xyzguess y(bi)        0.0772161
xyzguess f(bi)        0.0158764
xyzguess t(bi)         0.119336
xyzguess Q(bi)         0.228603

% garnet
xyzguess x(g)          0.455851
xyzguess c(g)          0.286243
xyzguess f(g)        0.00253871
xyzguess cr(g)      0.000841005
xyzguess t(g)         0.0113394

% epidote
xyzguess f(ep)          0.189427
xyzguess Q(ep)          0.182107  range  0.000 0.500

% cordierite
xyzguess x(cd)            0.3
xyzguess h(cd)            0.7

% Al-spinel
xyzguess x(spn)            0.14499
xyzguess y(spn)            0.01398
xyzguess c(spn)            0.04504
xyzguess t(spn)            0.01114
xyzguess Q1(spn)           0.50372 range -1 1
xyzguess Q2(spn)           0.08077 range -1 1
xyzguess Q3(spn)           0.02183 range -1 1

% Cr-spinel
xyzguess x(cm)            0.2
xyzguess y(cm)            0.1
xyzguess c(cm)            0.8
xyzguess t(cm)            0.05
xyzguess Q1(cm)           0.05 range -1 1
xyzguess Q2(cm)           0.05 range -1 1
xyzguess Q3(cm)           0.05 range -1 1

% magnetite
xyzguess x(mt)            0.8
xyzguess y(mt)            0.55
xyzguess c(mt)            0.2
xyzguess t(mt)            0.01
xyzguess Q1(mt)           0.33 range -1 1
xyzguess Q2(mt)           0.14 range -1 1
xyzguess Q3(mt)           0.25 range -1 1

% hornblende
xyzguess x(hb)         0.355436
xyzguess y(hb)         0.393748
xyzguess z(hb)        0.0255955
xyzguess a(hb)         0.476446
xyzguess k(hb)        0.0647451
xyzguess c(hb)         0.924162
xyzguess f(hb)         0.103286
xyzguess t(hb)        0.0360617
xyzguess Q1(hb)      -0.0186478  range -1.000 1.000
xyzguess Q2(hb)        0.111970  range -1.000 1.000

% ilmenite
xyzguess x(ilm)        0.913364
xyzguess Q(ilm)        0.627896  range -0.990 0.990

% --------------------------------------------------------
''',
    'ig50NCKFMASTOCr': '''
% silicate melt, dry (NCKFMASTOCr)
xyzguess wo(L)         0.228033
xyzguess sl(L)         0.123908
xyzguess fo(L)         0.383275
xyzguess fa(L)        0.0784050
xyzguess jd(L)        0.0408634
xyzguess hm(L)        0.0156940
xyzguess ek(L)        0.0178215
xyzguess ti(L)       0.00817432
xyzguess kj(L)       0.00163650
xyzguess yct(L)     0.000695507

% aqueous fluid with dissolved silicates
xyzguess wo(fl)     0.000103865
xyzguess sl(fl)      5.87807e-5
xyzguess fo(fl)      1.41812e-8
xyzguess fa(fl)      3.11791e-8
xyzguess jd(fl)     0.000862050
xyzguess hm(fl)     0.000159068
xyzguess ek(fl)      3.29610e-7
xyzguess ti(fl)     0.000162396
xyzguess kj(fl)      0.00562408
xyzguess h2o(fl)       0.985936

% plagioclase
xyzguess ca(pl4tr)        0.8
xyzguess k(pl4tr)        0.0116338

% olivine
xyzguess x(ol)         0.102434
xyzguess c(ol)       0.00275804
xyzguess Q(ol)      0.000156353

% orthopyroxene
xyzguess x(opx)       0.0956777
xyzguess y(opx)        0.182193  range  0.000 2.000
xyzguess c(opx)       0.0489271
xyzguess Q(opx)      -0.0475598  range -1.000 1.000
xyzguess f(opx)       0.0177886
xyzguess t(opx)      0.00823030
xyzguess cr(opx)      0.0205952
xyzguess j(opx)      0.00906326

% clinopyroxene
xyzguess x(cpx)       0.0964208
xyzguess y(cpx)       0.0825558  range  0.000 2.000
xyzguess o(cpx)        0.219892
xyzguess n(cpx)        0.118338
xyzguess Q(cpx)      -0.0282419  range -1.000 1.000
xyzguess f(cpx)       0.0209603
xyzguess cr(cpx)      0.0154784
xyzguess t(cpx)       0.0127859
xyzguess k(cpx)      0.00527429

% pigeonite
xyzguess x(pig)        0.124
xyzguess y(pig)        0.112  range  0.000 2.000
xyzguess o(pig)        0.888
xyzguess n(pig)        0.028
xyzguess Q(pig)       -0.0115  range -1.000 1.000
xyzguess f(pig)        0.004
xyzguess cr(pig)       0.001
xyzguess t(pig)        0.148
xyzguess k(pig)        0.001

% spinel
xyzguess x(spn)        0.144990
xyzguess y(spn)       0.0139965
xyzguess c(spn)       0.0451070
xyzguess t(spn)       0.0110937
xyzguess Q1(spn)       0.503697
xyzguess Q2(spn)      0.0807768
xyzguess Q3(spn)      0.0218537

% K-feldspar
xyzguess na(k4tr)       0.1
xyzguess ca(k4tr)       0.004

% muscovite
xyzguess x(mu)          0.275719
xyzguess y(mu)          0.334730
xyzguess f(mu)          0.0164856
xyzguess n(mu)          0.00226622
xyzguess c(mu)          3.36760e-5

% biotite
xyzguess x(bi)         0.457528
xyzguess y(bi)        0.0772161
xyzguess f(bi)        0.0158764
xyzguess t(bi)         0.119336
xyzguess Q(bi)         0.228603

% garnet
xyzguess x(g)          0.455851
xyzguess c(g)          0.286243
xyzguess f(g)        0.00253871
xyzguess cr(g)      0.000841005
xyzguess t(g)         0.0113394

% epidote
xyzguess f(ep)          0.189427
xyzguess Q(ep)          0.182107  range  0.000 0.500

% cordierite
xyzguess x(cd)            0.3
xyzguess h(cd)            0.7

% Al-spinel
xyzguess x(spn)            0.14499
xyzguess y(spn)            0.01398
xyzguess c(spn)            0.04504
xyzguess t(spn)            0.01114
xyzguess Q1(spn)           0.50372 range -1 1
xyzguess Q2(spn)           0.08077 range -1 1
xyzguess Q3(spn)           0.02183 range -1 1

% Cr-spinel
xyzguess x(cm)            0.2
xyzguess y(cm)            0.1
xyzguess c(cm)            0.8
xyzguess t(cm)            0.05
xyzguess Q1(cm)           0.05 range -1 1
xyzguess Q2(cm)           0.05 range -1 1
xyzguess Q3(cm)           0.05 range -1 1

% magnetite
xyzguess x(mt)            0.8
xyzguess y(mt)            0.55
xyzguess c(mt)            0.2
xyzguess t(mt)            0.01
xyzguess Q1(mt)           0.33 range -1 1
xyzguess Q2(mt)           0.14 range -1 1
xyzguess Q3(mt)           0.25 range -1 1

% hornblende
xyzguess x(hb)         0.355436
xyzguess y(hb)         0.393748
xyzguess z(hb)        0.0255955
xyzguess a(hb)         0.476446
xyzguess k(hb)        0.0647451
xyzguess c(hb)         0.924162
xyzguess f(hb)         0.103286
xyzguess t(hb)        0.0360617
xyzguess Q1(hb)      -0.0186478  range -1.000 1.000
xyzguess Q2(hb)        0.111970  range -1.000 1.000

% ilmenite
xyzguess x(ilm)        0.913364
xyzguess Q(ilm)        0.627896  range -0.990 0.990

% --------------------------------------------------------
''',
}

tcprj_tmpl = """
% ==================================================================
% Scriptfile for $project
%
% Use "%" for commenting (nothing is read between % and the line ending).
% No lines are read after the "*" character.
% ==================================================================

axfile $system

autoexit

% ============
% which phases
% ============

inexcess  no
omit no
tozero no

% ================
% which conditions
% ================

diagramPT 2 10 350 800

% ================
% psbuilder blocks
% ================

%{PSBCALC-BEGIN}
calcP 11 15 0.08
calcT 370 425
calctatp yes
with bi ab pa sph mu g ep
zeromodeisopleth ab
%{PSBCALC-END}

% =====================
% pseudosection-related
% =====================

pseudosection

%{PSBBULK-BEGIN}
bulk  H2O    SiO2  Al2O3 CaO  MgO  FeOt K2O  Na2O TiO2 MnO  O
bulk  100.00 71.13 11.61 1.39 4.65 5.78 2.68 1.99 0.67 0.10 0.01
%{PSBBULK-END}

% ============
% set up x-eos
% ============
$samecoding

% ==========================
% ptbuilder starting guesses
% ==========================

%{PSBGUESS-BEGIN}
%{PSBGUESS-END}
$guesses

*
"""
