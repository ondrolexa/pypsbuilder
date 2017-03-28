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
    args = parser.parse_args()
    print('Running psshow...')
    ps = PTPS(args.project)
    sys.exit(ps.show(out=args.out, label=args.label, bulk=args.bulk))


if __name__ == "__main__":
    main()
