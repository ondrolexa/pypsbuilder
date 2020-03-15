"""
Visual pseudosection explorer for THERMOCALC
"""
# author: Ondrej Lexa
# website: petrol.natur.cuni.cz/~ondro

import argparse
import sys
import os
try:
    import cPickle as pickle
except ImportError:
    import pickle
import gzip
import ast
import time
import re
from pathlib import Path
from collections import OrderedDict

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.collections import LineCollection
from matplotlib.colorbar import ColorbarBase
from mpl_toolkits.axes_grid1 import make_axes_locatable

from shapely.geometry import MultiPoint, Point
from descartes import PolygonPatch
from scipy.interpolate import Rbf
from scipy.interpolate import interp1d
from tqdm import tqdm, trange

from .psclasses import TCAPI, InvPoint, UniLine, PTsection, PTsection, polymorphs


class GridData:
    def __init__(self, ps, nx, ny):
        dx = (ps.xrange[1] - ps.xrange[0]) / nx
        self.tspace = np.linspace(ps.xrange[0] + dx/2, ps.xrange[1] - dx/2, nx)
        dy = (ps.yrange[1] - ps.yrange[0]) / ny
        self.pspace = np.linspace(ps.yrange[0] + dy/2, ps.yrange[1] - dy/2, ny)
        self.tg, self.pg = np.meshgrid(self.tspace, self.pspace)
        self.gridcalcs = np.empty(self.tg.shape, np.dtype(object))
        self.status = np.empty(self.tg.shape)
        self.status[:] = np.nan
        self.delta = np.empty(self.tg.shape)
        self.delta[:] = np.nan
        self.masks = OrderedDict()

    def __repr__(self):
        tmpl = 'Grid {}x{} with ok/failed/none solutions {}/{}/{}'
        ok = len(np.flatnonzero(self.status == 1))
        fail = len(np.flatnonzero(self.status == 0))
        return tmpl.format(len(self.tspace), len(self.pspace),
                           ok, fail, np.prod(self.tg.shape) - ok - fail)

    def neighs(self, r, c):
        m = np.array([[(r - 1, c - 1), (r - 1, c), (r - 1, c + 1)],
                      [(r, c - 1), (None, None), (r, c + 1)],
                      [(r + 1, c - 1), (r + 1, c), (r + 1, c + 1)]])
        if r < 1:
            m = m[1:, :]
        if r > len(self.pspace) - 2:
            m = m[:-1, :]
        if c < 1:
            m = m[:, 1:]
        if c > len(self.tspace) - 2:
            m = m[:, :-1]
        return zip([i for i in m[:, :, 0].flat if i is not None],
                   [i for i in m[:, :, 1].flat if i is not None])

    @property
    def tstep(self):
        return self.tspace[1] - self.tspace[0]

    @property
    def pstep(self):
        return self.pspace[1] - self.pspace[0]

    @property
    def extent(self):
        return (self.tspace[0] - self.tstep / 2, self.tspace[-1] + self.tstep / 2,
                self.pspace[0] - self.pstep / 2, self.pspace[-1] + self.pstep / 2)


class PTpath:
    def __init__(self, points, results):
        self.t, self.p = np.array(points).T
        self.results = results

    def get_path_data(self, phase, expr):
        ex = np.array([eval_expr(expr, res['data'][phase]) if phase in res['data'] else np.nan for res in self.results])
        return ex


class PTPS:
    def __init__(self, projfile):
        self.projfile = Path(projfile).resolve()
        if self.projfile.exists():
            with gzip.open(str(self.projfile), 'rb') as stream:
                data = pickle.load(stream)
            # check
            if not 'workdir' in data:
                data['workdir'] = self.projfile.parent
            self.ps = data['section']
            tc = TCAPI(data['workdir'])
            if tc.OK:
                self.tc = tc
                self.shapes, self.edges, self.bad_shapes, self.ignored_shapes, log = self.ps.create_shapes()
                print(' '.join(log))
                if 'variance' in data:
                    self.variance = data['variance']
                else:
                    # calculate variance
                    self.variance = {}
                    for key in self.shapes:
                        ans = '{}\nkill\n\n'.format(' '.join(key))
                        tcout = self.tc.runtc(ans)
                        for ln in tcout.splitlines():
                            if 'variance of required equilibrium' in ln:
                                break
                        self.variance[key] = int(ln[ln.index('(') + 1:ln.index('?')])
                # already gridded?
                if 'grid' in data:
                    self.grid = data['grid']
                # update variable lookup table
                self.collect_all_data_keys()
            else:
                raise Exception('Error during initialization of THERMOCALC in {}\n{}'.format(data['workdir'], tc.status))
        else:
            raise Exception('File {} does not exists.'.format(self.projfile))

    def __iter__(self):
        return iter(self.shapes)

    def __repr__(self):
        reprs = [repr(self.tc), repr(self.ps)]
        reprs.append('Areas: {}'.format(len(self.shapes)))
        if self.gridded:
            reprs.append(repr(self.grid))
        return '\n'.join(reprs)

    @property
    def name(self):
        return self.projfile.stem

    @property
    def gridded(self):
        return hasattr(self, 'grid')

    @property
    def phases(self):
        return {phase for key in self for phase in key}

    @property
    def keys(self):
        return list(self.shapes.keys())

    def invs_from_edges(self, edges):
        return {self.ps.unilines[ed].begin for ed in edges}.union({self.ps.unilines[ed].end for ed in edges}).difference({0})

    def save(self): # TODO:
        if self.gridded:
            # put to dict
            # put to dict
            with gzip.open(str(self.projfile), 'rb') as stream:
                data = pickle.load(stream)
            data['shapes'] = self.shapes
            data['edges'] = self.edges
            data['bad_shapes'] = self.bad_shapes
            data['ignored_shapes'] = self.ignored_shapes
            data['variance'] = self.variance
            data['grid'] = self.grid
            # do save
            with gzip.open(str(self.projfile), 'wb') as stream:
                pickle.dump(data, stream)

    def calculate_composition(self, nx=50, ny=50):
        grid = GridData(self.ps, nx=nx, ny=ny)
        last_inv = 0
        for (r, c) in tqdm(np.ndindex(grid.tg.shape), desc='Gridding', total=np.prod(grid.tg.shape)):
            x, y = grid.tg[r, c], grid.pg[r, c]
            k = self.identify(x, y)
            if k is not None:
                # update guesses from closest inv point
                dst = sys.float_info.max
                for id_inv, inv in self.ps.invpoints.items():
                    d2 = (inv._x - x)**2 + (inv._y - y)**2
                    if d2 < dst:
                        dst = d2
                        id_close = id_inv
                if id_close != last_inv:
                    self.tc.update_scriptfile(guesses=self.ps.invpoints[id_close].ptguess())
                    last_inv = id_close
                grid.status[r, c] = 0
                start_time = time.time()
                tcout, ans = self.tc.calc_assemblage(k.difference(self.tc.excess), y, x)
                delta = time.time() - start_time
                status, variance, pts, res, output = self.tc.parse_logfile()
                if len(res) == 1:
                    grid.gridcalcs[r, c] = res[0]
                    grid.status[r, c] = 1
                    grid.delta[r, c] = delta
                else:
                    # update guesses from closest uni line point
                    dst = sys.float_info.max
                    for id_uni in self.edges[k]:
                        uni = self.ps.unilines[id_uni]
                        for ix in list(range(len(uni._x))[uni.used]):
                            d2 = (uni._x[ix] - x)**2 + (uni._y[ix] - y)**2
                            if d2 < dst:
                                dst = d2
                                id_close = id_uni
                                idix = ix
                    self.tc.update_scriptfile(guesses=self.ps.unilines[id_close].ptguess(idx=idix))
                    start_time = time.time()
                    tcout, ans = self.tc.calc_assemblage(k.difference(self.tc.excess), y, x)
                    delta = time.time() - start_time
                    status, variance, pts, res, output = self.tc.parse_logfile()
                    if len(res) == 1:
                        grid.gridcalcs[r, c] = res[0]
                        grid.status[r, c] = 1
                        grid.delta[r, c] = delta
                    else:
                        grid.gridcalcs[r, c] = None
                        grid.status[r, c] = 0
            else:
                grid.gridcalcs[r, c] = None
        print('Grid search done. {} empty grid points left.'.format(len(np.flatnonzero(grid.status == 0))))
        self.grid = grid
        self.fix_solutions()
        self.create_masks()
        # update variable lookup table
        self.collect_all_data_keys()
        # save
        self.save()

    def fix_solutions(self):
        if self.gridded:
            ri, ci = np.nonzero(self.grid.status == 0)
            fixed, ftot = 0, len(ri)
            tq = trange(ftot, desc='Fix ({}/{})'.format(fixed, ftot))
            for ind in tq:
                r, c = ri[ind], ci[ind]
                x, y = self.grid.tg[r, c], self.grid.pg[r, c]
                k = self.identify(x, y)
                if k is not None:
                    # search already done grid neighs
                    for rn, cn in self.grid.neighs(r, c):
                        if self.grid.status[rn, cn] == 1:
                            self.tc.update_scriptfile(guesses=self.grid.gridcalcs[rn, cn]['ptguess'])
                            start_time = time.time()
                            tcout, ans = self.tc.calc_assemblage(k.difference(self.tc.excess), y, x)
                            delta = time.time() - start_time
                            status, variance, pts, res, output = self.tc.parse_logfile()
                            if len(res) == 1:
                                self.grid.gridcalcs[r, c] = res[0]
                                self.grid.status[r, c] = 1
                                self.grid.delta[r, c] = delta
                                fixed += 1
                                tq.set_description(desc='Fix ({}/{})'.format(fixed, ftot))
                                break
                if self.grid.status[r, c] == 0:
                    tqdm.write('No solution find for {}, {}'.format(x, y))
            print('Fix done. {} empty grid points left.'.format(len(np.flatnonzero(self.grid.status == 0))))

    def create_masks(self):
        if self.gridded:
            # Create data masks
            points = MultiPoint(list(zip(self.grid.tg.flatten(), self.grid.pg.flatten())))
            for key in tqdm(self, desc='Masking', total=len(self.shapes)):
                self.grid.masks[key] = np.array(list(map(self.shapes[key].contains, points))).reshape(self.grid.tg.shape)

    def collect_all_data_keys(self):
        data = dict()
        if self.gridded:
            for key in self:
                res = self.grid.gridcalcs[self.grid.masks[key]]
                if len(res) > 0:
                    for k in res[0]['data'].keys():
                        data[k] = list(res[0]['data'][k].keys())
        self.all_data_keys = data

    def collect_inv_data(self, key, phase, expr):
        dt = dict(pts=[], data=[])
        for id_inv in self.invs_from_edges(self.edges[key]):
            inv = self.ps.invpoints[id_inv]
            if not inv.manual:
                if phase in inv.results[0]['data']:
                    dt['pts'].append((inv._x, inv._y))
                    dt['data'].append(eval_expr(expr, inv.results[0]['data'][phase]))
        return dt

    def collect_edges_data(self, key, phase, expr):
        dt = dict(pts=[], data=[])
        for id_uni in self.edges[key]:
            uni = self.ps.unilines[id_uni]
            if not uni.manual:
                if phase in uni.results[uni.midix]['data']:
                    edt = zip(uni._x[uni.used],
                              uni._y[uni.used],
                              uni.results[uni.used],)
                    for x, y, res in edt:
                        dt['pts'].append((x, y))
                        dt['data'].append(eval_expr(expr, res['data'][phase]))
        return dt

    def collect_grid_data(self, key, phase, expr):
        dt = dict(pts=[], data=[])
        if self.gridded:
            results = self.grid.gridcalcs[self.grid.masks[key]]
            if len(results) > 0:
                if phase in results[0]['data']:
                    gdt = zip(self.grid.tg[self.grid.masks[key]],
                              self.grid.pg[self.grid.masks[key]],
                              results,
                              self.grid.status[self.grid.masks[key]])
                    for x, y, res, ok in gdt:
                        if ok == 1:
                            dt['pts'].append((x, y))
                            dt['data'].append(eval_expr(expr, res['data'][phase]))
        return dt

    def collect_data(self, key, phase, expr, which=7):
        dt = dict(pts=[], data=[])
        # check if phase or end-member is in assemblage
        if re.sub('[\(].*?[\)]', '', phase) in key:
            if which & (1 << 0):
                d = self.collect_inv_data(key, phase, expr)
                dt['pts'].extend(d['pts'])
                dt['data'].extend(d['data'])
            if which & (1 << 1):
                d = self.collect_edges_data(key, phase, expr)
                dt['pts'].extend(d['pts'])
                dt['data'].extend(d['data'])
            if which & (1 << 2):
                d = self.collect_grid_data(key, phase, expr)
                dt['pts'].extend(d['pts'])
                dt['data'].extend(d['data'])
        return dt

    def merge_data(self, phase, expr, which=7):
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

    def collect_ptpath(self, tpath, ppath, N=100, kind = 'quadratic'): # TODO:
        if self.gridded:
            tpath, ppath = np.asarray(tpath), np.asarray(ppath)
            assert tpath.shape == ppath.shape, 'Shape of temperatures and pressures should be same.'
            assert tpath.ndim == 1, 'Temperatures and pressures should be 1D array like data.'
            gpath = np.arange(tpath.shape[0], dtype=float)
            gpath /= gpath[-1]
            splt = interp1d(gpath, tpath, kind=kind)
            splp = interp1d(gpath, ppath, kind=kind)
            err = 0
            points, results = [], []
            for step in tqdm(np.linspace(0, 1, N), desc='Calculating'):
                t, p = splt(step), splp(step)
                key = self.identify(t, p)
                mask = self.grid.masks[key]
                dst = (t - self.grid.tg)**2 + (self.ps.ratio * (p - self.grid.pg))**2
                dst[~mask] = np.nan
                r, c = np.unravel_index(np.nanargmin(dst), self.grid.tg.shape)
                calc = None
                if self.grid.status[r, c] == 1:
                    calc = self.grid.gridcalcs[r, c]
                else:
                    for rn, cn in self.grid.neighs(r, c):
                        if self.grid.status[rn, cn] == 1:
                            calc = self.grid.gridcalcs[rn, cn]
                            break
                if calc is not None:
                    self.tc.update_scriptfile(guesses=calc['ptguess'])
                    tcout, ans = self.tc.calc_assemblage(key.difference(self.ps.excess), p, t)
                    status, variance, pts, res, output = self.tc.parse_logfile()
                    if len(res) == 1:
                        points.append((t, p))
                        results.append(res[0])
                else:
                    err += 1
            if err > 0:
                print('Solution not found on {} points'.format(err))
            return PTpath(points, results)

    def show(self, **kwargs):
        out = kwargs.get('out', None)
        cmap = kwargs.get('cmap', 'Purples')
        alpha = kwargs.get('alpha', 0.6)
        label = kwargs.get('label', False)
        bulk = kwargs.get('bulk', False)
        high = kwargs.get('high', [])

        if isinstance(out, str):
            out = [out]
        # check shapes created
        #if not self.ready:
        #    self.refresh_geometry()
        if self.shapes:
            vari = [self.variance[k] for k in self]
            poc = max(vari) - min(vari) + 1
            pscolors = plt.get_cmap(cmap)(np.linspace(0, 1, poc))
            # Set alpha
            pscolors[:, -1] = alpha
            pscmap = ListedColormap(pscolors)
            norm = BoundaryNorm(np.arange(min(vari) - 0.5, max(vari) + 1.5), poc, clip=True)
            fig, ax = plt.subplots()
            for k in self:
                ax.add_patch(PolygonPatch(self.shapes[k], fc=pscmap(norm(self.variance[k])), ec='none'))
            ax.autoscale_view()
            self.add_overlay(ax, label=label)
            if out:
                for o in out:
                    xy = []
                    for uni in self.ps.unilines.values():
                        if o in uni.out:
                            xy.append((uni.x, uni.y))
                        for poly in polymorphs:
                            if poly.issubset(uni.phases):
                                if o in poly:
                                    if poly.difference({o}).issubset(uni.out):
                                        xy.append((uni.x, uni.y))
                    if xy:
                        ax.plot(np.hstack([(*seg[0], np.nan) for seg in xy]),
                                np.hstack([(*seg[1], np.nan) for seg in xy]),
                                lw=2, label=o)
                # Shrink current axis's width
                box = ax.get_position()
                ax.set_position([box.x0 + box.width * 0.07, box.y0, box.width * 0.95, box.height])
                # Put a legend below current axis
                ax.legend(loc='upper right', bbox_to_anchor=(-0.08, 1), title='Out', borderaxespad=0, frameon=False)
            divider = make_axes_locatable(ax)
            cax = divider.append_axes('right', size='4%', pad=0.05)
            #cbar = ColorbarBase(ax=cax, cmap=pscmap, norm=norm, orientation='vertical', ticks=np.arange(min(vari), max(vari) + 1))
            cbar = ColorbarBase(ax=cax, cmap=pscmap, norm=norm, orientation='vertical', ticks=np.arange(min(vari), max(vari) + 1))
            cbar.set_label('Variance')
            ax.set_xlim(self.ps.xrange)
            ax.set_ylim(self.ps.yrange)
            # Show highlight. Change to list if only single key
            if isinstance(high, frozenset):
                high = [high]
            for k in high:
                ax.add_patch(PolygonPatch(self.shapes[k], fc='none', ec='red', lw=2))
            # Show bulk
            if bulk:
                if label:
                    ax.set_xlabel(self.name + (len(self.ps.excess) * ' +{}').format(*self.ps.excess))
                else:
                    ax.set_xlabel(self.name)
                # bulk composition
                ox, vals = self.ps.get_bulk_composition() # FIXME: TX has another bulk format
                table = r'''\begin{tabular}{ ''' + ' | '.join(len(ox)*['c']) + '}' + ' & '.join(ox) + r''' \\\hline ''' + ' & '.join(vals) + r'''\end{tabular}'''
                plt.figtext(0.1, 0.98, table, size=8, va='top', usetex=True)
            else:
                if label:
                    ax.set_title(self.name + (len(self.ps.excess) * ' +{}').format(*self.ps.excess))
                else:
                    ax.set_title(self.name)
            # coords
            ax.format_coord = self.format_coord
            # connect button press
            #cid = fig.canvas.mpl_connect('button_press_event', self.onclick)
            plt.show()
            # return ax
        else:
            print('There is no single area defined in your pseudosection. Check topology.')

    def format_coord(self, x, y):
        prec = 2
        point = Point(x, y)
        phases = ''
        for key in self.shapes:
            if self.shapes[key].contains(point):
                phases = ' '.join(sorted(list(key.difference(self.ps.excess))))
                break
        return '{}={:.{prec}f} {}={:.{prec}f} {}'.format(self.ps.x_var, x, self.ps.y_var, y, phases, prec=prec)

    def add_overlay(self, ax, fc='none', ec='k', label=False):
        for k in self:
            ax.add_patch(PolygonPatch(self.shapes[k], ec=ec, fc=fc, lw=0.5))
            if label:
                # multiline for long labels
                tl = sorted(list(k.difference(self.ps.excess)))
                wp = len(tl) // 4 + int(len(tl) % 4 > 1)
                txt = '\n'.join([' '.join(s) for s in [tl[i * len(tl) // wp: (i + 1) * len(tl) // wp] for i in range(wp)]])
                xy = self.shapes[k].representative_point().coords[0]
                ax.annotate(s=txt, xy=xy, weight='bold', fontsize=6, ha='center', va='center')

    def show_data(self, key, phase, expr=None, which=7):
        if expr is None:
            msg = 'Missing expression argument. Available variables for phase {} are:\n{}'
            print(msg.format(phase, ' '.join(self.all_data_keys[phase])))
        else:
            dt = self.collect_data(key, phase, expr, which=which)
            x, y = np.array(dt['pts']).T
            fig, ax = plt.subplots()
            pts = ax.scatter(x, y, c=dt['data'])
            ax.set_title('{} - {}({})'.format(' '.join(key), phase, expr))
            plt.colorbar(pts)
            plt.show()

    def show_grid(self, phase, expr=None, interpolation=None, label=False):
        if expr is None:
            msg = 'Missing expression argument. Available variables for phase {} are:\n{}'
            print(msg.format(phase, ' '.join(self.all_data_keys[phase])))
        else:
            gd = np.empty(self.grid.tg.shape)
            gd[:] = np.nan
            for key in self:
                res = self.grid.gridcalcs[self.grid.masks[key]]
                if len(res) > 0:
                    if phase in res[0]['data']:
                        rows, cols = np.nonzero(self.grid.masks[key])
                        for r, c in zip(rows, cols):
                            if self.grid.status[r, c] == 1:
                                gd[r, c] = eval_expr(expr, self.grid.gridcalcs[r, c]['data'][phase])
            fig, ax = plt.subplots()
            im = ax.imshow(gd, extent=self.grid.extent, interpolation=interpolation,
                           aspect='auto', origin='lower')
            self.add_overlay(ax, label=label)
            ax.set_xlim(self.ps.xrange)
            ax.set_ylim(self.ps.yrange)
            cbar = fig.colorbar(im)
            ax.set_title('{}({})'.format(phase, expr))
            fig.tight_layout()
            plt.show()

    def show_status(self, label=False):
        fig, ax = plt.subplots()
        cmap = ListedColormap(['orangered', 'limegreen'])
        bounds = [-0.5, 0.5, 1.5]
        norm = BoundaryNorm(bounds, cmap.N)
        im = ax.imshow(self.grid.status, extent=self.grid.extent,
                       aspect='auto', origin='lower', cmap=cmap, norm=norm)
        self.add_overlay(ax, label=label)
        ax.set_xlim(self.ps.xrange)
        ax.set_ylim(self.ps.yrange)
        ax.set_title('Gridding status - {}'.format(self.name))
        cbar = fig.colorbar(im, cmap=cmap, norm=norm, boundaries=bounds, ticks=[0, 1])
        cbar.ax.set_yticklabels(['Failed', 'OK'])
        fig.tight_layout()
        plt.show()

    def show_delta(self, label=False, pointsec=False):
        if pointsec:
            val = 1 / self.grid.delta
            lbl = 'points/sec'
            tit = 'THERMOCALC calculation rate - {}'
        else:
            val = self.grid.delta
            lbl = 'secs/point'
            tit = 'THERMOCALC execution time - {}'
        fig, ax = plt.subplots()
        im = ax.imshow(val, extent=self.grid.extent, aspect='auto', origin='lower')
        self.add_overlay(ax, label=label)
        ax.set_xlim(self.ps.xrange)
        ax.set_ylim(self.ps.yrange)
        cbar = fig.colorbar(im)
        cbar.set_label(lbl)
        ax.set_title(tit.format(self.name))
        fig.tight_layout()
        plt.show()

    def show_path_data(self, ptpath, phase, expr=None, label=False, pathwidth=4, allpath=True):
        if expr is None:
            msg = 'Missing expression argument. Available variables for phase {} are:\n{}'
            print(msg.format(phase, ' '.join(self.all_data_keys[phase])))
        else:
            ex = ptpath.get_path_data(phase, expr)
            fig, ax = plt.subplots()
            if allpath:
                ax.plot(ptpath.t, ptpath.p, '--', color='grey', lw=1)
            # Create a continuous norm to map from data points to colors
            norm = plt.Normalize(np.nanmin(ex), np.nanmax(ex))

            for s in np.ma.clump_unmasked(np.ma.masked_invalid(ex)):
                ts, ps, exs = ptpath.t[s], ptpath.p[s], ex[s]
                points = np.array([ts, ps]).T.reshape(-1, 1, 2)
                segments = np.concatenate([points[:-1], points[1:]], axis=1)
                lc = LineCollection(segments, cmap='viridis', norm=norm)
                # Set the values used for colormapping
                lc.set_array(exs)
                lc.set_linewidth(pathwidth)
                line = ax.add_collection(lc)
                self.add_overlay(ax, label=label)
            cbar = fig.colorbar(line, ax=ax)
            cbar.set_label('{}[{}]'.format(phase, expr))
            ax.set_xlim(self.ps.xrange)
            ax.set_ylim(self.ps.yrange)
            ax.set_title('PT path - {}'.format(self.name))
            plt.show()

    def show_path_modes(self, ptpath, exclude=[], cmap='tab20'):
        steps = len(ptpath.t)
        nd = np.linspace(0, 1, steps)
        splt = interp1d(nd, ptpath.t, kind='quadratic')
        splp = interp1d(nd, ptpath.p, kind='quadratic')
        pset = set()
        for res in ptpath.results:
            pset.update(res['data'].keys())

        pset = set()
        for res in ptpath.results:
            for key in res['data']:
                if 'mode' in res['data'][key] and key not in exclude:
                    pset.add(key)
        phases = sorted(list(pset))
        modes = np.array([[res['data'][phase]['mode'] if phase in res['data'] else 0 for res in ptpath.results] for phase in phases])
        modes = 100 * modes / modes.sum(axis=0)
        cm = plt.get_cmap(cmap)
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.set_prop_cycle(color=[cm(i/len(phases)) for i in range(len(phases))])
        bottom = np.zeros_like(modes[0])
        bars = []
        for n, mode in enumerate(modes):
            h = ax.bar(nd, mode, bottom=bottom, width=nd[1]-nd[0])
            bars.append(h[0])
            bottom += mode

        ax.format_coord = lambda x, y: 'T={:.2f} p={:.2f}'.format(splt(x), splp(x))
        ax.set_xlim(0, 1)
        ax.set_xlabel('Normalized distance along path')
        ax.set_ylabel('Mode [%]')
        box = ax.get_position()
        ax.set_position([box.x0, box.y0, box.width * 0.9, box.height])
        # Put a legend to the right of the current axis
        ax.legend(bars, phases, fancybox=True, loc='center left', bbox_to_anchor=(1.05,0.5))
        plt.show()

    def identify(self, T, p):
        for key in self:
            if Point(T, p).intersects(self.shapes[key]):
                return key

    def gidentify(self, label=False):
        fig, ax = plt.subplots()
        ax.autoscale_view()
        self.add_overlay(ax, label=label)
        ax.set_xlim(self.ps.xrange)
        ax.set_ylim(self.ps.yrange)
        ax.format_coord = self.format_coord
        T, p = plt.ginput(1)[0]
        return self.identify(T, p)

    def onclick(self, event):
        if event.button == 1:
            if event.inaxes:
                key = self.identify(event.xdata, event.ydata)
                if key:
                    print(' '.join(sorted(list(key))))

    def isopleths(self, phase, expr=None, **kwargs):
        if expr is None:
            msg = 'Missing expression argument. Available variables for phase {} are:\n{}'
            print(msg.format(phase, ' '.join(self.all_data_keys[phase])))
        else:
            # parse kwargs
            which = kwargs.get('which', 7)
            smooth = kwargs.get('smooth', 0)
            filled = kwargs.get('filled', True)
            out = kwargs.get('out', True)
            bulk = kwargs.get('bulk', False)
            nosplit = kwargs.get('nosplit', True)
            step = kwargs.get('step', None)
            N = kwargs.get('N', 10)
            gradient = kwargs.get('gradient', False)
            dt = kwargs.get('dt', True)
            only = kwargs.get('only', None)
            refine = kwargs.get('refine', 1)
            colors = kwargs.get('colors', None)
            cmap = kwargs.get('cmap', 'viridis')
            clabel = kwargs.get('clabel', [])

            if not self.gridded:
                print('Collecting only from uni lines and inv points. Not yet gridded...')
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
                dm = (mx - mn) / 25
                #cntv = np.linspace(max(0, mn - dm), mx + dm, N)
                cntv = np.linspace(mn - dm, mx + dm, N)
            # Thin-plate contouring of areas
            fig, ax = plt.subplots()
            for key in recs:
                tmin, pmin, tmax, pmax = self.shapes[key].bounds
                # ttspace = self.tspace[np.logical_and(self.tspace >= tmin - self.tstep, self.tspace <= tmax + self.tstep)]
                # ppspace = self.pspace[np.logical_and(self.pspace >= pmin - self.pstep, self.pspace <= pmax + self.pstep)]
                ttspace = np.arange(tmin - self.grid.tstep, tmax + self.grid.tstep, self.grid.tstep / refine)
                ppspace = np.arange(pmin - self.grid.pstep, pmax + self.grid.pstep, self.grid.pstep / refine)
                tg, pg = np.meshgrid(ttspace, ppspace)
                x, y = np.array(recs[key]['pts']).T
                try:
                    # Use scaling
                    rbf = Rbf(x, self.ps.ratio * y, recs[key]['data'], function='thin_plate', smooth=smooth)
                    zg = rbf(tg, self.ps.ratio * pg)
                    # experimental
                    if gradient:
                        if dt:
                            zg = np.gradient(zg, self.grid.tstep, self.grid.pstep)[0]
                        else:
                            zg = -np.gradient(zg, self.grid.tstep, self.grid.pstep)[1]
                        if N:
                            cntv = N
                        else:
                            cntv = 10
                    # ------------
                    if filled:
                        cont = ax.contourf(tg, pg, zg, cntv, colors=colors, cmap=cmap)
                    else:
                        cont = ax.contour(tg, pg, zg, cntv, colors=colors, cmap=cmap)
                    patch = PolygonPatch(self.shapes[key], fc='none', ec='none')
                    ax.add_patch(patch)
                    for col in cont.collections:
                        col.set_clip_path(patch)
                    # label if needed
                    if not filled and key == set(clabel):
                        positions = []
                        for col in cont.collections:
                            for seg in col.get_segments():
                                inside = np.fromiter(map(self.shapes[key].contains, MultiPoint(seg)), dtype=bool)
                                if np.any(inside):
                                    positions.append(seg[inside].mean(axis=0))
                        ax.clabel(cont, fontsize=9, manual=positions, fmt='%g', inline_spacing=3, inline=not nosplit)

                except Exception as e:
                    print('{} for {}'.format(type(e).__name__, key))
            if only is None:
                self.add_overlay(ax)
                # zero mode line
                if out:
                    xy = []
                    for uni in self.ps.unilines.values():
                        if phase in uni.out:
                            xy.append((uni.x, uni.y))
                        for poly in polymorphs:
                            if poly.issubset(uni.phases):
                                if phase in poly:
                                    if poly.difference({phase}).issubset(uni.out):
                                        xy.append((uni.x, uni.y))
                    if xy:
                        ax.plot(np.hstack([(*seg[0], np.nan) for seg in xy]),
                                np.hstack([(*seg[1], np.nan) for seg in xy]), lw=2)
            try:
                fig.colorbar(cont)
            except:
                print('There is trouble to draw colorbar. Sorry.')
            if bulk:
                if only is None:
                    ax.set_xlim(self.ps.xrange)
                    ax.set_ylim(self.ps.yrange)
                    ax.set_xlabel('{}({})'.format(phase, expr))
                else:
                    ax.set_xlabel('{} - {}({})'.format(' '.join(only), phase, expr))
                # bulk composition
                ox, vals = self.ps.get_bulk_composition()
                table = r'''\begin{tabular}{ ''' + ' | '.join(len(ox)*['c']) + '}' + ' & '.join(ox) + r''' \\\hline ''' + ' & '.join(vals) + r'''\end{tabular}'''
                plt.figtext(0.08, 0.94, table, size=10, va='top', usetex=True)
            else:
                if only is None:
                    ax.set_xlim(self.ps.xrange)
                    ax.set_ylim(self.ps.yrange)
                    ax.set_title('{}({})'.format(phase, expr))
                else:
                    ax.set_title('{} - {}({})'.format(' '.join(only), phase, expr))
            # coords
            ax.format_coord = self.format_coord
            # connect button press
            #cid = fig.canvas.mpl_connect('button_press_event', self.onclick)
            plt.show()

    def gendrawpd(self, export_areas=True):
        #self.refresh_geometry()
        with self.tc.drawpdfile.open('w', encoding=self.tc.TCenc) as output:
            output.write('% Generated by PyPSbuilder (c) Ondrej Lexa 2019\n')
            output.write('2    % no. of variables in each line of data, in this case P, T\n')
            exc = frozenset.intersection(*self.keys)
            nc = frozenset.union(*self.keys)
            # ex.insert(0, '')
            output.write('{}'.format(len(nc) - len(exc)) + '\n')
            output.write('2 1  %% which columns to be x,y in phase diagram\n')
            output.write('\n')
            output.write('% Points\n')
            for inv in self.ps.invpoints.values():
                output.write('% ------------------------------\n')
                output.write('i{}   {}\n'.format(inv.id, inv.label(excess=self.ps.excess)))
                output.write('\n')
                output.write('{} {}\n'.format(inv._y, inv._x))
                output.write('\n')
            output.write('% Lines\n')
            for uni in self.ps.unilines.values():
                output.write('% ------------------------------\n')
                output.write('u{}   {}\n'.format(uni.id, uni.label(excess=self.ps.excess)))
                output.write('\n')
                if uni.begin == 0:
                    b1 = 'begin'
                else:
                    b1 = 'i{}'.format(uni.begin)
                if uni.end == 0:
                    b2 = 'end'
                else:
                    b2 = 'i{}'.format(uni.end)
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
                # phases in areas for TC-Investigator
                with self.tc.workdir.joinpath('assemblages.txt').open('w') as tcinv:
                    vertices, edges, phases, tedges, tphases = self.ps.construct_areas()
                    # write output
                    output.write('% Areas\n')
                    output.write('% ------------------------------\n')
                    maxpf = max([len(p) for p in phases]) + 1
                    for ed, ph, ve in zip(edges, phases, vertices):
                        v = np.array(ve)
                        if not (np.all(v[:, 0] < self.ps.xrange[0]) or
                                np.all(v[:, 0] > self.ps.xrange[1]) or
                                np.all(v[:, 1] < self.ps.yrange[0]) or
                                np.all(v[:, 1] > self.ps.yrange[1])):
                            d = ('{:.2f} '.format(len(ph) / maxpf) +
                                 ' '.join(['u{}'.format(e) for e in ed]) +
                                 ' % ' + ' '.join(ph) + '\n')
                            output.write(d)
                            tcinv.write(' '.join(ph.union(exc)) + '\n')
                    for ed, ph in zip(tedges, tphases):
                        d = ('{:.2f} '.format(len(ph) / maxpf) +
                             ' '.join(['u{}'.format(e) for e in ed]) +
                             ' %- ' + ' '.join(ph) + '\n')
                        output.write(d)
                        tcinv.write(' '.join(ph.union(exc)) + '\n')
            output.write('\n')
            output.write('*\n')
            output.write('\n')
            output.write('window {} {} '.format(*self.ps.xrange) +
                         '{} {}\n\n'.format(*self.ps.yrange))
            output.write('darkcolour  56 16 101\n\n')
            dt = self.ps.xrange[1] - self.ps.xrange[0]
            dp = self.ps.yrange[1] - self.ps.yrange[0]
            ts = np.power(10, np.int(np.log10(dt)))
            ps = np.power(10, np.int(np.log10(dp)))
            tg = np.arange(0, self.ps.xrange[1] + ts, ts)
            tg = tg[tg >= self.ps.xrange[0]]
            pg = np.arange(0, self.ps.yrange[1] + ps, ps)
            pg = pg[pg >= self.ps.yrange[0]]
            output.write('bigticks ' +
                         '{} {} '.format(tg[1] - tg[0], tg[0]) +
                         '{} {}\n\n'.format(pg[1] - pg[0], pg[0]))
            output.write('smallticks {} '.format((tg[1] - tg[0]) / 10) +
                         '{}\n\n'.format((pg[1] - pg[0]) / 10))
            output.write('numbering yes\n\n')
            if export_areas:
                output.write('doareas yes\n\n')
            output.write('*\n')
            print('Drawpd file generated successfully.')

        if self.tc.rundr():
            print('Drawpd sucessfully executed.')
        else:
            print('Drawpd error!', str(err))

    def save_tab(self, tabfile=None, comps=None): # FIXME:
        if not tabfile:
            tabfile = self.name + '.tab'
        if not comps:
            comps = self.all_data_keys
        data = []
        for comp in tqdm(comps, desc='Exporting'):
            data.append(self.get_gridded(comp).flatten())
        with Path(tabfile).open('wb') as f:
            head = ['psbuilder', self.name + '.tab', '{:12d}'.format(2),
                    'T(°C)', '   {:16.16f}'.format(self.ps.trange[0])[:19],
                    '   {:16.16f}'.format(self.tstep)[:19], '{:12d}'.format(len(self.tspace)),
                    'p(kbar)', '   {:16.16f}'.format(self.ps.prange[0])[:19],
                    '   {:16.16f}'.format(self.pstep)[:19], '{:12d}'.format(len(self.pspace)),
                    '{:12d}'.format(len(data)), (len(data) * '{:15s}').format(*comps)]
            for ln in head:
                f.write(bytes(ln + '\n', 'utf-8'))
            np.savetxt(f, np.transpose(data), fmt='%15.6f', delimiter='')
        print('Saved.')

    def get_gridded(self, phase, expr=None, which=7, smooth=0): # FIXME:
        if expr is None:
            msg = 'Missing expression argument. Available variables for phase {} are:\n{}'
            print(msg.format(phase, ' '.join(self.all_data_keys[phase])))
        else:
            recs, mn, mx = self.merge_data(phase, expr, which=which)
            gd = np.empty(self.grid.tg.shape)
            gd[:] = np.nan
            for key in recs:
                tmin, pmin, tmax, pmax = self.shapes[key].bounds
                ttind = np.logical_and(self.grid.tspace >= tmin - self.grid.tstep, self.grid.tspace <= tmax + self.grid.tstep)
                ppind = np.logical_and(self.grid.pspace >= pmin - self.grid.pstep, self.grid.pspace <= pmax + self.grid.pstep)
                slc = np.ix_(ppind, ttind)
                tg, pg = self.grid.tg[slc], self.grid.pg[slc]
                x, y = np.array(recs[key]['pts']).T
                # Use scaling
                rbf = Rbf(x, self.ps.ratio * y, recs[key]['data'], function='thin_plate', smooth=smooth)
                zg = rbf(tg, self.ps.ratio * pg)
                gd[self.grid.masks[key]] = zg[self.grid.masks[key][slc]]
            return gd

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

def ps_show():
    parser = argparse.ArgumentParser(description='Draw pseudosection from project file')
    parser.add_argument('project', type=str,
                        help='builder project file')
    parser.add_argument('-o', '--out', nargs='+',
                        help='highlight out lines for given phases')
    parser.add_argument('-l', '--label', action='store_true',
                        help='show area labels')
    parser.add_argument('-b', '--bulk', action='store_true',
                        help='show bulk composition on figure')
    parser.add_argument('--cmap', type=str,
                        default='Purples', help='name of the colormap')
    parser.add_argument('--alpha', type=float,
                        default=0.6, help='alpha of colormap')
    args = parser.parse_args()
    ps = PTPS(args.project)
    sys.exit(ps.show(out=args.out, label=args.label, bulk=args.bulk,
                     cmap=args.cmap, alpha=args.alpha))


def ps_grid():
    parser = argparse.ArgumentParser(description='Calculate compositions in grid')
    parser.add_argument('project', type=str,
                        help='builder project file')
    parser.add_argument('--numT', type=int, default=51,
                        help='number of T steps')
    parser.add_argument('--numP', type=int, default=51,
                        help='number of P steps')
    args = parser.parse_args()
    ps = PTPS(args.project)
    sys.exit(ps.calculate_composition(numT=args.numT, numP=args.numP))


def ps_iso():
    parser = argparse.ArgumentParser(description='Draw isopleth diagrams')
    parser.add_argument('project', type=str,
                        help='builder project file')
    parser.add_argument('phase', type=str,
                        help='phase used for contouring')
    parser.add_argument('expr', type=str,
                        help='expression evaluated to calculate values')
    parser.add_argument('-f', '--filled', action='store_true',
                        help='filled contours')
    parser.add_argument('-o', '--out', action='store_true',
                        help='highlight out line for given phase')
    parser.add_argument('--nosplit', action='store_true',
                        help='controls whether the underlying contour is removed or not')
    parser.add_argument('-b', '--bulk', action='store_true',
                        help='show bulk composition on figure')
    parser.add_argument('--step', type=float,
                        default=None, help='contour step')
    parser.add_argument('--ncont', type=int,
                        default=10, help='number of contours')
    parser.add_argument('--colors', type=str,
                        default=None, help='color for all levels')
    parser.add_argument('--cmap', type=str,
                        default=None, help='name of the colormap')
    parser.add_argument('--smooth', type=float,
                        default=0, help='smoothness of the approximation')
    parser.add_argument('--clabel', nargs='+',
                        default=[], help='label contours in field defined by set of phases')
    args = parser.parse_args()
    ps = PTPS(args.project)
    sys.exit(ps.isopleths(args.phase, args.expr, filled=args.filled,
                          smooth=args.smooth, step=args.step, bulk=args.bulk,
                          N=args.ncont, clabel=args.clabel, nosplit=args.nosplit,
                          colors=args.colors, cmap=args.cmap, out=args.out))


def ps_drawpd():
    parser = argparse.ArgumentParser(description='Generate drawpd file from project')
    parser.add_argument('project', type=str,
                        help='psbuilder project file')
    parser.add_argument('-a', '--areas', action='store_true',
                        help='export also areas', default=True)
    args = parser.parse_args()
    ps = PTPS(args.project)
    sys.exit(ps.gendrawpd(export_areas=args.areas))
