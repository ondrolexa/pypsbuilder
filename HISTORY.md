# Changes

### 2.2.1 (XX YYY 2020)

 * gendrawpd fixed

### 2.2.1 (16 Jun 2020)

 * bugfix release
 * option to to move invpoint and keep results
   (useful to fine-tune topology)
 * tool to cleanup storage (trim metastable calculations)
 * option to hide labels of connected lines and points

## 2.2 (11 Apr 2020) - COVID-19 release

* pseudosection builders major update and refactoring
  - ptbuilder, txbuilder and pxbuilder implemented
  - compatible with TC 3.50
  - topology graph window added
  - dogmin implemented (results stored in projects)
  - autoconnect implemented
  - invariant point search implemented
  - merge of partially calculated univariant lines implemented
  - possibility to remove parts of univariant lines implemented
  - zoom to uni added to context menu
  - option to extend calculation range to extend univariant lines gently out of defined region
* psexplorers updated
  - PTPS, TXPS and PXPS implemented
  - possibility to merge several parts of pseudosection. Invariant points and
    univariant lines must be unique in single project.
  - calc along PT path implemented (now only for PT sections)

### 2.1.5 (25 Mar 2019)

* autocorrection of liquid model named as liq but starting guesses using L removed.
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

### 2.1.4 (04 Dec 2017)

* fix clabel positioning
* fix for minimum contour level
* silently ignore critical possible topology errors

### 2.1.2 (03 Apr 2017)

* Option to show bulk composition on psexplorer figures
* psshow changed default color map to be darker for higher variance
* manual or imported invariant points bub in psiso fixed
 * dio-o and gl-act-hb added to polymorphs

### 2.1.1 (28 Mar 2017)

* colors and cmap args added to cli version of psiso
* clabel of psiso specify field where contour labels will be placed

## 2.1 (23 Mar 2017)

* Major update and refactoring
* Starting guesses directly written to scriptfile
  (note that commented tags are needed in scriptfile)
* Updated parsing include rbi data
* Initial version of psexplorer to draw final pseudosections and isopleths
  (cli scrips provided)
* Manual unilines and invpoints shown in bold in lists

### 2.0.7 (13 Feb 2017)

* double-click on phaselist highlight all unilines with zero mode phase
* option to export partial areas
* excess phases stored in unilines and invpoints
* labeling phases sorted alphabeltically, same as phaselist
* auto bug fixed
* Keyboard shortcuts added Ctrl-T and Ctrl-P for CalcTatP and CalcPatT
* Ctrl-H Zoom home

### 2.0.6 (03 Feb 2017)

* refactoring and speedup
* executables stored in project
* scriptfile parsing improved
* several bugfixes

### 2.0.5 (19 Jan 2017)

* output parsing fixed (hopefully...)
* Rightclick invariant points menu fixed
* area construction for drawpd export fixed
* networkx dependecy removed

### 2.0.4 (13 Jan 2017)

* saveas added
* working directory written to Log window
* Log window catch output of both thermocalc and drawpd

### 2.0.3 (13 Jan 2017)

* invview right click to select not yet calculated uni lines implemented
* Zoom uni button persistent
* export list of phases in areas for TC-Investigator
* drawpd areas construction fixed

### 2.0.2 (10 Dec 2016)

* Areas export fixed
* inv filtering fixed

### 2.0.1 (10 Dec 2016)

* scriptfile encoding fix
* unilabels placement fixed
* Recent files implemented
* Adding uni and inv must be constrained by phases and out selection
* Export areas to drawpd
* refresh instead plot during zoom
* new unicutting algorithm
* Auto calculation around inv point
* THERMOCALC mac-roman encoding used

## 2.0 (19 Nov 2016)

* Initial release of PSBuilder
