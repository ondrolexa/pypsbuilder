#!/usr/bin/env python
import sys
import argparse
from pypsbuilder.psexplorer import PTPS


def main():
    parser = argparse.ArgumentParser(description='Identify phases in field')
    parser.add_argument('project', type=str,
                        help='psbuilder project file')
    args = parser.parse_args()
    ps = PTPS(args.project)
    print(' '.join(ps.ginput()))
    sys.exit()


if __name__ == "__main__":
    main()
