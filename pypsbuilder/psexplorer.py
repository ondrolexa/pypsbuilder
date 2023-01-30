"""Module to postprocess pseudocestions constructed with builders.

This module contains tools to postprocess and explore pseudosections
calculated by available builders.

It provides a tools to visualize pseudosections constructed with
builders, calculate compositional variations within multivariant fields, and
plot compositional isopleths.

It provides four command line scipts `psgrid`, `psdrawpd`, `psshow` and `psiso`,
or could be used interactively, e.g. within jupyter notebooks.

Example:

    >>> from pypsbuilder import PTPS
    >>> pt = PTPS('/path/to/myproject.ptb')
    >>> pt.show()

"""
# author: Ondrej Lexa 2020
# website: petrol.natur.cuni.cz/~ondro

import argparse
import sys

# import os
try:
    import cPickle as pickle
except ImportError:
    import pickle
import gzip
import ast
import time
from pathlib import Path
from collections import OrderedDict
import warnings

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm, Normalize
from matplotlib.collections import LineCollection
from matplotlib.colorbar import ColorbarBase
from mpl_toolkits.axes_grid1 import make_axes_locatable
from matplotlib.table import table
from matplotlib import ticker

from shapely.geometry import MultiPoint, Point, LineString
from shapely.ops import linemerge
from scipy.interpolate import Rbf, interp1d
from scipy.linalg import LinAlgWarning, lstsq
from scipy.interpolate import griddata  # interp2d
from tqdm import tqdm, trange

from .tcapi import get_tcapi
from .psclasses import PTsection, TXsection, PXsection  # InvPoint, UniLine
from .psclasses import polymorphs, PolygonPatch


class PS:
    """Base class for PTPS, TXPS and PXPS classes"""

    def __init__(self, *args, **kwargs):
        """Create PTPS class instance from builder project file.

        Args:
            projfile (str, Path): psbuilder project file or files
            tolerance (float): if not None, simplification tolerance. Default None
            origwd (bool): If True TCAPI uses original stored working directory
                Default False.
        """
        projfiles = [Path(projfile).resolve() for projfile in args if Path(projfile).exists()]
        assert len(projfiles) > 0, 'You have to provide existing filename.'
        assert hasattr(self, 'section_class'), 'You can not instantiate base class directly. Use PTPS, TXPS or PXPS.'
        # parse kwargs
        tolerance = kwargs.get('tolerance', None)
        origwd = kwargs.get('origwd', False)
        # individual based (keys are 0, 1...)
        self.projfiles = {}
        self.sections = {}
        self.grids = {}
        self._shapes = {}
        self.unilists = {}
        self._variance = {}
        self.abbr = {}
        self.show_errors = kwargs.get('show_errors', False)
        # common
        self.tolerance = tolerance
        self.tc = None
        bulk = None
        # read
        for ix, projfile in enumerate(projfiles):
            self.projfiles[ix] = projfile
            with gzip.open(str(projfile), 'rb') as stream:
                data = pickle.load(stream)
            # check section type
            assert type(data['section']) == self.section_class, 'The provided project file is not {}.'.format(
                self.section_class.__name__
            )
            self.sections[ix] = data['section']
            # check if workdir exists
            if 'workdir' not in data:
                data['workdir'] = str(projfile.parent)
            # check workdit compatibility
            if self.tc is None:
                if origwd:
                    tc, ok = get_tcapi(Path(data['workdir']))
                    assert ok, 'Error during initialization of THERMOCALC in {}\n{}'.format(data['workdir'], tc)
                else:
                    tc, ok = get_tcapi(projfile.parent)
                    assert ok, 'Error during initialization of THERMOCALC in {}\n{}'.format(projfile.parent, tc)
                self.tc = tc
            else:
                if origwd:
                    assert data['workdir'] == str(tc.workdir), 'Workdirs of merged profiles must be same.'
                else:
                    assert projfile.parent == tc.workdir, 'Workdirs of merged profiles must be same.'

            self._shapes[ix], self.unilists[ix], log = self.sections[ix].create_shapes(tolerance=self.tolerance)
            if log:
                print('\n'.join(log))
            # process variances
            if 'variance' in data:
                self._variance[ix] = data['variance']
            else:
                # # calculate variance
                # variance = {}
                # calcs = ['calcP {} {}'.format(*self.tc.prange),
                #          'calcT {} {}'.format(*self.tc.trange),
                #          'with someof {}'.format(' '.join(self.tc.phases - self.tc.excess)),
                #          'acceptvar no']
                # old_calcs = self.tc.update_scriptfile(get_old_calcs=True, calcs=calcs)
                # for key in self._shapes[ix]:
                #     ans = '{}\nkill\n\n'.format(' '.join(key))
                #     tcout = self.tc.runtc(ans)
                #     try:
                #         for ln in tcout.splitlines():
                #             if 'variance of required equilibrium' in ln:
                #                 break
                #         variance[key] = int(ln[ln.index('(') + 1:ln.index('?')])
                #     except Exception:
                #         variance[key] = 0
                #         print('Variance calculation failed for {} field.'.format(key))
                #         if self.show_errors:
                #             print(tcout)
                # self._variance[ix] = variance
                # self.tc.update_scriptfile(calcs=old_calcs)
                variance = {}
                for key in self._shapes[ix]:
                    variance[key] = self.tc.calc_variance(key)
                self._variance[ix] = variance
            # bulk
            if bulk is None:
                if 'bulk' in data:
                    bulk = data['bulk']
                else:
                    bulk = self.tc.bulk
            else:
                if 'bulk' in data:
                    assert bulk == data['bulk'], 'Bulks in merged projects must be same'
            # already gridded?
            if 'grid' in data:
                self.grids[ix] = data['grid']
        # union _shapes
        self.shapes = {}
        for shapes in self._shapes.values():
            for key, shape in shapes.items():
                if key in self.shapes:
                    self.shapes[key] = self.shapes[key].union(shape)
                else:
                    self.shapes[key] = shape
        # update variable lookup table
        self.collect_all_data_keys()

    def __repr__(self):
        reprs = ['{} explorer'.format(type(self).__name__)]
        reprs.append(repr(self.tc))
        for ps in self.sections.values():
            reprs.append(repr(ps))
        reprs.append('Areas: {}'.format(len(self.shapes)))
        if self.gridded:
            for grid in self.grids.values():
                reprs.append(repr(grid))
        return '\n'.join(reprs)

    def __iter__(self):
        return iter(self.shapes)

    @property
    def xrange(self):
        return min(ps.xrange[0] for ps in self.sections.values()), max(ps.xrange[1] for ps in self.sections.values())

    @property
    def yrange(self):
        return min(ps.yrange[0] for ps in self.sections.values()), max(ps.yrange[1] for ps in self.sections.values())

    @property
    def x_var(self):
        return self.sections[0].x_var

    @property
    def y_var(self):
        return self.sections[0].y_var

    @property
    def gridxstep(self):
        if self.gridded:
            v = [grid.xstep for grid in self.grids.values()]
        else:
            v = [(self.xrange[1] - self.xrange[0]) / 50]
        return sum(v) / len(v)

    @property
    def gridystep(self):
        if self.gridded:
            v = [grid.ystep for grid in self.grids.values()]
        else:
            v = [(self.yrange[1] - self.yrange[0]) / 50]
        return sum(v) / len(v)

    @property
    def ratio(self):
        return (self.xrange[1] - self.xrange[0]) / (self.yrange[1] - self.yrange[0])

    @property
    def name(self):
        """Get project directory name."""
        return self.projfiles[0].parent.stem

    @property
    def gridded(self):
        """True when compositional grid(s) is calculated, otherwise False"""
        return all([i in self.grids for i in range(len(self.sections))])

    @property
    def phases(self):
        """Returns set of all phases present in pseudosection"""
        return {phase for key in self.keys for phase in key}

    @property
    def endmembers(self):
        """Returns dictionary with phases and their end-members names"""
        em = {}
        for comp in set(self.all_data_keys.keys()).difference(self.phases).difference(set(['bulk', 'sys'])):
            k, v = comp.split(')')[0].split('(')
            if k in em:
                em[k].append(v)
            else:
                em[k] = [v]
        return em

    @property
    def variance(self):
        """Returns dictionary of variances"""
        v = self._variance[0].copy()
        for ix in range(1, len(self._variance)):
            v.update(self._variance[ix])
        return v

    @property
    def keys(self):
        """Returns set of all existing multivariant fields. Fields are
        identified by frozenset of present phases called key."""
        keylist = []
        for shapes in self._shapes.values():
            keylist.extend(list(shapes.keys()))
        return set(keylist)

    def check_phase_expr(self, phase, expr):
        if phase in self.all_data_keys:
            if expr is None:
                msg = 'Missing expression argument. Available variables for phase {} are:\n{}'
                print(msg.format(phase, ' '.join(self.all_data_keys[phase])))
                if phase in self.endmembers:
                    print('Available end-members for {}: {}'.format(phase, ' '.join(self.endmembers[phase])))
                return False
            else:
                return True
        else:
            print('Unknown phase {}'.format(phase))
            return False

    def get_section_id(self, x, y):
        """Return index of pseudosection and grid containing point"""
        ix_ok = None
        for ix, ps in enumerate(self.sections.values()):
            _, area = ps.range_shapes
            if area.contains(Point(x, y)):
                ix_ok = ix
                break
        return ix_ok

    def invs_from_unilist(self, ix, unilist):
        """Return set of IDs of invariant points associated with unilines.
        lines.

        Args:
            unilist (iterable): list of (section_id, uni_id) pairs

        Returns:
            set: set of associated invariant points
        """
        return (
            {self.sections[ix].unilines[ed].begin for ed in unilist}
            .union({self.sections[ix].unilines[ed].end for ed in unilist})
            .difference({0})
        )

    def save(self):
        """Save gridded copositions and constructed divariant fields into
        psbuilder project file.

        Note that once project is edited with psbuilder, calculated compositions
        are removed and need to be recalculated using `PTPS.calculate_composition`
        method.
        """
        if self.gridded:
            for ix, projfile in self.projfiles.items():
                # put to dict
                with gzip.open(str(projfile), 'rb') as stream:
                    data = pickle.load(stream)
                data['variance'] = self._variance[ix]
                data['grid'] = self.grids[ix]
                # do save
                with gzip.open(str(projfile), 'wb') as stream:
                    pickle.dump(data, stream)
        else:
            print('Not yet gridded...')

    def create_masks(self):
        """Update grid masks from existing divariant fields"""
        if self.gridded:
            for ix, grid in self.grids.items():
                # Create data masks
                points = MultiPoint(list(zip(grid.xg.flatten(), grid.yg.flatten())))
                shapes = self._shapes[ix]
                for key in shapes:
                    grid.masks[key] = np.array(list(map(shapes[key].contains, points.geoms))).reshape(grid.xg.shape)
        else:
            print('Not yet gridded...')

    def common_grid_and_masks(self, **kwargs):
        """Initialize common grid and mask for all partial grids"""
        nx = kwargs.get('nx', np.round(np.diff(self.xrange)[0] / self.gridxstep).astype(int))
        ny = kwargs.get('ny', np.round(np.diff(self.yrange)[0] / self.gridystep).astype(int))
        self.xstep = np.diff(self.xrange)[0] / nx
        self.ystep = np.diff(self.yrange)[0] / ny
        self.xspace = np.linspace(self.xrange[0] + self.xstep / 2, self.xrange[1] - self.xstep / 2, nx)
        self.yspace = np.linspace(self.yrange[0] + self.ystep / 2, self.yrange[1] - self.ystep / 2, ny)
        self.xg, self.yg = np.meshgrid(self.xspace, self.yspace)
        # Create data masks
        self.masks = {}
        points = MultiPoint(list(zip(self.xg.flatten(), self.yg.flatten())))
        for key in self.shapes:
            self.masks[key] = np.array(list(map(self.shapes[key].contains, points.geoms))).reshape(self.xg.shape)

    def collect_all_data_keys(self):
        """Collect all phases and variables calculated on grid.

        Result is stored in `all_data_keys` property as dictionary of
        dictionaries.

        Example:
            To get list of all variables calculated for phase 'g' or end-member
            'g(alm)' use::

                >>> pt.all_data_keys['g']
                ['mode', 'x', 'z', 'm', 'f', 'xMgX', 'xFeX', 'xMnX', 'xCaX', 'xAlY',
                'xFe3Y', 'H2O', 'SiO2', 'Al2O3', 'CaO', 'MgO', 'FeO', 'K2O', 'Na2O',
                'TiO2', 'MnO', 'O', 'factor', 'G', 'H', 'S', 'V', 'rho']
                >>> pt.all_data_keys['g(alm)']
                ['ideal', 'gamma', 'activity', 'prop', 'mu', 'RTlna']
        """
        data = dict()
        valid_phases = self.phases
        for ix, ps in self.sections.items():
            for inv in ps.invpoints.values():
                if not inv.manual:
                    for comp in inv.datakeys():
                        k = comp.split(')')[0].split('(')
                        if k[0] in valid_phases:
                            data[comp] = inv.datakeys(comp)

        if not valid_phases.issubset(data.keys()):
            # Search in unilines
            for ix, ps in self.sections.items():
                for uni in ps.unilines.values():
                    if not uni.manual:
                        for comp in uni.datakeys():
                            k = comp.split(')')[0].split('(')
                            if k[0] in valid_phases:
                                data[comp] = uni.datakeys(comp)

            if not valid_phases.issubset(data.keys()):
                # Search in griddata  NEED CHECK AND FIX
                for ix, grid in self.grids.items():
                    shapes = self._shapes[ix]
                    for key in shapes:
                        results = grid.gridcalcs[grid.masks[key] & (grid.status == 1)]
                        if len(results) > 0:
                            for comp in results[0].phases:
                                k = comp.split(')')[0].split('(')
                                if k[0] in valid_phases:
                                    data[comp] = list(results[0][comp].keys())

                if not valid_phases.issubset(data.keys()):
                    print('Some phases not calculated.')
        # if self.gridded:
        #     for ix, grid in self.grids.items():
        #         shapes = self._shapes[ix]
        #         for key in shapes:
        #             res = grid.gridcalcs[grid.masks[key] & (grid.status == 1)]
        #             if len(res) > 0:
        #                 for k in res[0]['data'].keys():
        #                     data[k] = list(res[0]['data'][k].keys())
        self.all_data_keys = data

    def collect_inv_data(self, key, phase, expr):
        """Retrieve value of variables based expression for given phase for
        all invariant points surrounding divariant field identified by key.

        Args:
            key (frozenset): Key identifying divariant field
            phase (str): Phase or end-member named
            expr (str): Expression to evaluate. It could use any variable
                existing for given phase. Check `all_data_keys` property for
                possible variables.

         Returns:
            Dictionary with 'pts' key storing list of coordinate tuples(t,p) and
            'data' key  storing list of thermocalc results.
        """
        dt = dict(pts=[], data=[])
        for ix, ps in self.sections.items():
            if key in self.unilists[ix]:
                for id_inv in self.invs_from_unilist(ix, self.unilists[ix][key]):
                    inv = ps.invpoints[id_inv]
                    if not inv.manual:
                        if phase in inv.results.phases:
                            if self.shapes[key].intersects(Point(inv._x, inv._y)):
                                dt['pts'].append((inv._x, inv._y))
                                dt['data'].append(eval_expr(expr, inv.results[0][phase]))
        return dt

    def collect_uni_data(self, key, phase, expr):
        """Retrieve values of expression for given phase for
        all univariant lines surrounding divariant field identified by key.

        Args:
            key (frozenset): Key identifying divariant field
            phase (str): Phase or end-member named
            expr (str): Expression to evaluate. It could use any variable
                existing for given phase. Check `all_data_keys` property for
                possible variables.

         Returns:
            Dictionary with 'pts' key storing list of coordinate tuples(t,p) and
            'data' key  storing list of thermocalc results.
        """
        dt = dict(pts=[], data=[])
        for ix, ps in self.sections.items():
            if key in self.unilists[ix]:
                for id_uni in self.unilists[ix][key]:
                    uni = ps.unilines[id_uni]
                    if not uni.manual:
                        if phase in uni.results.phases:
                            edt = zip(
                                uni._x[uni.used],
                                uni._y[uni.used],
                                uni.results[uni.used],
                            )
                            for x, y, res in edt:
                                if self.shapes[key].intersects(Point(x, y)):
                                    dt['pts'].append((x, y))
                                    dt['data'].append(eval_expr(expr, res[phase]))
        return dt

    def collect_grid_data(self, key, phase, expr):
        """Retrieve values of expression for given phase for
        all GridData points within divariant field identified by key.

        Args:
            key (frozenset): Key identifying divariant field
            phase (str): Phase or end-member named
            expr (str): Expression to evaluate. It could use any variable
                existing for given phase. Check `all_data_keys` property for
                possible variables.

         Returns:
            Dictionary with 'pts' key storing list of coordinate tuples(t,p) and
            'data' key  storing list of thermocalc results.
        """
        dt = dict(pts=[], data=[])
        if self.gridded:
            for ix, grid in self.grids.items():
                if key in grid.masks:
                    results = grid.gridcalcs[grid.masks[key] & (grid.status == 1)]
                    if len(results) > 0:
                        if phase in results[0].phases:
                            gdt = zip(
                                grid.xg[grid.masks[key]],
                                grid.yg[grid.masks[key]],
                                results,
                                grid.status[grid.masks[key]],
                            )
                            for x, y, res, ok in gdt:
                                if ok == 1:
                                    dt['pts'].append((x, y))
                                    dt['data'].append(eval_expr(expr, res[phase]))
        # else:
        #     print('Not yet gridded...')
        return dt

    def get_nearest_grid_data(self, x, y):
        """Retrieve nearest results from GridData to point.

        Args:
            x (float): x-coordinate of point
            y (float): y-coordiante of point

         Returns:
            THERMOCALC result set a assemblage key
        """
        dt = dict(pts=[], data=[])
        if self.gridded:
            ix = self.get_section_id(x, y)
            if ix is not None:
                r, c = self.grids[ix].get_indexes(x, y)
                dt = self.grids[ix].gridcalcs[r, c]
            return dt
        else:
            print('Not yet gridded...')

    def collect_data(self, key, phase, expr, which=7):
        """Convinient function to retrieve values of expression
        for given phase for user-defined combination of results of divariant
        field identified by key.

        Args:
            key (frozenset): Key identifying divariant field

            phase (str): Phase or end-member named
            expr (str): Expression to evaluate. It could use any variable
                existing for given phase. Check `all_data_keys` property for
                possible variables.
            which (int): Bitopt defining from where data are collected. 0 bit -
                invariant points, 1 bit - uniariant lines and 2 bit - GridData
                points

         Returns:
            Dictionary with 'pts' key storing list of coordinate tuples(t,p) and
            'data' key  storing list of thermocalc results.
        """
        dt = dict(pts=[], data=[])
        # check if phase or end-member is in assemblage
        if phase in self.all_data_keys:
            if which & (1 << 0):
                d = self.collect_inv_data(key, phase, expr)
                dt['pts'].extend(d['pts'])
                dt['data'].extend(d['data'])
            if which & (1 << 1):
                d = self.collect_uni_data(key, phase, expr)
                dt['pts'].extend(d['pts'])
                dt['data'].extend(d['data'])
            if which & (1 << 2):
                d = self.collect_grid_data(key, phase, expr)
                dt['pts'].extend(d['pts'])
                dt['data'].extend(d['data'])
        return dt

    def merge_data(self, phase, expr, which=7):
        """Returns merged data obtained by `collect_data` method for all
        divariant fields.

        Args:
            phase (str): Phase or end-member named
            expr (str): Expression to evaluate. It could use any variable
                existing for given phase. Check `all_data_keys` property for
                possible variables.
            which (int): Bitopt defining from where data are collected. 0 bit -
                invariant points, 1 bit - uniariant lines and 2 bit - GridData
                points

         Returns:
            Dictionary with 'pts' key storing list of coordinate tuples(t,p) and
            'data' key  storing list of thermocalc results.
        """
        mn, mx = sys.float_info.max, -sys.float_info.max
        recs = OrderedDict()
        for key in self:
            d = self.collect_data(key, phase, expr, which=which)
            z = d['data']
            if z:
                recs[key] = d
                mn = min(mn, min(z))
                mx = max(mx, max(z))
            # res = self.grid.gridcalcs[self.grid.masks[key]]
            # if len(res) > 0:
            #     if phase in res[0]['data']:
            #         d = self.collect_data(key, phase, expr, which=which)
            #         z = d['data']
            #         if z:
            #             recs[key] = d
            #             mn = min(mn, min(z))
            #             mx = max(mx, max(z))
        return recs, mn, mx

    def show(self, **kwargs):
        """Method to draw PT pseudosection.

        Args:
            label (bool): Whether to label divariant fields. Default False.
            out (str or list): Highligt zero-mode lines for given phases.
            high (frozenset or list): Highlight divariant fields identified
                by key(s).
            cmap (str): matplotlib colormap used to divariant fields coloring.
                Colors are based on variance. Default 'Purples'.
            bulk (bool): Whether to show bulk composition on top of diagram.
                Default False.
            alpha (float): alpha value for colors. Default 0.6
            connect (bool): Whether mouse click echo stable assemblage to STDOUT.
                Default False.
            show_vertices (bool): Whether to show vertices of drawn areas.
                Default False.
            fig_kw: dict passed to subplots method.
            filename: If not None, figure is saved to file
            save_kw: dict passed to savefig method.
        """
        out = kwargs.get('out', None)
        cmap = kwargs.get('cmap', 'Purples')
        alpha = kwargs.get('alpha', 0.6)
        label = kwargs.get('label', False)
        skiplabels = kwargs.get('skiplabels', 0)
        labelfs = kwargs.get('labelfs', 6)
        bulk = kwargs.get('bulk', False)
        high = kwargs.get('high', [])
        connect = kwargs.get('connect', False)
        show_vertices = kwargs.get('show_vertices', False)
        fig = kwargs.get('fig', None)
        fig_kw = kwargs.get('fig_kw', {})
        filename = kwargs.get('filename', None)
        save_kw = kwargs.get('save_kw', {})

        if self.shapes:
            if isinstance(out, str):
                out = [out]
            vari = [self.variance[k] for k in self]
            poc = max(vari) - min(vari) + 1
            # skip extreme values to visually differs from empty areas
            pscolors = plt.get_cmap(cmap)(np.linspace(0, 1, poc + 2))[1:-1, :]
            # Set alpha
            pscolors[:, -1] = alpha
            pscmap = ListedColormap(pscolors)
            norm = BoundaryNorm(np.arange(min(vari) - 0.5, max(vari) + 1.5), poc, clip=True)
            if fig is None:
                show = True
                fig, ax = plt.subplots(**fig_kw)
            else:
                show = False
                ax = fig.add_subplot()
            for k, shape in self.shapes.items():
                patch = PolygonPatch(shape, fc=pscmap(norm(self.variance[k])), ec='none')
                ax.add_patch(patch)
                if show_vertices:
                    x, y = zip(*patch.get_path().vertices)
                    ax.plot(x, y, 'k.', ms=3)
            ax.autoscale_view()
            self.add_overlay(ax, label=label, skiplabels=skiplabels, fontsize=labelfs)
            if out:
                for o in out:
                    xy = []
                    for ix, ps in self.sections.items():
                        for uni in ps.unilines.values():
                            if o in uni.out:
                                xy.append(np.array(uni.shape().coords).T)
                            for poly in polymorphs:
                                if poly.issubset(uni.phases):
                                    if o in poly:
                                        if poly.difference({o}).issubset(uni.out):
                                            xy.append(np.array(uni.shape().coords).T)
                    if xy:
                        ax.plot(
                            np.hstack([(*seg[0], np.nan) for seg in xy]),
                            np.hstack([(*seg[1], np.nan) for seg in xy]),
                            lw=2,
                            label=o,
                        )
                # Shrink current axis's width
                box = ax.get_position()
                ax.set_position([box.x0 + box.width * 0.07, box.y0, box.width * 0.95, box.height])
                # Put a legend below current axis
                ax.legend(loc='upper right', bbox_to_anchor=(-0.08, 1), title='Out', borderaxespad=0, frameon=False)
            divider = make_axes_locatable(ax)
            cax = divider.append_axes('right', size='4%', pad=0.05)
            cbar = ColorbarBase(
                ax=cax, cmap=pscmap, norm=norm, orientation='vertical', ticks=np.arange(min(vari), max(vari) + 1)
            )
            cbar.set_label('Variance')
            ax.set_xlim(self.xrange)
            ax.set_ylim(self.yrange)
            ax.set_xlabel(self.x_var)
            ax.set_ylabel(self.y_var)
            # Show highlight. Change to list if only single key
            if not isinstance(high, list):
                high = [high]
            for k in high:
                if isinstance(k, str):
                    k = frozenset(k.split())
                k = k.union(self.tc.excess)
                if k in self.keys:
                    ax.add_patch(PolygonPatch(self.shapes[k], fc='none', ec='red', lw=2))
                else:
                    print('Field {} not found.'.format(' '.join(k)))
            # Show bulk
            if bulk:
                if label:
                    ax.set_xlabel(self.name + (len(self.tc.excess) * ' +{}').format(*self.tc.excess))
                else:
                    ax.set_xlabel(self.name)
                # bulk composition
                if self.section_class.__name__ == 'PTsection':
                    if self.tc.usedbulk is not None:
                        ox, val = self.tc.usedbulk
                    else:
                        ox, val = self.tc.bulk
                    table(ax=ax, cellText=[val], colLabels=ox, loc='top')
                else:
                    if self.tc.usedbulk is not None:
                        ox, val1, val2 = self.tc.usedbulk
                    else:
                        ox, val1, val2 = self.tc.bulk
                    table(ax=ax, cellText=[val1, val2], colLabels=ox, loc='top')
            else:
                if label:
                    ax.set_title(self.name + (len(self.tc.excess) * ' +{}').format(*self.tc.excess))
                else:
                    ax.set_title(self.name)
            # coords
            ax.format_coord = self.format_coord
            # connect button press
            if connect:
                fig.canvas.mpl_connect('button_press_event', self.onclick)
            if filename is not None:
                plt.savefig(filename, **save_kw)
                plt.close(fig)
            else:
                if show:
                    plt.show()
        else:
            print('There is no single area defined in your pseudosection. Check topology.')

    def format_coord(self, x, y):
        prec = 2
        point = Point(x, y)
        phases = ''
        for key, shape in self.shapes.items():
            if shape.contains(point):
                phases = ' '.join(sorted(list(key.difference(self.tc.excess))))
                break
        return '{}={:.{prec}f} {}={:.{prec}f} {}'.format(self.x_var, x, self.y_var, y, phases, prec=prec)

    def add_overlay(self, ax, fc='none', ec='k', label=False, skiplabels=0, fontsize=6):
        area = (self.xrange[1] - self.xrange[0]) * (self.yrange[1] - self.yrange[0])
        for k, shape in self.shapes.items():
            ax.add_patch(PolygonPatch(shape, ec=ec, fc=fc, lw=0.5))
            if label and (100 * shape.area / area > skiplabels):
                # multiline for long labels
                tl = sorted(list(k.difference(self.tc.excess)))
                extra = self.tc.excess.difference(self.tc.excess.intersection(k))
                # if excess in scriptfile is not accurate
                if extra:
                    tl += ['-{}'.format(pp) for pp in extra]
                wp = len(tl) // 4 + int(len(tl) % 4 > 1)
                txt = '\n'.join(
                    [
                        ' '.join([self.abbr.get(sa, sa) for sa in s])
                        for s in [tl[i * len(tl) // wp : (i + 1) * len(tl) // wp] for i in range(wp)]
                    ]
                )
                if shape.geom_type == 'MultiPolygon':
                    for part in shape:
                        xy = part.representative_point().coords[0]
                        ax.annotate(text=txt, xy=xy, weight='bold', fontsize=fontsize, ha='center', va='center')
                else:
                    xy = shape.representative_point().coords[0]
                    ax.annotate(text=txt, xy=xy, weight='bold', fontsize=fontsize, ha='center', va='center')

    def show_data(self, key, phase, expr=None, which=7):
        """Convinient function to show values of expression
        for given phase for user-defined combination of results of divariant
        field identified by key.

        Args:
            key (frozenset): Key identifying divariant field
            phase (str): Phase or end-member named
            expr (str): Expression to evaluate. It could use any variable
                existing for given phase. Check `all_data_keys` property for
                possible variables.
            which (int): Bitopt defining from where data are collected. 0 bit -
                invariant points, 1 bit - uniariant lines and 2 bit - GridData
                points

         Returns:
            Dictionary with 'pts' key storing list of coordinate tuples(t,p) and
            'data' key  storing list of thermocalc results.
        """
        if self.check_phase_expr(phase, expr):
            dt = self.collect_data(key, phase, expr, which=which)
            x, y = np.array(dt['pts']).T
            fig, ax = plt.subplots()
            pts = ax.scatter(x, y, c=dt['data'])
            ax.set_title('{} - {}({})'.format(' '.join(key), phase, expr))
            plt.colorbar(pts)
            plt.show()

    def show_grid(self, phase, expr=None, interpolation=None, label=False, skiplabels=0, labelfs=6):
        """Convinient function to show values of expression for given phase only
        from Grid Data.

        Args:
            phase (str): Phase or end-member named
            expr (str): Expression to evaluate. It could use any variable
                existing for given phase. Check `all_data_keys` property for
                possible variables.
            interpolation (str): matplotlib imshow interpolation method.
                Default None.
            label (bool): Whether to label divariant fields. Default False.
        """
        if self.gridded:
            if self.check_phase_expr(phase, expr):
                fig, ax = plt.subplots()
                cgd = {}
                mn, mx = sys.float_info.max, -sys.float_info.max
                for ix, grid in self.grids.items():
                    gd = np.empty(grid.xg.shape)
                    gd[:] = np.nan
                    for key in grid.masks:
                        results = grid.gridcalcs[grid.masks[key] & (grid.status == 1)]
                        if len(results) > 0:
                            if phase in results[0].phases:
                                rows, cols = np.nonzero(grid.masks[key])
                                for r, c in zip(rows, cols):
                                    if grid.status[r, c] == 1:
                                        gd[r, c] = eval_expr(expr, grid.gridcalcs[r, c][phase])
                    cgd[ix] = gd
                    mn = min(np.nanmin(gd), mn)
                    mx = max(np.nanmax(gd), mx)
                for ix, grid in self.grids.items():
                    im = ax.imshow(
                        cgd[ix],
                        extent=grid.extent,
                        interpolation=interpolation,
                        aspect='auto',
                        origin='lower',
                        vmin=mn,
                        vmax=mx,
                    )
                self.add_overlay(ax, label=label, skiplabels=skiplabels, fontsize=labelfs)
                ax.set_xlim(self.xrange)
                ax.set_ylim(self.yrange)
                fig.colorbar(im)
                ax.set_title('{}({})'.format(phase, expr))
                fig.tight_layout()
                plt.show()
        else:
            print('Not yet gridded...')

    def show_status(self, label=False, skiplabels=0, labelfs=6):
        """Shows status of grid calculations"""
        if self.gridded:
            fig, ax = plt.subplots()
            im = {}
            cmap = ListedColormap(['orangered', 'limegreen'])
            bounds = [-0.5, 0.5, 1.5]
            norm = BoundaryNorm(bounds, cmap.N)
            for ix, grid in self.grids.items():
                im[ix] = ax.imshow(grid.status, extent=grid.extent, aspect='auto', origin='lower', cmap=cmap, norm=norm)
            self.add_overlay(ax, label=label, skiplabels=skiplabels, fontsize=labelfs)
            ax.set_xlim(self.xrange)
            ax.set_ylim(self.yrange)
            ax.set_title('Gridding status - {}'.format(self.name))
            cbar = fig.colorbar(im[0], boundaries=bounds, ticks=[0, 1])
            cbar.ax.set_yticklabels(['Failed', 'OK'])
            fig.tight_layout()
            plt.show()
        else:
            print('Not yet gridded...')

    def show_delta(self, label=False, pointsec=False, skiplabels=0, labelfs=6):
        """Shows THERMOCALC execution time for all grid points.

        Args:
            pointsec (bool): Whether to show points/sec or secs/point. Default False.
            label (bool): Whether to label divariant fields. Default False.
        """
        if self.gridded:
            fig, ax = plt.subplots()
            cval = {}
            mn, mx = sys.float_info.max, -sys.float_info.max
            for ix, grid in self.grids.items():
                if pointsec:
                    val = 1 / grid.delta
                    lbl = 'points/sec'
                    tit = 'THERMOCALC calculation rate - {}'
                else:
                    val = grid.delta
                    lbl = 'secs/point'
                    tit = 'THERMOCALC execution time - {}'
                cval[ix] = val
                mn = min(np.nanmin(val), mn)
                mx = max(np.nanmax(val), mx)
            for ix, grid in self.grids.items():
                im = ax.imshow(cval[ix], extent=grid.extent, aspect='auto', origin='lower', vmin=mn, vmax=mx)
            self.add_overlay(ax, label=label, skiplabels=skiplabels, fontsize=labelfs)
            ax.set_xlim(self.xrange)
            ax.set_ylim(self.yrange)
            cbar = fig.colorbar(im)
            cbar.set_label(lbl)
            ax.set_title(tit.format(self.name))
            fig.tight_layout()
            plt.show()
        else:
            print('Not yet gridded...')

    def identify(self, x, y):
        """Return key (frozenset) of divariant field for given temperature and pressure.

        Args:
            x (float): x coord
            y (float): y coord
        """
        key = None
        for k, shape in self.shapes.items():
            if shape.contains(Point(x, y)):
                key = k
                break
        return key

    def gidentify(self, label=False, skiplabels=0, labelfs=6):
        """Visual version of `identify` method. PT point is provided by mouse click.

        Args:
            label (bool): Whether to label divariant fields. Default False.
        """
        fig, ax = plt.subplots()
        ax.autoscale_view()
        self.add_overlay(ax, label=label, skiplabels=skiplabels, fontsize=labelfs)
        ax.set_xlim(self.xrange)
        ax.set_ylim(self.yrange)
        ax.format_coord = self.format_coord
        x, y = plt.ginput(1)[0]
        plt.close(fig)
        return self.identify(x, y)

    def glabel(self, label=False, skiplabels=0, labelfs=6):
        """Return formatted string of assamblage at PT point provided by mouse click.

        Args:
            label (bool): Whether to label divariant fields. Default False.
        """
        fig, ax = plt.subplots()
        ax.autoscale_view()
        self.add_overlay(ax, label=label, skiplabels=skiplabels, fontsize=labelfs)
        ax.set_xlim(self.xrange)
        ax.set_ylim(self.yrange)
        ax.format_coord = self.format_coord
        pts = plt.ginput(0)
        plt.close(fig)
        for ix, (x, y) in enumerate(pts):
            print(f'{ix+1}: {" ".join(sorted([self.abbr.get(sa, sa) for sa in self.identify(x, y)]))}')

    def pointcalc(self, label=False, skiplabels=0, labelfs=6):
        fig, ax = plt.subplots()
        ax.autoscale_view()
        self.add_overlay(ax, label=label, skiplabels=skiplabels, fontsize=labelfs)
        ax.set_xlim(self.xrange)
        ax.set_ylim(self.yrange)
        ax.format_coord = self.format_coord
        x, y = plt.ginput(1)[0]
        plt.close(fig)
        k = self.identify(x, y)
        if k is not None:
            last_inv = 0
            for ix, ps in self.sections.items():
                # update guesses from closest inv point
                dst = sys.float_info.max
                for id_inv, inv in ps.invpoints.items():
                    d2 = (inv._x - x) ** 2 + (inv._y - y) ** 2
                    if d2 < dst:
                        dst = d2
                        id_close = id_inv
                if id_close != last_inv and not ps.invpoints[id_close].manual:
                    self.tc.update_scriptfile(guesses=ps.invpoints[id_close].ptguess())
                    last_inv = id_close
            tcout, ans = self.tc.calc_assemblage(k.difference(self.tc.excess), y, x)
            status, res, output = self.tc.parse_logfile()
            if res is None:
                for ix, ps in self.sections.items():
                    # update guesses from closest uni line point
                    dst = sys.float_info.max
                    for id_uni in self.unilists[ix][k]:
                        uni = ps.unilines[id_uni]
                        if not uni.manual:
                            for vix in list(range(len(uni._x))[uni.used]):
                                d2 = (uni._x[vix] - x) ** 2 + (uni._y[vix] - y) ** 2
                                if d2 < dst:
                                    dst = d2
                                    id_close = id_uni
                                    vix_close = vix
                    self.tc.update_scriptfile(guesses=ps.unilines[id_close].ptguess(idx=vix_close))
                tcout, ans = self.tc.calc_assemblage(k.difference(self.tc.excess), y, x)
                status, res, output = self.tc.parse_logfile()
            if res is None:
                print('Calculation failed')
            else:
                print(output)
                return res[0]

    def ginput_path(self, label=False, skiplabels=0, labelfs=6):
        """Collect Path data by mouse digitizing.

        Args:
            label (bool): Whether to label divariant fields. Default False.
        """
        fig, ax = plt.subplots()
        ax.autoscale_view()
        self.add_overlay(ax, label=label, skiplabels=skiplabels, fontsize=labelfs)
        ax.set_xlim(self.xrange)
        ax.set_ylim(self.yrange)
        ax.format_coord = self.format_coord
        xy = plt.ginput(0)
        return np.array(xy).T

    def onclick(self, event):
        if event.button == 1:
            if event.inaxes:
                key = self.identify(event.xdata, event.ydata)
                if key:
                    print(' '.join(sorted([self.abbr.get(sa, sa) for sa in key])))

    def isopleths(self, phase, expr=None, **kwargs):
        """Method to draw compositional isopleths.

        Isopleths are drawn as contours for values evaluated from provided
        expression. Individual divariant fields are contoured separately, so
        final plot allows sharp changes accross univariant lines. Within
        divariant field the selected interpolation is used.

        Args:
            phase (str): Phase or end-member named
            expr (str): Expression to evaluate. It could use any variable
                existing for given phase. Check `all_data_keys` property for
                possible variables.
            N (int): Max number of contours. Default 10.
            step (int): Step between contour levels. If defined, N is ignored.
                Default None.
            cdf (bool): When True contour levels are percentile based.
                Default False.
            levels (list): User-defined contour levels. If defined, N and step
                is ignored.
            which (int): Bitopt defining from where data are collected. 0 bit -
                invariant points, 1 bit - uniariant lines and 2 bit - GridData
                points. Default 7 (all data)
            method: Interpolation method. Default is 'rbf', other option is
                'quadratic', which uses least-square fit to quadratic surface.
            rbf_func: Default 'thin_plate'. See scipy.interpolation.Rbf
            smooth (int): Values greater than zero increase the smoothness
                of the approximation. 0 is for interpolation (default),
                the function will always go through the nodal points.
            epsilon (int): Adjustable constant for gaussian or multiquadrics
                functions - defaults to approximate average distance between
                nodes (which is a good start).
            refine (int): Degree of grid refinement. Default 1
            filled (bool): Whether to contours should be filled. Defaut True.
            filled_over (bool): Whether to overlay contourline over filled
                contours. Defaut False.
            out (str or list): Highligt zero-mode lines for given phases.
            high (frozenset or list): Highlight divariant fields identified
                by key(s).
            cmap (str): matplotlib colormap used to divariant fields coloring.
                Colors are based on variance. Default 'viridis'.
            bulk (bool): Whether to show bulk composition on top of diagram.
                Default False.
            labelkeys (frozenset or list): Keys of divariant fields where contours
                should be labeled.
            nosplit (bool): Controls whether the contour underlying labels are
                removed or not. Defaut True
            gradient (bool): Whether the first derivate of values should be used.
                Default False.
            dt (bool): Whether the gradient should be calculated along
                temperature or pressure. Default True.
            fig_kw: dict passed to subplots method.
            filename: If not None, figure is saved to file
            save_kw: dict passed to savefig method.
        """
        if self.check_phase_expr(phase, expr):
            # parse kwargs
            which = kwargs.get('which', 7)
            smooth = kwargs.get('smooth', 0)
            epsilon = kwargs.get('epsilon', None)
            filled = kwargs.get('filled', True)
            filled_over = kwargs.get('filled_over', False)
            out = kwargs.get('out', None)
            bulk = kwargs.get('bulk', False)
            high = kwargs.get('high', [])
            nosplit = kwargs.get('nosplit', False)
            step = kwargs.get('step', None)
            N = kwargs.get('N', 10)
            cdf = kwargs.get('cdf', False)
            gradient = kwargs.get('gradient', False)
            dx = kwargs.get('dx', True)
            only = kwargs.get('only', None)
            refine = kwargs.get('refine', 1)
            method = kwargs.get('method', 'rbf')
            rbf_func = kwargs.get('rbf_func', 'thin_plate')
            cmap = kwargs.get('cmap', 'viridis')
            labelkeys = kwargs.get('labelkeys', [])
            fig = kwargs.get('fig', None)
            fig_kw = kwargs.get('fig_kw', {})
            filename = kwargs.get('filename', None)
            save_kw = kwargs.get('save_kw', {})

            if not self.gridded:
                print('Collecting only from uni lines and inv points. Not yet gridded...')
            # fix labelkeys
            if not isinstance(labelkeys, list):
                labelkeys = [labelkeys]
            labelkyes_ok = []
            for lbl in labelkeys:
                if isinstance(lbl, str):
                    lbl = frozenset(lbl.split())
                labelkyes_ok.append(lbl.union(self.tc.excess))
            if isinstance(out, str):
                out = [out]
            if only is not None:
                recs = OrderedDict()
                d = self.collect_data(only, phase, expr, which=which)
                z = d['data']
                if z:
                    recs[only] = d
                    mn = min(z)
                    mx = max(z)
            else:
                recs, mn, mx = self.merge_data(phase, expr, which=which)
            if step:
                cntv = np.arange(0, mx + step, step)
                cntv = cntv[cntv >= mn - step]
            else:
                if cdf:
                    dd = []
                    for key in recs:
                        dd.extend(recs[key]['data'])
                    cntv = np.percentile(dd, np.linspace(0, 100, N))
                else:
                    ml = ticker.MaxNLocator(nbins=N)
                    cntv = ml.tick_values(vmin=mn, vmax=mx)
            cntv = kwargs.get('levels', cntv)
            # Thin-plate contouring of areas
            if fig is None:
                show = True
                fig, ax = plt.subplots(**fig_kw)
            else:
                show = False
                ax = fig.add_subplot()
            for key in recs:
                phase_parts = phase.split(')')[0].split('(')
                if phase_parts[0] in key:
                    tmin, pmin, tmax, pmax = self.shapes[key].bounds
                    # ttspace = self.xspace[np.logical_and(self.xspace >= tmin - self.xstep, self.xspace <= tmax + self.xstep)]
                    # ppspace = self.yspace[np.logical_and(self.yspace >= pmin - self.ystep, self.yspace <= pmax + self.ystep)]
                    ttspace = np.arange(tmin - self.gridxstep, tmax + self.gridxstep, self.gridxstep / refine)
                    ppspace = np.arange(pmin - self.gridystep, pmax + self.gridystep, self.gridystep / refine)
                    tg, pg = np.meshgrid(ttspace, ppspace)
                    x, y = np.array(recs[key]['pts']).T
                    pts = recs[key]['pts']
                    data = recs[key]['data']
                    try:
                        if method == 'quadratic':
                            tgg = tg.flatten()
                            pgg = pg.flatten()
                            A = np.c_[np.ones_like(x), x, y, x * y, x**2, y**2]
                            C, _, _, _ = lstsq(A, data)
                            # evaluate it on a grid
                            zg = np.dot(np.c_[np.ones_like(tgg), tgg, pgg, tgg * pgg, tgg**2, pgg**2], C).reshape(
                                tg.shape
                            )
                        else:
                            with warnings.catch_warnings():
                                warnings.filterwarnings("error")
                                rbf = Rbf(x, self.ratio * y, data, function=rbf_func, smooth=smooth, epsilon=epsilon)
                                zg = rbf(tg, self.ratio * pg)
                    except Exception as e:
                        if self.show_errors:
                            print(e)
                        try:
                            if method == 'quadratic':
                                print('Using nearest method in {}'.format(' '.join(sorted(list(key)))))
                                zg = griddata(np.array(pts), data, (tg, pg), method='nearest', rescale=True)
                            else:
                                # preprocess with griddata
                                zg_tmp = griddata(pts, data, (tg, pg), method='linear', rescale=True)
                                # locate valid data
                                ri, ci = np.nonzero(np.isfinite(zg_tmp))
                                x, y, z = np.array([[tg[r, c], pg[r, c], zg_tmp[r, c]] for r, c in zip(ri, ci)]).T
                                # do Rbf extrapolation
                                with warnings.catch_warnings():
                                    warnings.filterwarnings("ignore", category=LinAlgWarning)
                                    rbf = Rbf(x, self.ratio * y, z, function=rbf_func, smooth=smooth, epsilon=epsilon)
                                    zg = rbf(tg, self.ratio * pg)
                        except Exception:
                            print('Using nearest method in {}'.format(' '.join(sorted(list(key)))))
                            zg = griddata(np.array(pts), data, (tg, pg), method='nearest', rescale=True)
                    # experimental
                    if gradient:
                        grd = np.gradient(zg, self.gridxstep, self.gridystep)
                        if dx:
                            zg = grd[0]
                        else:
                            zg = -grd[1]
                        if N:
                            cntv = N
                        else:
                            cntv = 10
                    # ------------
                    with warnings.catch_warnings():
                        warnings.filterwarnings("ignore", category=UserWarning)
                        if filled:
                            cont = ax.contourf(tg, pg, zg, cntv, cmap=cmap)
                            if filled_over:
                                contover = ax.contour(tg, pg, zg, cntv, colors='whitesmoke')
                        else:
                            cont = ax.contour(tg, pg, zg, cntv, cmap=cmap)
                    patch = PolygonPatch(self.shapes[key], fc='none', ec='none')
                    ax.add_patch(patch)
                    for col in cont.collections:
                        col.set_clip_path(patch)
                    if filled and filled_over:
                        for col in contover.collections:
                            col.set_clip_path(patch)
                    # label if needed
                    if not filled and key in labelkyes_ok:
                        positions = []
                        for col in cont.collections:
                            for seg in col.get_paths():  # get_segments():
                                inside = np.fromiter(
                                    map(self.shapes[key].contains, MultiPoint(seg.vertices).geoms), dtype=bool
                                )
                                if np.any(inside):
                                    positions.append(seg.vertices[inside].mean(axis=0))
                        ax.clabel(cont, fontsize=9, manual=positions, fmt='%g', inline_spacing=3, inline=not nosplit)
            if only is None:
                self.add_overlay(ax)
                # zero mode lines
                if out:
                    for o in out:
                        xy = []
                        for ps in self.sections.values():
                            for uni in ps.unilines.values():
                                if o in uni.out:
                                    xy.append((uni.x, uni.y))
                                for poly in polymorphs:
                                    if poly.issubset(uni.phases):
                                        if o in poly:
                                            if poly.difference({o}).issubset(uni.out):
                                                xy.append((uni.x, uni.y))
                        if xy:
                            ax.plot(
                                np.hstack([(*seg[0], np.nan) for seg in xy]),
                                np.hstack([(*seg[1], np.nan) for seg in xy]),
                                lw=2,
                            )
            try:
                fig.colorbar(cont)
            except Exception as e:
                print('There is trouble to draw colorbar. Sorry.')
                if self.show_errors:
                    print(e)
            # Show highlight. Change to list if only single key
            if not isinstance(high, list):
                high = [high]
            if only is None:
                for k in high:
                    if isinstance(k, str):
                        k = frozenset(k.split())
                    k = k.union(self.tc.excess)
                    if k in self.shapes:
                        ax.add_patch(PolygonPatch(self.shapes[k], fc='none', ec='red', lw=2))
                    else:
                        print('Field {} not found.'.format(' '.join(k)))
            # bulk
            if bulk:
                if only is None:
                    ax.set_xlim(self.xrange)
                    ax.set_ylim(self.yrange)
                    ax.set_xlabel('{}({})'.format(phase, expr))
                else:
                    ax.set_xlabel('{} - {}({})'.format(' '.join(only), phase, expr))
                # bulk composition
                if self.section_class.__name__ == 'PTsection':
                    ox, val = self.tc.bulk
                    table(ax=ax, cellText=[val], colLabels=ox, loc='top')
                else:
                    ox, val1, val2 = self.tc.bulk
                    table(ax=ax, cellText=[val1, val2], colLabels=ox, loc='top')
            else:
                if only is None:
                    ax.set_xlim(self.xrange)
                    ax.set_ylim(self.yrange)
                    ax.set_title('{}({})'.format(phase, expr))
                else:
                    ax.set_title('{} - {}({})'.format(' '.join(only), phase, expr))
            # coords
            ax.format_coord = self.format_coord
            # connect button press
            # cid = fig.canvas.mpl_connect('button_press_event', self.onclick)
            if filename is not None:
                plt.savefig(filename, **save_kw)
                plt.close(fig)
            else:
                if show:
                    plt.show()

    def isopleths_vector(self, phase, expr=None, **kwargs):
        """Method to draw vectorized compositional isopleths.

        Isopleths are drawn as lines for values evaluated from provided
        expression. Individual divariant fields are contoured separately, so
        final plot allows sharp changes accross univariant lines. Within
        divariant field the selected interpolation is used.

        Args:
            phase (str): Phase or end-member named
            expr (str): Expression to evaluate. It could use any variable
                existing for given phase. Check `all_data_keys` property for
                possible variables.
            N (int): Max number of contours. Default 10.
            step (int): Step between contour levels. If defined, N is ignored.
                Default None.
            cdf (bool): When True contour levels are percentile based.
                Default False.
            levels (list): User-defined contour levels. If defined, N and step
                is ignored.
            which (int): Bitopt defining from where data are collected. 0 bit -
                invariant points, 1 bit - uniariant lines and 2 bit - GridData
                points. Default 7 (all data)
            method: Interpolation method. Default is 'rbf', other option is
                'quadratic', which uses least-square fit to quadratic surface.
            rbf_func: Default 'thin_plate'. See scipy.interpolation.Rbf
            smooth (int): Values greater than zero increase the smoothness
                of the approximation. 0 is for interpolation (default),
                the function will always go through the nodal points.
            epsilon (int): Adjustable constant for gaussian or multiquadrics
                functions - defaults to approximate average distance between
                nodes (which is a good start).
            out (str or list): Highligt zero-mode lines for given phases.
            overlay (bool): Whether to show assemblage fields. Default True
            high (frozenset or list): Highlight divariant fields identified
                by key(s).
            cmap (str): matplotlib colormap used to divariant fields coloring.
                Colors are based on variance. Default 'viridis'.
            bulk (bool): Whether to show bulk composition on top of diagram.
                Default False.
            fig_kw: dict passed to subplots method.
            filename: If not None, figure is saved to file
            save_kw: dict passed to savefig method.
        """
        from skimage import measure
        from matplotlib.cm import ScalarMappable

        if self.check_phase_expr(phase, expr):
            # parse kwargs
            which = kwargs.get('which', 7)
            smooth = kwargs.get('smooth', 0)
            epsilon = kwargs.get('epsilon', None)
            filled = kwargs.get('filled', True)
            filled_over = kwargs.get('filled_over', False)
            out = kwargs.get('out', None)
            bulk = kwargs.get('bulk', False)
            high = kwargs.get('high', [])
            nosplit = kwargs.get('nosplit', False)
            step = kwargs.get('step', None)
            N = kwargs.get('N', 10)
            cdf = kwargs.get('cdf', False)
            overlay = kwargs.get('overlay', True)
            only = kwargs.get('only', None)
            refine = kwargs.get('refine', 1)
            method = kwargs.get('method', 'rbf')
            rbf_func = kwargs.get('rbf_func', 'thin_plate')
            cmap = kwargs.get('cmap', 'viridis')
            fig = kwargs.get('fig', None)
            fig_kw = kwargs.get('fig_kw', {})
            filename = kwargs.get('filename', None)
            save_kw = kwargs.get('save_kw', {})

            if not self.gridded:
                print('Collecting only from uni lines and inv points. Not yet gridded...')
            if isinstance(out, str):
                out = [out]
            if only is not None:
                recs = OrderedDict()
                d = self.collect_data(only, phase, expr, which=which)
                z = d['data']
                if z:
                    recs[only] = d
                    mn = min(z)
                    mx = max(z)
            else:
                recs, mn, mx = self.merge_data(phase, expr, which=which)
            mapper = ScalarMappable(norm=Normalize(vmin=mn, vmax=mx, clip=True), cmap=cmap)
            if step:
                cntv = np.arange(0, mx + step, step)
                cntv = cntv[cntv >= mn - step]
            else:
                if cdf:
                    dd = []
                    for key in recs:
                        dd.extend(recs[key]['data'])
                    cntv = np.percentile(dd, np.linspace(0, 100, N))
                else:
                    ml = ticker.MaxNLocator(nbins=N)
                    cntv = ml.tick_values(vmin=mn, vmax=mx)
            cntv = kwargs.get('levels', cntv)
            # Thin-plate contouring of areas
            if fig is None:
                show = True
                fig, ax = plt.subplots(**fig_kw)
            else:
                show = False
                ax = fig.add_subplot()
            for key in recs:
                phase_parts = phase.split(')')[0].split('(')
                if phase_parts[0] in key:
                    tmin, pmin, tmax, pmax = self.shapes[key].bounds
                    # ttspace = self.xspace[np.logical_and(self.xspace >= tmin - self.xstep, self.xspace <= tmax + self.xstep)]
                    # ppspace = self.yspace[np.logical_and(self.yspace >= pmin - self.ystep, self.yspace <= pmax + self.ystep)]
                    ttspace = np.arange(tmin - self.gridxstep, tmax + self.gridxstep, self.gridxstep / refine)
                    ppspace = np.arange(pmin - self.gridystep, pmax + self.gridystep, self.gridystep / refine)
                    tg, pg = np.meshgrid(ttspace, ppspace)
                    x, y = np.array(recs[key]['pts']).T
                    pts = recs[key]['pts']
                    data = recs[key]['data']
                    try:
                        if method == 'quadratic':
                            tgg = tg.flatten()
                            pgg = pg.flatten()
                            A = np.c_[np.ones_like(x), x, y, x * y, x**2, y**2]
                            C, _, _, _ = lstsq(A, data)
                            # evaluate it on a grid
                            zg = np.dot(np.c_[np.ones_like(tgg), tgg, pgg, tgg * pgg, tgg**2, pgg**2], C).reshape(
                                tg.shape
                            )
                        else:
                            rbf = Rbf(x, self.ratio * y, data, function=rbf_func, smooth=smooth, epsilon=epsilon)
                            zg = rbf(tg, self.ratio * pg)
                    except Exception as e:
                        if self.show_errors:
                            print(e)
                        zg = griddata(np.array(pts), data, (tg, pg), method='cubic', rescale=True)
                    # ------------
                    scx = (tmax - tmin + 2 * self.gridxstep) / zg.shape[1]
                    scy = (pmax - pmin + 2 * self.gridystep) / zg.shape[0]
                    lns = []
                    for v in cntv:
                        contours = measure.find_contours(zg, v)
                        for contour in contours:
                            cnt = np.array(
                                (
                                    contour[:, 1] * scx + tmin - self.gridxstep,
                                    contour[:, 0] * scy + pmin - self.gridystep,
                                )
                            ).T
                            lnc = LineString(cnt)
                            if self.shapes[key].intersects(lnc):
                                ln = self.shapes[key].intersection(lnc)
                                if ln.geom_type == 'MultiLineString':
                                    for lnp in ln.geoms:
                                        lnp = lnp.simplify(tolerance=0.01)
                                        x, y = np.array(lnp.coords).T
                                        ax.plot(x, y, color=mapper.to_rgba(v))
                                else:
                                    ln = ln.simplify(tolerance=0.01)
                                    x, y = np.array(ln.coords).T
                                    ax.plot(x, y, color=mapper.to_rgba(v))
            if only is None:
                if overlay:
                    self.add_overlay(ax)
                # zero mode lines
                if out:
                    for o in out:
                        xy = []
                        for ps in self.sections.values():
                            for uni in ps.unilines.values():
                                if o in uni.out:
                                    xy.append((uni.x, uni.y))
                                for poly in polymorphs:
                                    if poly.issubset(uni.phases):
                                        if o in poly:
                                            if poly.difference({o}).issubset(uni.out):
                                                xy.append((uni.x, uni.y))
                        if xy:
                            ax.plot(
                                np.hstack([(*seg[0], np.nan) for seg in xy]),
                                np.hstack([(*seg[1], np.nan) for seg in xy]),
                                lw=2,
                            )
            try:
                cbar = fig.colorbar(mapper)
                cbar.ax.set_yticks(cntv)
            except Exception as e:
                print('There is trouble to draw colorbar. Sorry.')
                if self.show_errors:
                    print(e)
            # Show highlight. Change to list if only single key
            if not isinstance(high, list):
                high = [high]
            if only is None:
                for k in high:
                    if isinstance(k, str):
                        k = frozenset(k.split())
                    k = k.union(self.tc.excess)
                    if k in self.shapes:
                        ax.add_patch(PolygonPatch(self.shapes[k], fc='none', ec='red', lw=2))
                    else:
                        print('Field {} not found.'.format(' '.join(k)))
            # bulk
            if bulk:
                if only is None:
                    ax.set_xlim(self.xrange)
                    ax.set_ylim(self.yrange)
                    ax.set_xlabel('{}({})'.format(phase, expr))
                else:
                    ax.set_xlabel('{} - {}({})'.format(' '.join(only), phase, expr))
                # bulk composition
                if self.section_class.__name__ == 'PTsection':
                    ox, val = self.tc.bulk
                    table(ax=ax, cellText=[val], colLabels=ox, loc='top')
                else:
                    ox, val1, val2 = self.tc.bulk
                    table(ax=ax, cellText=[val1, val2], colLabels=ox, loc='top')
            else:
                if only is None:
                    ax.set_xlim(self.xrange)
                    ax.set_ylim(self.yrange)
                    ax.set_title('{}({})'.format(phase, expr))
                else:
                    ax.set_title('{} - {}({})'.format(' '.join(only), phase, expr))
            # coords
            ax.format_coord = self.format_coord
            # connect button press
            # cid = fig.canvas.mpl_connect('button_press_event', self.onclick)
            if filename is not None:
                plt.savefig(filename, **save_kw)
                plt.close(fig)
            else:
                if show:
                    plt.show()

    def gendrawpd(self, export_areas=True):
        """Method to write drawpd file

        Args:
            export_areas (bool): Whether to include constructed areas. Default True.
        """
        with self.tc.drawpdfile.open('w', encoding=self.tc.TCenc) as output:
            output.write('% Generated by pypsbuilder (c) Ondrej Lexa 2020\n')
            output.write('2    % no. of variables in each line of data, in this case P, T\n')
            exc = frozenset.intersection(*self.keys)
            nc = frozenset.union(*self.keys)
            # ex.insert(0, '')
            output.write('{}'.format(len(nc) - len(exc)) + '\n')
            output.write('2 1  %% which columns to be x,y in phase diagram\n')
            output.write('\n')
            output.write('% Points\n')
            # global numbering
            all_points = dict()
            all_points_number = 0
            for ix, ps in self.sections.items():
                all_points[ix] = dict()
                for inv in ps.invpoints.values():
                    all_points_number += 1
                    all_points[ix][inv.id] = all_points_number
                    output.write('% ------------------------------\n')
                    output.write('i{}   {}\n'.format(all_points_number, inv.label(excess=ps.excess)))
                    output.write('\n')
                    output.write('{} {}\n'.format(inv._y, inv._x))
                    output.write('\n')
            output.write('% Lines\n')
            # global numbering
            all_lines = dict()
            all_lines_number = 0
            all_lines_topology = dict()
            for ix, ps in self.sections.items():
                all_lines[ix] = dict()
                for uni in ps.unilines.values():
                    all_lines_number += 1
                    all_lines[ix][uni.id] = all_lines_number
                    output.write('% ------------------------------\n')
                    output.write('u{}   {}\n'.format(all_lines_number, uni.label(excess=ps.excess)))
                    output.write('\n')
                    if uni.begin == 0:
                        b1 = 'begin'
                    else:
                        b1 = 'i{}'.format(all_points[ix][uni.begin])
                    if uni.end == 0:
                        b2 = 'end'
                    else:
                        b2 = 'i{}'.format(all_points[ix][uni.end])
                    all_lines_topology[all_lines_number] = uni
                    if uni.manual:
                        output.write('{} {} connect\n'.format(b1, b2))
                        output.write('\n')
                    else:
                        output.write('{} {}\n'.format(b1, b2))
                        output.write('\n')
                        for p, t in zip(uni.y, uni.x):
                            output.write('{} {}\n'.format(p, t))
                        output.write('\n')
            output.write('*\n')
            output.write('% ----------------------------------------------\n\n')
            if export_areas:
                output.write('% Areas\n')
                output.write('% ------------------------------\n')
                mxv, mnv = sys.float_info.min, sys.float_info.max
                for key in self.shapes:
                    if self.variance[key] < mnv:
                        mnv = self.variance[key]
                    if self.variance[key] > mxv:
                        mxv = self.variance[key]
                shades = np.linspace(1, 0, mxv - mnv + 3)[1:-1]  # exclude extreme values
                for key in self.shapes:
                    uids = [
                        all_lines[ix][uid]
                        for ix in self.unilists
                        if key in self.unilists[ix]
                        for uid in self.unilists[ix][key]
                        if uid in all_lines[ix]
                    ]
                    poly = linemerge([all_lines_topology[uid].shape() for uid in uids])
                    positions = [poly.project(Point(*all_lines_topology[uid].get_label_point())) for uid in uids]
                    orderix = sorted(range(len(positions)), key=lambda k: positions[k])
                    d = '{:.2f} {} % {}\n'.format(
                        shades[self.variance[key] - mnv],
                        ' '.join(['u{}'.format(uids[ix]) for ix in orderix]),
                        ' '.join(sorted(key)),
                    )
                    output.write(d)
            output.write('\n')
            output.write('*\n')
            output.write('\n')
            output.write('window {} {} {} {}\n\n'.format(*self.xrange, *self.yrange))
            output.write('darkcolour  56 16 101\n\n')
            dt = self.xrange[1] - self.xrange[0]
            dp = self.yrange[1] - self.yrange[0]
            ts = np.power(10, np.int(np.log10(dt)))
            ps = np.power(10, np.int(np.log10(dp)))
            tg = np.arange(0, self.xrange[1] + ts, ts)
            tg = tg[tg >= self.xrange[0]]
            pg = np.arange(0, self.yrange[1] + ps, ps)
            pg = pg[pg >= self.yrange[0]]
            output.write('bigticks {} {} {} {}\n\n'.format(tg[1] - tg[0], tg[0], pg[1] - pg[0], pg[0]))
            output.write('smallticks {} {}\n\n'.format((tg[1] - tg[0]) / 10, (pg[1] - pg[0]) / 10))
            output.write('numbering yes\n\n')
            if export_areas:
                output.write('doareas yes\n\n')
            output.write('*\n')
            print('Drawpd file generated successfully.')

        if self.tx.drexe is not None:
            if self.tc.rundr():
                print('Drawpd sucessfully executed.')
            else:
                print('Drawpd error!')

    def save_tab(self, comps, tabfile=None):
        """Export gridded values to Perple_X tab format. Could be used in pywerami.

        Note: Gridded values are interpolated from raw results

        Args:
            comps (list): List of (phase, expr) tuples.
                          phase (str): Phase or end-member named
                          expr (str): Expression to evaluate. It could use any
                                      variable existing for given phase. Check
                                      `all_data_keys` property for possible
                                      variables.
            tabfile (str): filename for tabfile. Default pseudosection name.tab
        """
        if not tabfile:
            tabfile = self.name + '.tab'
        data = []
        comps_labels = []
        for phase, expr in tqdm(comps, desc='Collecting data...'):
            data.append(self.get_gridded(phase, expr).flatten())
            comps_labels.append('{}({})'.format(phase, expr))
        with Path(tabfile).open('wb') as f:
            head = [
                'ptbuilder',
                self.name + '.tab',
                '{:12d}'.format(2),
                'T(°C)',
                '   {:16.16f}'.format(self.xrange[0])[:19],
                '   {:16.16f}'.format(self.xstep)[:19],
                '{:12d}'.format(len(self.xspace)),
                'p(kbar)',
                '   {:16.16f}'.format(self.yrange[0])[:19],
                '   {:16.16f}'.format(self.ystep)[:19],
                '{:12d}'.format(len(self.yspace)),
                '{:12d}'.format(len(data)),
                (len(data) * '{:15s}').format(*comps_labels),
            ]
            for ln in head:
                f.write(bytes(ln + '\n', 'utf-8'))
            np.savetxt(f, np.transpose(data), fmt='%15.6f', delimiter='')
        print('Saved.')

    def get_gridded(self, phase, expr=None, which=7, smooth=0):
        if self.gridded:
            if self.check_phase_expr(phase, expr):
                if not hasattr(self, 'masks'):
                    self.common_grid_and_masks()
                #  interpolate on common grid
                recs, mn, mx = self.merge_data(phase, expr, which=which)
                gd = np.empty(self.xg.shape)
                gd[:] = np.nan
                for key in recs:
                    xmin, ymin, xmax, ymax = self.shapes[key].bounds
                    xxind = np.logical_and(self.xspace >= xmin - self.xstep, self.xspace <= xmax + self.xstep)
                    yyind = np.logical_and(self.yspace >= ymin - self.ystep, self.yspace <= ymax + self.ystep)
                    slc = np.ix_(yyind, xxind)
                    tg, pg = self.xg[slc], self.yg[slc]
                    x, y = np.array(recs[key]['pts']).T
                    # Use scaling
                    rbf = Rbf(x, self.ratio * y, recs[key]['data'], function='linear', smooth=smooth)
                    zg = rbf(tg, self.ratio * pg)
                    gd[self.masks[key]] = zg[self.masks[key][slc]]
                return gd
        else:
            print('Not yet gridded...')

    def get_grids(self, phase, expr=None):
        """Convinient function to get dictionary of grids.

        Args:
            phase (str): Phase or end-member named
            expr (str): Expression to evaluate. It could use any variable
                existing for given phase. Check `all_data_keys` property for
                possible variables.
        """
        if self.gridded:
            if self.check_phase_expr(phase, expr):
                cgd = {}
                mn, mx = sys.float_info.max, -sys.float_info.max
                for ix, grid in self.grids.items():
                    gd = np.empty(grid.xg.shape)
                    gd[:] = np.nan
                    for key in grid.masks:
                        results = grid.gridcalcs[grid.masks[key] & (grid.status == 1)]
                        if len(results) > 0:
                            if phase in results[0].phases:
                                rows, cols = np.nonzero(grid.masks[key])
                                for r, c in zip(rows, cols):
                                    if grid.status[r, c] == 1:
                                        gd[r, c] = eval_expr(expr, grid.gridcalcs[r, c][phase])
                    cgd[ix] = gd
                return cgd


class PTPS(PS):
    """Class to postprocess ptbuilder project"""

    def __init__(self, *args, **kwargs):
        self.section_class = PTsection
        super(PTPS, self).__init__(*args, **kwargs)

    def calculate_composition(self, nx=50, ny=50):
        """Method to calculate compositional variations on grid.

        A compositions are calculated for stable assemblages in regular grid
        covering pT range of pseudosection. A stable assemblage is identified
        from constructed divariant fields. Results are stored in `grid` property
        as `GridData` instance. A property `all_data_keys` is updated.

        Before any grid point calculation, ptguesses are updated from nearest
        invariant point. If calculation fails, nearest solution from univariant
        line is used to update ptguesses. Finally, if solution is still not found,
        the method `fix_solutions` is called and neigbouring grid calculations are
        used to provide ptguess.

        Args:
            nx (int): Number of grid points along x direction (T)
            ny (int): Number of grid points along y direction (p)
        """
        axr = self.xrange
        ayr = self.yrange
        gpleft = 0
        for ix, ps in self.sections.items():
            paxr = ps.xrange
            payr = ps.yrange
            grid = GridData(
                ps,
                nx=round(nx * (paxr[1] - paxr[0]) / (axr[1] - axr[0])),
                ny=round(ny * (payr[1] - payr[0]) / (ayr[1] - ayr[0])),
            )
            last_inv = 0
            for (r, c) in tqdm(
                np.ndindex(grid.xg.shape),
                desc='Gridding {}/{}'.format(ix + 1, len(self.sections)),
                total=np.prod(grid.xg.shape),
            ):
                x, y = grid.xg[r, c], grid.yg[r, c]
                k = self.identify(x, y)
                if k is not None:
                    # update guesses from closest inv point
                    dst = sys.float_info.max
                    for id_inv, inv in ps.invpoints.items():
                        d2 = (inv._x - x) ** 2 + (inv._y - y) ** 2
                        if d2 < dst:
                            dst = d2
                            id_close = id_inv
                    if id_close != last_inv and not ps.invpoints[id_close].manual:
                        self.tc.update_scriptfile(guesses=ps.invpoints[id_close].ptguess())
                        last_inv = id_close
                    grid.status[r, c] = 0
                    start_time = time.time()
                    tcout, ans = self.tc.calc_assemblage(k.difference(self.tc.excess), y, x)
                    delta = time.time() - start_time
                    status, res, output = self.tc.parse_logfile()
                    if res is not None:
                        grid.gridcalcs[r, c] = res[0]
                        grid.status[r, c] = 1
                        grid.delta[r, c] = delta
                    else:
                        # update guesses from closest uni line point
                        dst = sys.float_info.max
                        for id_uni in self.unilists[ix][k]:
                            uni = ps.unilines[id_uni]
                            if not uni.manual:
                                for vix in list(range(len(uni._x))[uni.used]):
                                    d2 = (uni._x[vix] - x) ** 2 + (uni._y[vix] - y) ** 2
                                    if d2 < dst:
                                        dst = d2
                                        id_close = id_uni
                                        vix_close = vix
                        self.tc.update_scriptfile(guesses=ps.unilines[id_close].ptguess(idx=vix_close))
                        start_time = time.time()
                        tcout, ans = self.tc.calc_assemblage(k.difference(self.tc.excess), y, x)
                        delta = time.time() - start_time
                        status, res, output = self.tc.parse_logfile()
                        if res is not None:
                            grid.gridcalcs[r, c] = res[0]
                            grid.status[r, c] = 1
                            grid.delta[r, c] = delta
                        else:
                            grid.gridcalcs[r, c] = None
                            grid.status[r, c] = 0
                else:
                    grid.gridcalcs[r, c] = None
            print('Grid search done. {} empty points left.'.format(len(np.flatnonzero(grid.status == 0))))
            gpleft += len(np.flatnonzero(grid.status == 0))
            self.grids[ix] = grid
        if gpleft > 0:
            self.fix_solutions()
        self.create_masks()
        # save
        self.save()
        # update variable lookup table
        self.collect_all_data_keys()

    def fix_solutions(self):
        """Method try to find solution for grid points with failed status.

        Ptguesses are used from successfully calculated neighboring points until
        solution is find. Otherwise ststus remains failed.
        """
        if self.gridded:
            for ix, grid in self.grids.items():
                log = []
                ri, ci = np.nonzero(grid.status == 0)
                fixed, ftot = 0, len(ri)
                tq = trange(ftot, desc='Fix ({}/{})'.format(fixed, ftot))
                for ind in tq:
                    r, c = ri[ind], ci[ind]
                    x, y = grid.xg[r, c], grid.yg[r, c]
                    k = self.identify(x, y)
                    if k is not None:
                        # search already done grid neighs
                        for rn, cn in grid.neighs(r, c):
                            if grid.status[rn, cn] == 1:
                                self.tc.update_scriptfile(guesses=grid.gridcalcs[rn, cn].ptguess)
                                start_time = time.time()
                                tcout, ans = self.tc.calc_assemblage(k.difference(self.tc.excess), y, x)
                                delta = time.time() - start_time
                                status, res, output = self.tc.parse_logfile()
                                if res is not None:
                                    grid.gridcalcs[r, c] = res[0]
                                    grid.status[r, c] = 1
                                    grid.delta[r, c] = delta
                                    fixed += 1
                                    tq.set_description(desc='Fix ({}/{})'.format(fixed, ftot))
                                    break
                    if grid.status[r, c] == 0:
                        log.append('No solution find for {}, {}'.format(x, y))
                log.append('Fix done. {} empty grid points left.'.format(len(np.flatnonzero(grid.status == 0))))
                print('\n'.join(log))
        else:
            print('Not yet gridded...')

    def collect_ptpath(self, tpath, ppath, N=100, kind='quadratic'):
        """Method to collect THERMOCALC calculations along defined PT path.

        PT path is interpolated from provided points using defined method. For
        each point THERMOCALC seek for solution using ptguess from nearest
        `GridData` point.

        Args:
            tpath (numpy.array): 1D array of temperatures for given PT path
            ppath (numpy.array): 1D array of pressures for given PT path
            N (int): Number of calculation steps. Default 100.
            kind (str): Kind of interpolation. See scipy.interpolate.interp1d

        Returns:
            PTpath: returns instance of PTpath class storing all calculations
                along PT path.
        """
        if self.gridded:
            tpath, ppath = np.asarray(tpath), np.asarray(ppath)
            assert tpath.shape == ppath.shape, 'Shape of temperatures and pressures should be same.'
            assert tpath.ndim == 1, 'Temperatures and pressures should be 1D array like data.'
            gpath = np.arange(tpath.shape[0], dtype=float)
            gpath /= gpath[-1]
            if gpath.size < 3:
                kind = 'linear'
            splt = interp1d(gpath, tpath, kind=kind)
            splp = interp1d(gpath, ppath, kind=kind)
            err = 0
            points, results = [], []
            for step in tqdm(np.linspace(0, 1, N), desc='Calculating'):
                t, p = splt(step), splp(step)
                key = self.identify(t, p)
                ix = self.get_section_id(t, p)
                if ix is not None:
                    r, c = self.grids[ix].get_indexes(t, p)
                    calc = None
                    if self.grids[ix].status[r, c] == 1:
                        calc = self.grids[ix].gridcalcs[r, c]
                    else:
                        for rn, cn in self.grids[ix].neighs(r, c):
                            if self.grids[ix].status[rn, cn] == 1:
                                calc = self.grids[ix].gridcalcs[rn, cn]
                                break
                    if calc is not None:
                        self.tc.update_scriptfile(guesses=calc.ptguess)
                        tcout, ans = self.tc.calc_assemblage(key.difference(self.tc.excess), p, t)
                        status, res, output = self.tc.parse_logfile()
                        if res is not None:
                            points.append((t, p))
                            results.append(res[0])
                    else:
                        err += 1
            if err > 0:
                print('Solution not found on {} points'.format(err))
            return PTpath(points, results)
        else:
            print('Not yet gridded...')

    def show_path_data(self, ptpath, phase, expr=None, label=False, pathwidth=4, allpath=True, skiplabels=0, labelfs=6):
        """Show values of expression for given phase calculated along PTpath.

        It plots colored strip on PT space. Strips arenot drawn accross fields,
        where 'phase' is not present.

        Args:
            ptpath (PTpath): Results obtained by `collect_ptpath` method.
            phase (str): Phase or end-member named
            expr (str): Expression to evaluate. It could use any variable
                existing for given phase. Check `all_data_keys` property for
                possible variables.
            label (bool): Whether to label divariant fields. Default False.
            pathwidth (int): Width of colored strip. Default 4.
            allpath (bool): Whether to plot full PT path (dashed line).
        """
        if self.check_phase_expr(phase, expr):
            ex = ptpath.get_path_data(phase, expr)
            fig, ax = plt.subplots()
            if allpath:
                ax.plot(ptpath.t, ptpath.p, '--', color='grey', lw=1)
            # Create a continuous norm to map from data points to colors
            norm = Normalize(np.nanmin(ex), np.nanmax(ex))

            for s in np.ma.clump_unmasked(np.ma.masked_invalid(ex)):
                ts, ps, exs = ptpath.t[s], ptpath.p[s], ex[s]
                points = np.array([ts, ps]).T.reshape(-1, 1, 2)
                segments = np.concatenate([points[:-1], points[1:]], axis=1)
                lc = LineCollection(segments, cmap='viridis', norm=norm)
                # Set the values used for colormapping
                lc.set_array(exs)
                lc.set_linewidth(pathwidth)
                line = ax.add_collection(lc)
                self.add_overlay(ax, label=label, skiplabels=skiplabels, fontsize=labelfs)
            cbar = fig.colorbar(line, ax=ax)
            cbar.set_label('{}[{}]'.format(phase, expr))
            ax.set_xlim(self.xrange)
            ax.set_ylim(self.yrange)
            ax.set_title('PT path - {}'.format(self.name))
            plt.show()

    def show_path_modes(self, ptpath, exclude=[], cmap='tab20'):
        """Show stacked area diagram of phase modes along PT path

        Args:
            ptpath (PTpath): Results obtained by `collect_ptpath` method.
            exclude (list): List of phases to exclude. Included phases area
                normalized to 100%.
            cmap (str): matplotlib colormap. Default 'tab20'
        """
        if not isinstance(exclude, list):
            exclude = [exclude]
        steps = len(ptpath.t)
        nd = np.linspace(0, 1, steps)
        splt = interp1d(nd, ptpath.t, kind='quadratic')
        splp = interp1d(nd, ptpath.p, kind='quadratic')
        pset = set()
        for res in ptpath.results:
            for key in res.phases:
                if key not in exclude and 'mode' in res[key]:
                    pset.add(key)
        phases = sorted(list(pset))
        modes = np.array(
            [[res[phase]['mode'] if phase in res.phases else 0 for res in ptpath.results] for phase in phases]
        )
        modes = 100 * modes / modes.sum(axis=0)
        cm = plt.get_cmap(cmap)
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.set_prop_cycle(color=[cm(i / len(phases)) for i in range(len(phases))])
        bottom = np.zeros_like(modes[0])
        bars = []
        for n, mode in enumerate(modes):
            h = ax.bar(nd, mode, bottom=bottom, width=nd[1] - nd[0])
            bars.append(h[0])
            bottom += mode

        ax.format_coord = lambda x, y: 'T={:.2f} p={:.2f}'.format(splt(x), splp(x))
        ax.set_xlim(0, 1)
        ax.set_xlabel('Normalized distance along path')
        ax.set_ylabel('Mode [%]')
        box = ax.get_position()
        ax.set_position([box.x0, box.y0, box.width * 0.9, box.height])
        # Put a legend to the right of the current axis
        ax.legend(bars, phases, fancybox=True, loc='center left', bbox_to_anchor=(1.05, 0.5))
        plt.show()


class TXPS(PS):
    """Class to postprocess txbuilder project"""

    def __init__(self, *args, **kwargs):
        self.section_class = TXsection
        super(TXPS, self).__init__(*args, **kwargs)

    def calculate_composition(self, nx=50, ny=50):
        """Method to calculate compositional variations on grid.

        A compositions are calculated for stable assemblages in regular grid
        covering pT range of pseudosection. A stable assemblage is identified
        from constructed divariant fields. Results are stored in `grid` property
        as `GridData` instance. A property `all_data_keys` is updated.

        Before any grid point calculation, ptguesses are updated from nearest
        invariant point. If calculation fails, nearest solution from univariant
        line is used to update ptguesses. Finally, if solution is still not found,
        the method `fix_solutions` is called and neigbouring grid calculations are
        used to provide ptguess.

        Args:
            nx (int): Number of grid points along x direction (T)
            ny (int): Number of grid points along y direction (p)
        """
        axr = self.xrange
        ayr = self.yrange
        gpleft = 0
        for ix, ps in self.sections.items():
            paxr = ps.xrange
            payr = ps.yrange
            grid = GridData(
                ps,
                nx=round(nx * (paxr[1] - paxr[0]) / (axr[1] - axr[0])),
                ny=round(ny * (payr[1] - payr[0]) / (ayr[1] - ayr[0])),
            )
            last_inv = 0
            with tqdm(desc='Gridding {}/{}'.format(ix + 1, len(self.sections)), total=np.prod(grid.xg.shape)) as pbar:
                pm = (self.tc.prange[0] + self.tc.prange[1]) / 2
                for r in range(len(grid.yspace)):
                    for c in range(len(grid.xspace)):
                        x, y = grid.xg[r, c], grid.yg[r, c]
                        k = self.identify(x, y)
                        if k is not None:
                            # update guesses from closest inv point
                            dst = sys.float_info.max
                            for id_inv, inv in ps.invpoints.items():
                                d2 = (inv._x - x) ** 2 + (inv._y - y) ** 2
                                if d2 < dst:
                                    dst = d2
                                    id_close = id_inv
                            if id_close != last_inv and not ps.invpoints[id_close].manual:
                                self.tc.update_scriptfile(guesses=ps.invpoints[id_close].ptguess())
                                last_inv = id_close
                            grid.status[r, c] = 0
                            start_time = time.time()
                            tcout, ans = self.tc.calc_assemblage(k.difference(self.tc.excess), pm, x, onebulk=y)
                            delta = time.time() - start_time
                            status, res, output = self.tc.parse_logfile()
                            if res is not None:
                                grid.gridcalcs[r, c] = res[0]
                                grid.status[r, c] = 1
                                grid.delta[r, c] = delta
                            else:
                                # update guesses from closest uni line point
                                dst = sys.float_info.max
                                for id_uni in self.unilists[ix][k]:
                                    uni = ps.unilines[id_uni]
                                    if not uni.manual:
                                        for vix in list(range(len(uni._x))[uni.used]):
                                            d2 = (uni._x[vix] - x) ** 2 + (uni._y[vix] - y) ** 2
                                            if d2 < dst:
                                                dst = d2
                                                id_close = id_uni
                                                vix_close = vix
                                self.tc.update_scriptfile(guesses=ps.unilines[id_close].ptguess(idx=vix_close))
                                start_time = time.time()
                                tcout, ans = self.tc.calc_assemblage(k.difference(self.tc.excess), pm, x, onebulk=y)
                                delta = time.time() - start_time
                                status, res, output = self.tc.parse_logfile()
                                if res is not None:
                                    grid.gridcalcs[r, c] = res[0]
                                    grid.status[r, c] = 1
                                    grid.delta[r, c] = delta
                                else:
                                    grid.gridcalcs[r, c] = None
                                    grid.status[r, c] = 0
                        else:
                            grid.gridcalcs[r, c] = None
                        pbar.update(1)
            print('Grid search done. {} empty points left.'.format(len(np.flatnonzero(grid.status == 0))))
            gpleft += len(np.flatnonzero(grid.status == 0))
            self.grids[ix] = grid
        if gpleft > 0:
            self.fix_solutions()
        self.create_masks()
        # update variable lookup table
        self.collect_all_data_keys()
        # save
        self.save()

    def fix_solutions(self):
        """Method try to find solution for grid points with failed status.

        Ptguesses are used from successfully calculated neighboring points until
        solution is find. Otherwise ststus remains failed.
        """
        if self.gridded:
            for ix, grid in self.grids.items():
                log = []
                ri, ci = np.nonzero(grid.status == 0)
                fixed, ftot = 0, len(ri)
                pm = (self.tc.prange[0] + self.tc.prange[1]) / 2
                tq = trange(ftot, desc='Fix ({}/{})'.format(fixed, ftot))
                for ind in tq:
                    r, c = ri[ind], ci[ind]
                    x, y = grid.xg[r, c], grid.yg[r, c]
                    k = self.identify(x, y)
                    if k is not None:
                        # search already done grid neighs
                        for rn, cn in grid.neighs(r, c):
                            if grid.status[rn, cn] == 1:
                                self.tc.update_scriptfile(guesses=grid.gridcalcs[rn, cn]['ptguess'])
                                start_time = time.time()
                                tcout, ans = self.tc.calc_assemblage(k.difference(self.tc.excess), pm, x, onebulk=y)
                                delta = time.time() - start_time
                                status, res, output = self.tc.parse_logfile()
                                if res is not None:
                                    grid.gridcalcs[r, c] = res[0]
                                    grid.status[r, c] = 1
                                    grid.delta[r, c] = delta
                                    fixed += 1
                                    tq.set_description(desc='Fix ({}/{})'.format(fixed, ftot))
                                    break
                    if grid.status[r, c] == 0:
                        log.append('No solution find for {}, {}'.format(x, y))
                log.append('Fix done. {} empty grid points left.'.format(len(np.flatnonzero(grid.status == 0))))
                print('\n'.join(log))
        else:
            print('Not yet gridded...')


class PXPS(PS):
    """Class to postprocess pxbuilder project"""

    def __init__(self, *args, **kwargs):
        self.section_class = PXsection
        super(PXPS, self).__init__(*args, **kwargs)

    def calculate_composition(self, nx=50, ny=50):
        """Method to calculate compositional variations on grid.

        A compositions are calculated for stable assemblages in regular grid
        covering pT range of pseudosection. A stable assemblage is identified
        from constructed divariant fields. Results are stored in `grid` property
        as `GridData` instance. A property `all_data_keys` is updated.

        Before any grid point calculation, ptguesses are updated from nearest
        invariant point. If calculation fails, nearest solution from univariant
        line is used to update ptguesses. Finally, if solution is still not found,
        the method `fix_solutions` is called and neigbouring grid calculations are
        used to provide ptguess.

        Args:
            nx (int): Number of grid points along x direction (T)
            ny (int): Number of grid points along y direction (p)
        """
        axr = self.xrange
        ayr = self.yrange
        gpleft = 0
        for ix, ps in self.sections.items():
            paxr = ps.xrange
            payr = ps.yrange
            grid = GridData(
                ps,
                nx=round(nx * (paxr[1] - paxr[0]) / (axr[1] - axr[0])),
                ny=round(ny * (payr[1] - payr[0]) / (ayr[1] - ayr[0])),
            )
            last_inv = 0
            with tqdm(desc='Gridding', total=np.prod(grid.xg.shape)) as pbar:
                tm = (self.tc.trange[0] + self.tc.trange[1]) / 2
                for c in range(len(grid.xspace)):
                    for r in range(len(grid.yspace)):
                        x, y = grid.xg[r, c], grid.yg[r, c]
                        k = self.identify(x, y)
                        if k is not None:
                            # update guesses from closest inv point
                            dst = sys.float_info.max
                            for id_inv, inv in ps.invpoints.items():
                                d2 = (inv._x - x) ** 2 + (inv._y - y) ** 2
                                if d2 < dst:
                                    dst = d2
                                    id_close = id_inv
                            if id_close != last_inv and not ps.invpoints[id_close].manual:
                                self.tc.update_scriptfile(guesses=ps.invpoints[id_close].ptguess())
                                last_inv = id_close
                            grid.status[r, c] = 0
                            start_time = time.time()
                            tcout, ans = self.tc.calc_assemblage(k.difference(self.tc.excess), y, tm, onebulk=x)
                            delta = time.time() - start_time
                            status, res, output = self.tc.parse_logfile()
                            if res is not None:
                                grid.gridcalcs[r, c] = res[0]
                                grid.status[r, c] = 1
                                grid.delta[r, c] = delta
                            else:
                                # update guesses from closest uni line point
                                dst = sys.float_info.max
                                for id_uni in self.unilists[ix][k]:
                                    uni = ps.unilines[id_uni]
                                    if not uni.manual:
                                        for vix in list(range(len(uni._x))[uni.used]):
                                            d2 = (uni._x[vix] - x) ** 2 + (uni._y[vix] - y) ** 2
                                            if d2 < dst:
                                                dst = d2
                                                id_close = id_uni
                                                vix_close = vix
                                self.tc.update_scriptfile(guesses=ps.unilines[id_close].ptguess(idx=vix_close))
                                start_time = time.time()
                                tcout, ans = self.tc.calc_assemblage(k.difference(self.tc.excess), y, tm, onebulk=x)
                                delta = time.time() - start_time
                                status, res, output = self.tc.parse_logfile()
                                if res is not None:
                                    grid.gridcalcs[r, c] = res[0]
                                    grid.status[r, c] = 1
                                    grid.delta[r, c] = delta
                                else:
                                    grid.gridcalcs[r, c] = None
                                    grid.status[r, c] = 0
                        else:
                            grid.gridcalcs[r, c] = None
                        pbar.update(1)
            print('Grid search done. {} empty points left.'.format(len(np.flatnonzero(grid.status == 0))))
            gpleft += len(np.flatnonzero(grid.status == 0))
            self.grids[ix] = grid
        if gpleft > 0:
            self.fix_solutions()
        self.create_masks()
        # update variable lookup table
        self.collect_all_data_keys()
        # save
        self.save()

    def fix_solutions(self):
        """Method try to find solution for grid points with failed status.

        Ptguesses are used from successfully calculated neighboring points until
        solution is find. Otherwise ststus remains failed.
        """
        if self.gridded:
            for ix, grid in self.grids.items():
                log = []
                ri, ci = np.nonzero(grid.status == 0)
                fixed, ftot = 0, len(ri)
                tm = (self.tc.trange[0] + self.tc.trange[1]) / 2
                tq = trange(ftot, desc='Fix ({}/{})'.format(fixed, ftot))
                for ind in tq:
                    r, c = ri[ind], ci[ind]
                    x, y = grid.xg[r, c], grid.yg[r, c]
                    k = self.identify(x, y)
                    if k is not None:
                        # search already done grid neighs
                        for rn, cn in grid.neighs(r, c):
                            if grid.status[rn, cn] == 1:
                                start_time = time.time()
                                tcout, ans = self.tc.calc_assemblage(k.difference(self.tc.excess), y, tm, onebulk=x)
                                delta = time.time() - start_time
                                status, res, output = self.tc.parse_logfile()
                                if res is not None:
                                    grid.gridcalcs[r, c] = res[0]
                                    grid.status[r, c] = 1
                                    grid.delta[r, c] = delta
                                    fixed += 1
                                    tq.set_description(desc='Fix ({}/{})'.format(fixed, ftot))
                                    break
                    if grid.status[r, c] == 0:
                        log.append('No solution find for {}, {}'.format(x, y))
                log.append('Fix done. {} empty grid points left.'.format(len(np.flatnonzero(grid.status == 0))))
                print('\n'.join(log))
        else:
            print('Not yet gridded...')


class GridData:
    """Class to store gridded calculations.

    Attributes:
        xspace (numpy.array): Array of x coordinates used for gridding
        yspace (numpy.array): Array of y coordinates used for gridding
        gridcalcs (numpy.array): 2D array of THERMOCALC Results
        status (numpy.array): 2D array indicating status of calculation. The
            values are 1 - OK, 0 - Failed, NaN - not calculated (outside of any
            divariant field)
        delta (numpy.array): 2D array of time needed for THERMOCALC calculation
        masks (dict): Dictionaty associating divariant field key (frozenset) and
            binary mask for `gridcalcs`, `status` and `delta` arrays. Masks are
            used to retrieve results for individual divariant fields.

    """

    def __init__(self, ps, nx, ny):
        dx = (ps.xrange[1] - ps.xrange[0]) / nx
        self.xspace = np.linspace(ps.xrange[0] + dx / 2, ps.xrange[1] - dx / 2, nx)
        dy = (ps.yrange[1] - ps.yrange[0]) / ny
        self.yspace = np.linspace(ps.yrange[0] + dy / 2, ps.yrange[1] - dy / 2, ny)
        self.xg, self.yg = np.meshgrid(self.xspace, self.yspace)
        self.gridcalcs = np.empty(self.xg.shape, np.dtype(object))
        self.status = np.empty(self.xg.shape)
        self.status[:] = np.nan
        self.delta = np.empty(self.xg.shape)
        self.delta[:] = np.nan
        self.masks = OrderedDict()

    def __repr__(self):
        tmpl = 'Grid {}x{} with ok/failed/none solutions {}/{}/{}'
        ok = len(np.flatnonzero(self.status == 1))
        fail = len(np.flatnonzero(self.status == 0))
        return tmpl.format(len(self.xspace), len(self.yspace), ok, fail, np.prod(self.xg.shape) - ok - fail)

    def get_indexes(self, x, y):
        """Return row and column index tuple of nearest grid point

        Args:
            x (float): x-coordinate of point
            y (float): y-coordiante of point

        """
        c = np.searchsorted(self.xspace, x)
        r = np.searchsorted(self.yspace, y)
        return r, c

    def contains(self, x, y):
        xmin, xmax, ymin, ymax = self.extent
        return (x >= xmin) & (x < xmax) & (y >= ymin) & (y < ymax)

    def neighs(self, r, c):
        """Returns list of row, column tuples of neighbouring points on grid.

        Args:
            r (int): Row index
            c (int): Column index
        """
        m = np.array(
            [
                [(r - 1, c - 1), (r - 1, c), (r - 1, c + 1)],
                [(r, c - 1), (None, None), (r, c + 1)],
                [(r + 1, c - 1), (r + 1, c), (r + 1, c + 1)],
            ]
        )
        if r < 1:
            m = m[1:, :]
        if r > len(self.yspace) - 2:
            m = m[:-1, :]
        if c < 1:
            m = m[:, 1:]
        if c > len(self.xspace) - 2:
            m = m[:, :-1]
        return zip([i for i in m[:, :, 0].flat if i is not None], [i for i in m[:, :, 1].flat if i is not None])

    @property
    def xstep(self):
        """Returns spacing along temperature axis"""
        return self.xspace[1] - self.xspace[0]

    @property
    def ystep(self):
        """Returns spacing along pressure axis"""
        return self.yspace[1] - self.yspace[0]

    @property
    def extent(self):
        """Returns extend of grid (Note that grid is cell centered)"""
        return (
            self.xspace[0] - self.xstep / 2,
            self.xspace[-1] + self.xstep / 2,
            self.yspace[0] - self.ystep / 2,
            self.yspace[-1] + self.ystep / 2,
        )


class PTpath:
    """Class to store THERMOCALC calculations along PT paths.

    Attributes:
        t (numpy.array): 1D array of temperatures.
        p (numpy.array): 1D array of pressures.
        results (list): List of THERMOCALC results dictionaries.
    """

    def __init__(self, points, results):
        self.t, self.p = np.array(points).T
        self.results = results

    def get_path_data(self, phase, expr):
        ex = np.array([eval_expr(expr, res[phase]) if phase in res.phases else np.nan for res in self.results])
        return ex


def eval_expr(expr, dt):
    """Evaluate expression using THERMOCALC output variables.

    Args:
        expr (str): expression to be evaluated
        dt (dict): dictionary of all available variables and their values

    Returns:
        float: value evaluated from epxression

    Example:
        >>> ps = pt.sections[0]
        >>> eval_expr('mode', ps.invpoints[5].results['g'])
        0.02496698
        >>> eval_expr('xMgX/(xFeX+xMgX)', ps.invpoints[5].results['g'])
        0.12584215591915301
    """

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

    ops = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply, ast.Div: np.divide, ast.Pow: np.power}
    return eval_(ast.parse(expr, mode='eval').body)


explorers = {'.ptb': PTPS, '.txb': TXPS, '.pxb': PXPS}


def ps_show():
    parser = argparse.ArgumentParser(description='Draw pseudosection from project file')
    parser.add_argument('project', type=str, nargs='+', help='builder project file(s)')
    parser.add_argument('-o', '--out', nargs='+', help='highlight out lines for given phases')
    parser.add_argument('-l', '--label', action='store_true', help='show area labels')
    parser.add_argument('--origwd', action='store_true', help='use stored original working directory')
    parser.add_argument('-b', '--bulk', action='store_true', help='show bulk composition on figure')
    parser.add_argument('--cmap', type=str, default='Purples', help='name of the colormap')
    parser.add_argument('--alpha', type=float, default=0.6, help='alpha of colormap')
    parser.add_argument('--connect', action='store_true', help='whether mouse click echo stable assemblage')
    parser.add_argument('--high', action='append', default=[], help='highlight field defined by set of phases')
    parser.add_argument('--tolerance', type=float, default=None, help='tolerance to simplify univariant lines')
    args = parser.parse_args()
    PSOK = explorers.get(Path(args.project[0]).suffix, None)
    if PSOK is not None:
        ps = PSOK(*args.project, tolerance=args.tolerance, origwd=args.origwd)
        sys.exit(
            ps.show(
                out=args.out,
                label=args.label,
                bulk=args.bulk,
                high=args.high,
                cmap=args.cmap,
                alpha=args.alpha,
                connect=args.connect,
            )
        )
    else:
        print('Project file not recognized...')
        sys.exit(1)


def ps_grid():
    parser = argparse.ArgumentParser(description='Calculate compositions in grid')
    parser.add_argument('project', type=str, nargs='+', help='builder project file(s)')
    parser.add_argument('--nx', type=int, default=50, help='number of T steps')
    parser.add_argument('--ny', type=int, default=50, help='number of P steps')
    parser.add_argument('--origwd', action='store_true', help='use stored original working directory')
    parser.add_argument('--tolerance', type=float, default=None, help='tolerance to simplify univariant lines')
    args = parser.parse_args()
    PSOK = explorers.get(Path(args.project[0]).suffix, None)
    if PSOK is not None:
        ps = PSOK(*args.project, tolerance=args.tolerance, origwd=args.origwd)
        sys.exit(ps.calculate_composition(nx=args.nx, ny=args.ny))
    else:
        print('Project file not recognized...')
        sys.exit(1)


def ps_iso():
    parser = argparse.ArgumentParser(description='Draw isopleth diagrams')
    parser.add_argument('project', type=str, nargs='+', help='builder project file(s)')
    parser.add_argument('phase', type=str, help='phase used for contouring')
    parser.add_argument('-e', '--expr', type=str, default=None, help='expression evaluated to calculate values')
    parser.add_argument('-f', '--filled', action='store_true', help='filled contours', default=False)
    parser.add_argument('--origwd', action='store_true', help='use stored original working directory')
    parser.add_argument('-o', '--out', nargs='+', help='highlight out lines for given phases')
    parser.add_argument(
        '--nosplit', action='store_true', help='controls whether the underlying contour is removed or not'
    )
    parser.add_argument('-b', '--bulk', action='store_true', help='show bulk composition on figure')
    parser.add_argument('--step', type=float, default=None, help='contour step')
    parser.add_argument('--ncont', type=int, default=10, help='number of contours')
    parser.add_argument('--colors', type=str, default=None, help='color for all levels')
    parser.add_argument('--cmap', type=str, default=None, help='name of the colormap')
    parser.add_argument('--smooth', type=float, default=0, help='smoothness of the approximation')
    parser.add_argument(
        '--labelkey', action='append', default=[], help='label contours in field defined by set of phases'
    )
    parser.add_argument('--high', action='append', default=[], help='highlight field defined by set of phases')
    parser.add_argument('--tolerance', type=float, default=None, help='tolerance to simplify univariant lines')
    args = parser.parse_args()
    PSOK = explorers.get(Path(args.project[0]).suffix, None)
    if PSOK is not None:
        ps = PSOK(*args.project, tolerance=args.tolerance, origwd=args.origwd)
        sys.exit(
            ps.isopleths(
                args.phase,
                expr=args.expr,
                filled=args.filled,
                smooth=args.smooth,
                step=args.step,
                bulk=args.bulk,
                N=args.ncont,
                labelkeys=args.labelkey,
                nosplit=args.nosplit,
                colors=args.colors,
                cmap=args.cmap,
                out=args.out,
                high=args.high,
            )
        )
    else:
        print('Project file not recognized...')
        sys.exit(1)


def ps_drawpd():
    parser = argparse.ArgumentParser(description='Generate drawpd file from project')
    parser.add_argument('project', type=str, nargs='+', help='psbuilder project file(s)')
    parser.add_argument('-a', '--areas', action='store_true', help='export also areas', default=True)
    parser.add_argument('--origwd', action='store_true', help='use stored original working directory')
    parser.add_argument('--tolerance', type=float, default=None, help='tolerance to simplify univariant lines')
    args = parser.parse_args()
    PSOK = explorers.get(Path(args.project[0]).suffix, None)
    if PSOK is not None:
        ps = PSOK(*args.project, tolerance=args.tolerance, origwd=args.origwd)
        sys.exit(ps.gendrawpd(export_areas=args.areas))
    else:
        print('Project file not recognized...')
        sys.exit(1)
