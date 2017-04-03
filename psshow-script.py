#!/usr/bin/env python
import sys
import argparse
from pypsbuilder.psexplorer import PTPS


def main():
    parser = argparse.ArgumentParser(description='Draw pseudosection from project file')
    parser.add_argument('project', type=str,
                        help='psbuilder project file')
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


if __name__ == "__main__":
    main()
