"""THERMOCALC API classes.

This module contain function to initialize working directory. It will
download the latest 3.5 version of THERMOCALC and appropriate dataset
and ax file according to user selection

"""

# author: Ondrej Lexa
# website: https://github.com/ondrolexa/pypsbuilder

import platform
import shutil
import string
import unicodedata
from io import BytesIO
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

# recent files
set_urls = {
    "metapelite": "https://hpxeosandthermocalc.org/wp-content/uploads/2025/05/tc-thermoinput-metapelite-2022-01-23.zip",
    "metabasite": "https://hpxeosandthermocalc.org/wp-content/uploads/2025/05/tc-thermoinput-metabasite-2022-01-30.zip",
    "igw24": "https://hpxeosandthermocalc.org/wp-content/uploads/2025/06/tc-thermoinput-igw24-2025-06-28.zip",
    "igg25": "https://hpxeosandthermocalc.org/wp-content/uploads/2025/05/tc-thermoinput-igg25-h18corr-2024-12-21.zip",
}

exe_urls = {
    "linux": "https://hpxeosandthermocalc.org/wp-content/uploads/2025/05/tc351-linux-bundle.zip",
    "win": "https://hpxeosandthermocalc.org/wp-content/uploads/2025/05/tc351-win-bundle.zip",
    "mac": "https://hpxeosandthermocalc.org/wp-content/uploads/2025/05/tc351-mac-bundle.zip",
}


def tcprojinit():
    cwd = Path.cwd()
    dir_needed = True
    while dir_needed:
        dest_tmp = input(f"Enter project directory [{cwd}]: ")
        if dest_tmp == "":
            dest = cwd
        else:
            dest = Path(dest_tmp)
        if dest.is_dir():
            if not any(dest.iterdir()):
                dir_needed = False
            else:
                print(f"ERROR: {dest} is not empty...")
        elif not dest.exists() and dest.parent.is_dir():
            dest.mkdir()
            dir_needed = False
        else:
            print(f"ERROR: {dest} is not valid directory...")

    projname_needed = True
    whitelist = f"_{string.ascii_letters}{string.digits}"
    while projname_needed:
        projname = input("Enter name of the project (max 8 chars) [project]: ")
        if projname == "":
            projname = "project"
        # replace spaces
        projname = projname.replace(" ", "_")
        # keep only valid ascii chars
        projname = (
            unicodedata.normalize("NFKD", projname).encode("ASCII", "ignore").decode()
        )
        # keep only whitelisted chars
        projname = "".join(c for c in projname if c in whitelist)
        if len(projname) < 1:
            print("ERROR: project name may not be empty")
        elif len(projname) > 8:
            print("ERROR: project name may not be longer than 8 characters")
        else:
            projname_needed = False

    range_needed = True
    while range_needed:
        range_raw = input("Enter [pmin, pmax, tmin, tmax] [1.9, 10.1, 345, 805]: ")
        if range_raw == "":
            pmin, pmax, tmin, tmax = 1.9, 10.1, 345, 805
        else:
            try:
                pmin, pmax, tmin, tmax = (
                    float(v) for v in range_raw.strip("[]").split(",")
                )
            except ValueError:
                print("ERROR: enter four comma-separated numbers")
                continue
        if pmax <= pmin:
            print("ERROR: pmax must be greater than pmin")
        elif tmax <= tmin:
            print("ERROR: tmax must be greater than tmin")
        else:
            range_needed = False

    pstep = (pmax - pmin) / 2

    set_needed = True
    sets = {1: "metapelite", 2: "metabasite", 3: "igg25", 4: "igw24"}
    while set_needed:
        print("Choose THERMOCALC input set")
        for k in sets:
            print(f" {k}. {sets[k]} set")
        try:
            n = input("Which set? [1]: ")
            if n == "":
                n = "1"
            if int(n) in [1, 2, 3, 4]:
                set_needed = False
        except ValueError:
            print("ERROR: enter 1, 2, 3 or 4")
    tcset = sets[int(n)]

    if tcset == "metapelite":
        ds = "62"
        system = "mp51MnNCKFMASHTO"
        samecoding = metapelite_samecoding
        guesses = metapelite_guesses
    elif tcset == "metabasite":
        ds = "62"
        system = "mb51NCKFMASHTO"
        samecoding = metabasite_samecoding
        guesses = metabasite_guesses
    elif tcset == "igw24":
        ds = "636"
        system = "ig51W24"
        samecoding = igw24_samecoding
        guesses = igw24_guesses
    elif tcset == "igg25":
        ds = "636"
        system = "ig51G25"
        samecoding = igg25_samecoding
        guesses = igg25_guesses

    # create prefs file
    with open(dest / "tc-prefs.txt", "w") as f:
        content = string.Template(tcpref_tmpl).substitute(dataset=ds, project=projname)[
            1:
        ]
        f.write(content)

    # download executable
    comp = platform.system()
    if comp == "Linux":
        with urlopen(exe_urls["linux"]) as zip:
            with ZipFile(BytesIO(zip.read())) as zfile:
                with (
                    zfile.open("tc351-linux-bundle/tc351lin") as source,
                    open(dest / "tc351lin", "wb") as target,
                ):
                    shutil.copyfileobj(source, target)
                Path(dest / "tc351lin").chmod(0o755)
    elif comp == "Windows":
        with urlopen(exe_urls["win"]) as zip:
            with ZipFile(BytesIO(zip.read())) as zfile:
                with (
                    zfile.open("tc351-win-bundle/tc351.exe") as source,
                    open(dest / "tc351.exe", "wb") as target,
                ):
                    shutil.copyfileobj(source, target)
                Path(dest / "tc351.exe").chmod(0o755)
    else:
        with urlopen(exe_urls["mac"]) as zip:
            with ZipFile(BytesIO(zip.read())) as zfile:
                with (
                    zfile.open("tc351-mac-bundle/tc351") as source,
                    open(dest / "tc351", "wb") as target,
                ):
                    shutil.copyfileobj(source, target)
                Path(dest / "tc351").chmod(0o755)

    # download set
    tcset_url = set_urls[tcset]
    with urlopen(tcset_url) as zip:
        with ZipFile(BytesIO(zip.read())) as zfile:
            # the zip's actual top-level folder name doesn't always match
            # the URL slug (e.g. "igw24" in the URL vs "igW24" inside the
            # zip), so read it from the archive instead of guessing it
            prefix = sorted(
                {
                    name.split("/")[0]
                    for name in zfile.namelist()
                    if not name.startswith("__MACOSX")
                }
            )[0]
            scsg_candidates = sorted(
                name
                for name in zfile.namelist()
                if name.startswith(f"{prefix}/samecoding_and_starting_guesses")
                and name.endswith(".txt")
            )
            if not scsg_candidates:
                samecoding = ""
            else:
                with zfile.open(scsg_candidates[0]) as f:
                    scsg = f.readlines()
                scsg = [s.decode("mac-roman") for s in scsg]
                samecoding = "".join([ln for ln in scsg if ln.startswith("samecoding")])
            with (
                zfile.open(f"{prefix}/tc-ds{ds}.txt") as source,
                open(dest / f"tc-ds{ds}.txt", "wb") as target,
            ):
                shutil.copyfileobj(source, target)
            with (
                zfile.open(f"{prefix}/tc-{system}.txt") as source,
                open(dest / f"tc-{system}.txt", "wb") as target,
            ):
                shutil.copyfileobj(source, target)

    # create project file
    with open(dest / f"tc-{projname}.txt", "w") as f:
        content = string.Template(tcprj_tmpl).substitute(
            system=system,
            project=projname,
            samecoding=samecoding,
            guesses=guesses,
            pmin=pmin,
            pmax=pmax,
            tmin=tmin,
            tmax=tmax,
            step=pstep,
        )[1:]
        f.write(content)


tcpref_tmpl = """
setpagewidth 700
dataset $dataset
scriptfile $project
calcmode 1
*
"""

metapelite_samecoding = """
samecoding mu pa       % make paragonite from muscovite
samecoding sp mt       % make high-T magnetite from spinel
samecoding ilm hem     % make FTO hematite from FTO ilmenite
samecoding ilmm hemm   % make FMMnTO hematite from FMMnTO ilmenite
"""

metapelite_guesses = """
% -------------------
xyzguess x(g)          0.824169
xyzguess z(g)         0.0317199
xyzguess m(g)          0.118530
xyzguess f(g)         0.0260643

xyzguess q(liq)        0.173460
xyzguess fsp(liq)      0.311414
xyzguess na(liq)       0.443405
xyzguess an(liq)     0.00913561
xyzguess ol(liq)     0.00192499
xyzguess x(liq)        0.746571
xyzguess h2o(liq)      0.485792

xyzguess ca(pl4tr)     0.377110
xyzguess k(pl4tr)     0.0370401

xyzguess na(k4tr)      0.227897
xyzguess ca(k4tr)     0.0114380

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

% --------------------------------------------------------
"""

metabasite_samecoding = """
samecoding hb act gl
samecoding dio o jd
samecoding sp mt
samecoding ilm hem
samecoding ilmm hemm
"""


metabasite_guesses = """
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
"""

igg25_samecoding = """
samecoding liq_G25w  liq      		% silicate melt (wet)
samecoding fl_G25    fl	                % aqueous fluid
samecoding ol_H18    ol	 		% olivine
samecoding g_W24     g			% garnet
samecoding spl_T21   spl mgt cm usp	% spinel, magnetite, Cr-spinel, ulvospinel
samecoding fsp_H22   pl afs  		% plagioclase, alkali feldspar
samecoding cpx_W24   cpx pig		% augitic clinopyroxene, pigeonite
samecoding opx_W24   opx		% orthopyroxene
samecoding ilm_W24   ilm hem            % ilmenite, hematite
samecoding bi_G25    bi                 % biotite
samecoding mu_W14    mu                 % muscovite
samecoding amp_G16   hb gl act          % hornblende, glaucophane, actinolite
samecoding ep_H11    ep                 % epidote
samecoding cd_G25    cd                 % cordierite
"""

igg25_guesses = """
% --------------------------------------------------------
xyzguess wo(liq)      0.18
xyzguess sl(liq)      0.14
xyzguess fo(liq)      0.02
xyzguess fa(liq)      0.03
xyzguess ns(liq)      0.25
xyzguess hm(liq)      0.04
xyzguess ek(liq)      0.0005
xyzguess ti(liq)      0.03
xyzguess ks(liq)      0.18
xyzguess yan(liq)     0.004
xyzguess yab(liq)     0.09
xyzguess yen(liq)     0.02
xyzguess ykf(liq)     0.06
% -----------------------------
xyzguess x(ol)        0.3
xyzguess c(ol)        0.01
xyzguess Q(ol)        0.001     range -0.5 0.5
% -----------------------------
xyzguess x(g)         0.4
xyzguess c(g)         0.2
xyzguess f(g)         0.01
xyzguess cr(g)        0.002
xyzguess t(g)         0.02
% -----------------------------
xyzguess x(spl)       0.65
xyzguess y(spl)       0.08
xyzguess c(spl)       0.01
xyzguess t(spl)       0.01
xyzguess Q1(spl)      0.2       range -1 1
xyzguess Q2(spl)      0.2       range -1 1
xyzguess Q3(spl)      0.15      range -1 1
% -----------------------------
xyzguess x(cm)        0.5
xyzguess y(cm)        0.08
xyzguess c(cm)        0.85
xyzguess t(cm)        0.01
xyzguess Q1(cm)       0.2       range -1 1
xyzguess Q2(cm)       0.4       range -1 1
xyzguess Q3(cm)       0.02      range -1 1
% -----------------------------
xyzguess x(mgt)       0.85
xyzguess y(mgt)       0.85
xyzguess c(mgt)       0.01
xyzguess t(mgt)       0.01
xyzguess Q1(mgt)      0.05      range -1 1
xyzguess Q2(mgt)      0.05      range -1 1
xyzguess Q3(mgt)      0.02      range -1 1
% -----------------------------
xyzguess x(usp)       0.3
xyzguess y(usp)       0.1
xyzguess c(usp)       0.01
xyzguess t(usp)       0.85
xyzguess Q1(usp)      0.15      range -1 1
xyzguess Q2(usp)      0.05      range -1 1
xyzguess Q3(usp)      0.02      range -1 1
% -----------------------------
xyzguess ca(pl)       0.67
xyzguess k(pl)        0.01
% -----------------------------
xyzguess ca(afs)      0.03
xyzguess k(afs)       0.85
% -----------------------------
xyzguess x(cpx)       0.2
xyzguess y(cpx)       0.08      range  0  2
xyzguess o(cpx)       0.1
xyzguess n(cpx)       0.05
xyzguess f(cpx)       0.03
xyzguess t(cpx)       0.02
xyzguess cr(cpx)      0.003
xyzguess k(cpx)       0.001
xyzguess Q(cpx)      -0.01      range -1 1
% -----------------------------
xyzguess x(pig)       0.2
xyzguess y(pig)       0.08      range  0  2
xyzguess o(pig)       0.8
xyzguess n(pig)       0.05
xyzguess f(pig)       0.03
xyzguess t(pig)       0.02
xyzguess cr(pig)      0.003
xyzguess k(pig)       0.001
xyzguess Q(pig)      -0.01      range -1 1
% -----------------------------
xyzguess x(opx)       0.3
xyzguess y(opx)       0.1	range  0  2
xyzguess c(opx)       0.05
xyzguess j(opx)       0.02
xyzguess f(opx)       0.03
xyzguess t(opx)       0.02
xyzguess cr(opx)      0.003
xyzguess Q(opx)      -0.2       range -1 1
% -----------------------------
xyzguess i(ilm)       0.98
xyzguess m(ilm)       0.0007
xyzguess Q(ilm)       0.88      range -1 1
xyzguess Qt(ilm)      0.88      range -1 1
% -----------------------------
xyzguess i(hem)        0.1
xyzguess m(hem)        0.001
xyzguess Q(hem)        0.08     range -1 1
xyzguess Qt(hem)       0.08     range -1 1
% -----------------------------
xyzguess x(bi)         0.35
xyzguess y(bi)         0.25
xyzguess f(bi)         0.04
xyzguess t(bi)         0.17
xyzguess Q(bi)         0.25   range -1  1
% -----------------------------
xyzguess x(mu)         0.25
xyzguess y(mu)         0.60
xyzguess f(mu)         0.17
xyzguess n(mu)         0.06
xyzguess c(mu)         0.004
% -----------------------------
xyzguess x(hb)         0.40
xyzguess y(hb)         0.65
xyzguess z(hb)         0.35
xyzguess a(hb)         0.35
xyzguess k(hb)         0.01
xyzguess c(hb)         0.60
xyzguess f(hb)         0.05
xyzguess t(hb)         0.01
xyzguess Q1(hb)       -0.06  range  -1  1
xyzguess Q2(hb)        0.30  range  -1  1
% -----------------------------
xyzguess x(gl)         0.45
xyzguess y(gl)         0.80
xyzguess z(gl)         0.88
xyzguess a(gl)         0.05
xyzguess k(gl)         0.01
xyzguess c(gl)         0.10
xyzguess f(gl)         0.04
xyzguess t(gl)         0.04
xyzguess Q1(gl)        0.40  range  -1  1
xyzguess Q2(gl)       -0.03  range  -1  1
% -----------------------------
xyzguess x(act)        0.35
xyzguess y(act)        0.20
xyzguess z(act)        0.20
xyzguess a(act)        0.05
xyzguess k(act)        0.01
xyzguess c(act)        0.78
xyzguess f(act)        0.02
xyzguess t(act)        0.002
xyzguess Q1(act)       0.3   range -1  1
xyzguess Q2(act)      -0.15  range -1  1
% -----------------------------
xyzguess f(ep)          0.1
xyzguess Q(ep)          0.2      range  -1/2  1/2
% -----------------------------
xyzguess x(cd)          0.3
xyzguess h(cd)          0.7
% --------------------------------------------------------
"""

igw24_samecoding = """
samecoding liq_W24d  liq      		% silicate melt (dry)
samecoding ol_H18    ol	 		% olivine
samecoding g_W24     g			% garnet
samecoding spl_T21   spl mgt cm usp	% spinel, magnetite, Cr-spinel, ulvospinel
samecoding fsp_H22   pl afs  		% plagioclase, alkali feldspar
samecoding cpx_W24   cpx pig		% augitic clinopyroxene, pigeonite
samecoding opx_W24   opx		% orthopyroxene
samecoding ilm_W24   ilm hem            % ilmenite, hematite
samecoding nph_W24   nph nphk 		% Na-rich nepheline, K-rich nepheline
samecoding kals_W24  kals		% kalsilite
samecoding lct_W24   lct		% leucite
samecoding mel_W24   mel		% melilite
"""

igw24_guesses = """
% --------------------------------------------------------
xyzguess wo(liq)      0.18
xyzguess sl(liq)      0.14
xyzguess fo(liq)      0.02
xyzguess fa(liq)      0.03
xyzguess ns(liq)      0.25
xyzguess hm(liq)      0.04
xyzguess ek(liq)      0.0005
xyzguess ti(liq)      0.03
xyzguess ks(liq)      0.18
xyzguess yan(liq)     0.004
xyzguess yab(liq)     0.09
xyzguess yen(liq)     0.02
xyzguess ykf(liq)     0.06
% -----------------------------
xyzguess x(ol)        0.3
xyzguess c(ol)        0.01
xyzguess Q(ol)        0.001     range -0.5 0.5
% -----------------------------
xyzguess x(g)         0.4
xyzguess c(g)         0.2
xyzguess f(g)         0.01
xyzguess cr(g)        0.002
xyzguess t(g)         0.02
% -----------------------------
xyzguess x(spl)       0.65
xyzguess y(spl)       0.08
xyzguess c(spl)       0.01
xyzguess t(spl)       0.01
xyzguess Q1(spl)      0.2       range -1 1
xyzguess Q2(spl)      0.2       range -1 1
xyzguess Q3(spl)      0.15      range -1 1
% -----------------------------
xyzguess x(cm)        0.5
xyzguess y(cm)        0.08
xyzguess c(cm)        0.85
xyzguess t(cm)        0.01
xyzguess Q1(cm)       0.2       range -1 1
xyzguess Q2(cm)       0.4       range -1 1
xyzguess Q3(cm)       0.02      range -1 1
% -----------------------------
xyzguess x(mgt)       0.85
xyzguess y(mgt)       0.85
xyzguess c(mgt)       0.01
xyzguess t(mgt)       0.01
xyzguess Q1(mgt)      0.05      range -1 1
xyzguess Q2(mgt)      0.05      range -1 1
xyzguess Q3(mgt)      0.02      range -1 1
% -----------------------------
xyzguess x(usp)       0.3
xyzguess y(usp)       0.1
xyzguess c(usp)       0.01
xyzguess t(usp)       0.85
xyzguess Q1(usp)      0.15      range -1 1
xyzguess Q2(usp)      0.05      range -1 1
xyzguess Q3(usp)      0.02      range -1 1
% -----------------------------
xyzguess ca(pl)       0.67
xyzguess k(pl)        0.01
% -----------------------------
xyzguess ca(afs)      0.03
xyzguess k(afs)       0.85
% -----------------------------
xyzguess x(cpx)       0.2
xyzguess y(cpx)       0.08      range  0  2
xyzguess o(cpx)       0.1
xyzguess n(cpx)       0.05
xyzguess f(cpx)       0.03
xyzguess t(cpx)       0.02
xyzguess cr(cpx)      0.003
xyzguess k(cpx)       0.001
xyzguess Q(cpx)      -0.01      range -1 1
% -----------------------------
xyzguess x(pig)       0.2
xyzguess y(pig)       0.08      range  0  2
xyzguess o(pig)       0.8
xyzguess n(pig)       0.05
xyzguess f(pig)       0.03
xyzguess t(pig)       0.02
xyzguess cr(pig)      0.003
xyzguess k(pig)       0.001
xyzguess Q(pig)      -0.01      range -1 1
% -----------------------------
xyzguess x(opx)       0.3
xyzguess y(opx)       0.1	range  0  2
xyzguess c(opx)       0.05
xyzguess j(opx)       0.02
xyzguess f(opx)       0.03
xyzguess t(opx)       0.02
xyzguess cr(opx)      0.003
xyzguess Q(opx)      -0.2       range -1 1
% -----------------------------
xyzguess i(ilm)       0.98
xyzguess m(ilm)       0.0007
xyzguess Q(ilm)       0.88      range -1 1
xyzguess Qt(ilm)      0.88      range -1 1
% -----------------------------
xyzguess i(hem)        0.1
xyzguess m(hem)        0.001
xyzguess Q(hem)        0.08     range -1 1
xyzguess Qt(hem)       0.08     range -1 1
% -----------------------------
xyzguess k(nph)        0.1
xyzguess s(nph)        0.04
xyzguess f(nph)        0.0001
xyzguess c(nph)        0.001
xyzguess Q(nph)        0.2      range -1 1
% -----------------------------
xyzguess k(nphk)       0.9
xyzguess s(nphk)       0.04
xyzguess f(nphk)       0.0001
xyzguess c(nphk)       0.001
xyzguess Q(nphk)       0.05     range -1 1
% -----------------------------
xyzguess k(kals)       0.88
% ----------------------------
xyzguess n(lct)        0.05
% -----------------------------
xyzguess x(mel)        0.20
xyzguess n(mel)        0.18
xyzguess y(mel)        0.40
xyzguess f(mel)        0.06
% ----------------------------
"""

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
tozero no

% ================
% which conditions
% ================

diagramPT $pmin $pmax $tmin $tmax

% ================
% psbuilder blocks
% ================

%{PSBCALC-BEGIN}
calcP $pmin $pmax $step
calcT $tmin $tmax
calctatp yes
with *
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
