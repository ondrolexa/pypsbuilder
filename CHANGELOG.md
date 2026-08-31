# Changelog
All notable pypsbuilder changes.

## [2.6.8] - master
### Added
 - `Export JSON` menu item added to ptbuilder/txbuilder/pxbuilder File menu, exporting invariant points and univariant lines in a schema readable back in by `Import from JSON`
### Fixed
 - TC35API rejects `omit` scriptfile script as unrecognised (discontinued in THERMOCALC 3.51); use `with`/`inexcess` instead
 - TC35API bombed-run detection matches THERMOCALC 3.51's actual `-- run bombed` output
 - About, Modes and Full TC output dialogs no longer get hidden behind the main builder window; About dialog now also shows the builder's icon
 - `Import from JSON` no longer requires an empty project; existing invariant points/univariant lines are left untouched and only genuinely new entries are calculated. It seeds THERMOCALC ptguesses from the nearest already-calculated invariant point before each calculation
### Changed
 - CI test matrix now runs on Linux, Windows and macOS (in addition to the existing Python version matrix)

## [2.6.7] - 2026-08-29
### Added
 - `tcinit` now prompts for the P-T range (`[pmin, pmax, tmin, tmax]`), used to set the generated scriptfile's `diagramPT`/`calcP`/`calcT` lines
 - `tcinit` creates the destination directory automatically when it doesn't exist yet but its parent does

## [2.6.6] - 2026-08-29
### Fixed
 - project extra jupyter renamed to lab

 ## [2.6.5] - 2026-08-29
### Added
 - `Import from JSON` menu item in ptbuilder/txbuilder/pxbuilder to batch-import invariant points and univariant lines JSON
 - THERMOCALC 3.51 support in `tcinit`
### Fixed
 - security: project files now load through a restricted unpickler, closing an arbitrary-code-execution risk from opening a crafted `.ptb`/`.txb`/`.pxb` file
 - `eval_expr` now supports unary +/- (e.g. `-mode`)
 - fixed crash opening some real project files (`annotate()` got an array instead of a scalar)
 - `PS.show_grid` no longer silently drops its `expr`/`interpolation` arguments
 - fixed `PXPS.fix_solutions` not reseeding THERMOCALC guesses from a solved neighbor before retrying a failed grid point
 - THERMOCALC/drawpd subprocess calls no longer hang indefinitely on an unresponsive process
 - fixed deprecated matplotlib colormap API usage
### Changed
 - faster diagram field lookups and grid calculation via spatial indexing and vectorized nearest-point search

## [2.6.4] - 2025-08-03
### Fixed
 - TC 3.51 compatibility added
### Added
 - `sys` could be used as phase to access G H S V rho variables

## [2.6.3] - 2025-04-03
### Fixed
 - fixed multipolygon bug when subsections are merged

## [2.6.2] - 2025-02-11
### Fixed
 - f-string py3.10 bugfix

## [2.6.1] - 2025-01-24
### Added
 - Both PyQt5 and PyQt6 are supported and need to be specified as
   extra option during installation

## [2.6.0] - 2025-01-23
Initial PyQt6 release

## [2.5.3] - 2024-12-18
Latest version using PyQt5 only

## [2.5.0] - 2024-12-13
### Fixed
 - fix for coe-q

## [2.4.2] - 2024-04-23
### Fixed
 - another fix of and-ky-sill triple point linking

## [2.4.1] - 2024-03-07
### Fixed
 - fixed and-ky-sill triple point uniline suggestions
 - filled_over labeling fixed
 - cdf isoplths bug fixed
### Added
 - overlap_isopleths method added

## [2.4.0] - 2023-12-21
### Fixed
 - important collect_grid_data bug causing isopleths twisting fixed.
### Added
 - collect_ptpath missing field check added
 - remove_grid_data method added
 - isopleths bivariate spline method added

## [2.3.6] - 2023-12-13
### Added
 - search_composition method added to PTPS to find best estimate for isopleths intersection

## [2.3.5] - 2023-12-09
### Fixed
 - accept var check

## [2.3.4] - 2023-03-10
### Added
 - tristate labeling of uni and inv
### Fixed
 - TC34API bug fixed

## [2.3.3] - 2023-02-08
### Fixed
 - gendrawpd bug fixed
 - missing omit or inexcess fix

## [2.3.2] - 2023-01-31
### Added
 - tcinit script added to initialize project directory
 - bulk table bug fixed
 - pointcalc method to run TC for given pT added to explorer
 - fixed some issues with creating areas
 - experimental vector isoplets for easy editing added (needs scikit-image)

## [2.3.1] - 2022-10-06
### Fixed
 - Fixed support for both TC34x and TC350beta
 - added tool to parse TC calculations (executed out of builder)
 - fixed ShapelyDeprecationWarning
 - fixed collect_ptpath() along 2-point path

## [2.3.0] 2021-05-04
### Fixed
- latest THERMOCALC 3.50 compatibility

### Added
- isopleths quadratic surface fit method added
- isopleths figure and savefig options added

## [2.2.2] - 2021-01-25
### Fixed
- gendrawpd fixed
- fix to partially support TC347

## [2.2.1] - 2020-06-16
### Added
- bugfix release
- option to to move invpoint and keep results
(useful to fine-tune topology)
- tool to cleanup storage (trim metastable calculations)
- option to hide labels of connected lines and points

## [2.2.0] - 2020-04-11
### Added
- ptbuilder, txbuilder and pxbuilder pseudosection builders
- topology graph window added
- dogmin implemented (results stored in projects)
- autoconnect implemented
- invariant point search implemented
- merge of partially calculated univariant lines implemented
- possibility to remove parts of univariant lines implemented
- zoom to uni added to context menu
- option to extend calculation range to extend univariant lines gently out of defined region
- PTPS, TXPS and PXPS psexplorers implemented
- possibility to merge several parts of pseudosection. Invariant points and
univariant lines must be unique in single project.
- calc along PT path implemented (now only for PT sections)

## [2.1.5] - 2019-03-25
### Removed
- autocorrection of liquid model named as liq but starting guesses using L removed.
User must check if liq model is coded properly. In case of tc-6xmn.txt it should be:

```
  % =================================================
  liq 8  1

     q(liq)          0.1814
     fsp(liq)        0.3490
     na(liq)         0.5840
     an(liq)        0.01104
     ol(liq)        0.01373
     x(liq)          0.7333
     h2o(liq)        0.4276

  % --------------------------------------------------
```

## [2.1.4] - 2017-12-04
### Fixed
- clabel positioning
- minimum contour level
- silently ignore critical possible topology errors

## [2.1.2] - 2017-04-03
### Added
- Option to show bulk composition on psexplorer figures
- dio-o and gl-act-hb added to polymorphs

### Fixed
- psshow changed default color map to be darker for higher variance
- manual or imported invariant points bub in psiso fixed

## [2.1.1] - 2017-03-28
### Added
- colors and cmap args added to cli version of psiso
- clabel arg psiso to place contour labels

## [2.1.0] - 2017-03-23
### Added
- Write starting guesses from existing calculations
(note that commented tags are needed in scriptfile)
- Updated parsing include rbi data
- Initial version of psexplorer to draw final pseudosections and isopleths
(cli scrips provided)
- Manual unilines and invpoints shown in bold in lists

## [2.0.7] - 2017-02-13
### Added
- double-click on phaselist highlight all unilines with zero mode phase
- option to export partial areas
- Keyboard shortcuts added Ctrl-T and Ctrl-P for CalcTatP and CalcPatT,
Ctrl-H Zoom home

### Fixes
- excess phases stored in unilines and invpoints
- labeling phases sorted alphabeltically, same as phaselist
- auto bug fixed

## [2.0.6] - 2017-02-03
### Fixed
- path to executables stored in project
- scriptfile parsing improved

## [2.0.5] 2017-01-19
### Fixes
- output parsing fixed (hopefully...)
- Rightclick invariant points menu fixed
- area construction for drawpd export fixed
- networkx dependecy removed

## [2.0.4] - 2017-01-13
### Added
- saveas project added
- working directory written to Log window
- Log window catch output of both thermocalc and drawpd

## [2.0.3] - 2017-01-13
### Added
- invview right click to select not yet calculated uni lines implemented

### Fixes
- Zoom uni button persistent
- export list of phases in areas for TC-Investigator
- drawpd areas construction fixed

## [2.0.2] - 2016-12-10
### Fixed
- Areas export fixed
- inv filtering fixed

## [2.0.1] - 2016-12-10
### Added
- Recent files implemented
- Adding manual uni and inv must be constrained by phases and out selection
- Export areas to drawpd
- Auto calculation around inv point

### Fixed
- scriptfile encoding fix
- unilabels placement fixed
- refresh instead plot during zoom
- new unicutting algorithm
- THERMOCALC mac-roman encoding used

## [2.0.0] 2016-11-19
### Added
- Initial release of new generation of PSBuilder

[2.3.0dev]: https://github.com/ondrolexa/pypsbuilder/compare/v2.2.2...HEAD
[2.2.2]: https://github.com/ondrolexa/pypsbuilder/compare/v2.2.1...v2.2.2
[2.2.1]: https://github.com/ondrolexa/pypsbuilder/compare/v2.1.5...v2.2.1
