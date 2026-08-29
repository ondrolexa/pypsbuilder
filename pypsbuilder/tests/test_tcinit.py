"""Coverage-extension tests for tcinit.py.

tcprojinit() is interactive (input()) and downloads real zips from
hpxeosandthermocalc.org - the committed suite must not depend on either,
so this builds synthetic in-memory zipfile.ZipFile fixtures (matching the
real bundle/dataset internal layout discovered by testing tcprojinit()
against the *real* URLs in an earlier session, including the __MACOSX/
noise entries and the mismatched-capitalization folder names that
motivated reading the prefix from the archive instead of the URL slug)
and monkeypatches input()/platform.system()/urlopen.
"""

import io
from pathlib import Path
from unittest import mock
from zipfile import ZipFile

import pytest

import pypsbuilder.tcinit as tcinit


def _make_zip(files):
    buf = io.BytesIO()
    with ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _exe_zip(folder, exe_name):
    return _make_zip(
        {
            f"{folder}/": "",
            f"__MACOSX/._{folder}": "",
            f"{folder}/scripts-tc351.pdf": "pdf content",
            f"{folder}/{exe_name}": "#!/bin/sh\necho fake tc\n",
            f"__MACOSX/{folder}/._{exe_name}": "",
        }
    )


def _set_zip(folder, ds, system, samecoding_name="samecoding_and_starting_guesses.txt"):
    return _make_zip(
        {
            f"{folder}/": "",
            f"__MACOSX/._{folder}": "",
            f"{folder}/0_version_notes.txt": "notes",
            f"{folder}/README.txt": "readme",
            f"{folder}/{samecoding_name}": (
                "samecoding mu pa % comment\nsamecoding sp mt\nnot a samecoding line\n"
            ),
            f"__MACOSX/{folder}/._{samecoding_name}": "",
            f"{folder}/tc-ds{ds}.txt": "fake dataset file content\n",
            f"__MACOSX/{folder}/._tc-ds{ds}.txt": "",
            f"{folder}/tc-{system}.txt": "fake axfile content\n",
            f"__MACOSX/{folder}/._tc-{system}.txt": "",
        }
    )


@pytest.fixture
def synthetic_urls():
    """Build synthetic zip bytes for every URL tcinit.py references,
    matching the exact internal paths the code expects."""
    return {
        tcinit.exe_urls["linux"]: _exe_zip("tc351-linux-bundle", "tc351lin"),
        tcinit.exe_urls["win"]: _exe_zip("tc351-win-bundle", "tc351.exe"),
        tcinit.exe_urls["mac"]: _exe_zip("tc351-mac-bundle", "tc351"),
        tcinit.set_urls["metapelite"]: _set_zip(
            "tc-thermoinput-metapelite-2022-01-23", "62", "mp51MnNCKFMASHTO"
        ),
        tcinit.set_urls["metabasite"]: _set_zip(
            "tc-thermoinput-metabasite-2022-01-30", "62", "mb51NCKFMASHTO"
        ),
        # capitalization deliberately differs from the URL slug ("igw24"),
        # and the samecoding file uses the real suffixed-name convention -
        # both are exactly what motivated reading prefix from the archive
        # and prefix-matching the samecoding filename.
        tcinit.set_urls["igw24"]: _set_zip(
            "tc-thermoinput-igW24-2025-06-28",
            "636",
            "ig51W24",
            samecoding_name="samecoding_and_starting_guesses_W24.txt",
        ),
        tcinit.set_urls["igg25"]: _set_zip(
            "tc-thermoinput-igG25-H18corr-2024-12-21",
            "636",
            "ig51G25",
            samecoding_name="samecoding_and_starting_guesses_G25.txt",
        ),
    }


def _fake_urlopen(cache):
    def _urlopen(url, *args, **kwargs):
        return io.BytesIO(cache[url])

    return _urlopen


SETS = {"1": "metapelite", "2": "metabasite", "3": "igg25", "4": "igw24"}
EXPECTED = {
    "metapelite": ("62", "mp51MnNCKFMASHTO"),
    "metabasite": ("62", "mb51NCKFMASHTO"),
    "igg25": ("636", "ig51G25"),
    "igw24": ("636", "ig51W24"),
}


@pytest.mark.parametrize("comp", ["Linux", "Windows", "Darwin"])
@pytest.mark.parametrize("choice", ["1", "2", "3", "4"])
def test_tcprojinit_all_platform_dataset_combinations(
    tmp_path, synthetic_urls, comp, choice
):
    dest = tmp_path / f"proj_{comp}_{choice}"
    dest.mkdir()
    inputs = iter([str(dest), "testproj", choice])

    with (
        mock.patch("builtins.input", lambda *a: next(inputs)),
        mock.patch("pypsbuilder.tcinit.platform.system", return_value=comp),
        mock.patch("pypsbuilder.tcinit.urlopen", _fake_urlopen(synthetic_urls)),
    ):
        tcinit.tcprojinit()

    ds, system = EXPECTED[SETS[choice]]

    assert (dest / "tc-prefs.txt").exists()
    prefs = (dest / "tc-prefs.txt").read_text()
    assert "scriptfile testproj" in prefs
    assert f"dataset {ds}" in prefs

    exe_name = {"Linux": "tc351lin", "Windows": "tc351.exe", "Darwin": "tc351"}[comp]
    exe_path = dest / exe_name
    assert exe_path.exists()
    assert exe_path.stat().st_mode & 0o111  # executable bit set

    assert (dest / f"tc-ds{ds}.txt").read_text() == "fake dataset file content\n"
    assert (dest / f"tc-{system}.txt").read_text() == "fake axfile content\n"


def test_tcprojinit_samecoding_extracted_from_prefix_matched_file(
    tmp_path, synthetic_urls
):
    """igw24's samecoding file is named samecoding_and_starting_guesses_W24.txt
    (suffixed), not the exact name - this is the specific bug fixed earlier
    this session."""
    dest = tmp_path / "proj"
    dest.mkdir()
    inputs = iter([str(dest), "testproj", "4"])  # igw24

    with (
        mock.patch("builtins.input", lambda *a: next(inputs)),
        mock.patch("pypsbuilder.tcinit.platform.system", return_value="Linux"),
        mock.patch("pypsbuilder.tcinit.urlopen", _fake_urlopen(synthetic_urls)),
    ):
        tcinit.tcprojinit()

    projfile = dest / "tc-testproj.txt"
    content = projfile.read_text()
    assert "samecoding mu pa" in content
    assert "samecoding sp mt" in content
    assert "not a samecoding line" not in content


def test_tcprojinit_no_samecoding_file_falls_back_to_empty(tmp_path):
    """When no samecoding_and_starting_guesses*.txt entry matches, the
    current code falls back to an empty string rather than raising."""
    dest = tmp_path / "proj"
    dest.mkdir()
    inputs = iter([str(dest), "testproj", "1"])  # metapelite

    cache = {
        tcinit.exe_urls["linux"]: _exe_zip("tc351-linux-bundle", "tc351lin"),
        tcinit.set_urls["metapelite"]: _make_zip(
            {
                "tc-thermoinput-metapelite-2022-01-23/tc-ds62.txt": "ds content\n",
                "tc-thermoinput-metapelite-2022-01-23/tc-mp51MnNCKFMASHTO.txt": "ax content\n",
            }
        ),
    }

    with (
        mock.patch("builtins.input", lambda *a: next(inputs)),
        mock.patch("pypsbuilder.tcinit.platform.system", return_value="Linux"),
        mock.patch("pypsbuilder.tcinit.urlopen", _fake_urlopen(cache)),
    ):
        tcinit.tcprojinit()

    projfile = dest / "tc-testproj.txt"
    assert projfile.exists()


def test_tcprojinit_rejects_nonempty_directory(tmp_path, synthetic_urls, capsys):
    dest = tmp_path / "proj"
    dest.mkdir()
    (dest / "existing_file.txt").write_text("already here")

    good_dest = tmp_path / "empty_proj"
    good_dest.mkdir()

    inputs = iter([str(dest), str(good_dest), "testproj", "1"])

    with (
        mock.patch("builtins.input", lambda *a: next(inputs)),
        mock.patch("pypsbuilder.tcinit.platform.system", return_value="Linux"),
        mock.patch("pypsbuilder.tcinit.urlopen", _fake_urlopen(synthetic_urls)),
    ):
        tcinit.tcprojinit()

    assert "is not empty" in capsys.readouterr().out
    assert (good_dest / "tc-prefs.txt").exists()


def test_tcprojinit_default_project_name(tmp_path, synthetic_urls):
    dest = tmp_path / "proj"
    dest.mkdir()
    inputs = iter([str(dest), "", "1"])  # empty name -> default "project"

    with (
        mock.patch("builtins.input", lambda *a: next(inputs)),
        mock.patch("pypsbuilder.tcinit.platform.system", return_value="Linux"),
        mock.patch("pypsbuilder.tcinit.urlopen", _fake_urlopen(synthetic_urls)),
    ):
        tcinit.tcprojinit()

    assert (dest / "tc-project.txt").exists()
    assert "scriptfile project" in (dest / "tc-prefs.txt").read_text()


def test_tcprojinit_project_name_sanitization(tmp_path, synthetic_urls):
    dest = tmp_path / "proj"
    dest.mkdir()
    # spaces replaced, non-ascii stripped, then re-entered because
    # "a b" -> "a_b" is valid on first pass (no retry needed here);
    # test a name that's too long first to exercise the retry loop
    inputs = iter([str(dest), "toolongname123", "short nm", "1"])

    with (
        mock.patch("builtins.input", lambda *a: next(inputs)),
        mock.patch("pypsbuilder.tcinit.platform.system", return_value="Linux"),
        mock.patch("pypsbuilder.tcinit.urlopen", _fake_urlopen(synthetic_urls)),
    ):
        tcinit.tcprojinit()

    assert (dest / "tc-short_nm.txt").exists()
