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
                        help='show alrea labels')
    args = parser.parse_args()
    print('Running psshow...')
    ps = PTPS(args.project)
    sys.exit(ps.show(out=args.out, label=args.label))


if __name__ == "__main__":
    main()
