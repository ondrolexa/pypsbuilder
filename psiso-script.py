#!/usr/bin/env python
import sys
import argparse
from pypsbuilder.psexplorer import PTPS


def main():
    parser = argparse.ArgumentParser(description='Draw isopleth diagrams')
    parser.add_argument('project', type=str,
                        help='psbuilder project file')
    parser.add_argument('phase', type=str,
                        help='phase used for contouring')
    parser.add_argument('expr', type=str,
                        help='expression evaluated to calculate values')
    parser.add_argument('-f', '--filled', action='store_true',
                        help='filled contours')
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
    print('Running psiso...')
    ps = PTPS(args.project)
    sys.exit(ps.isopleths(args.phase, args.expr, filled=args.filled,
                          smooth=args.smooth, step=args.step,
                          N=args.ncont, clabel=args.clabel,
                          colors=args.colors, cmap=args.cmap))


if __name__ == "__main__":
    main()
