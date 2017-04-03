#!/usr/bin/env python
import sys
import argparse
from pypsbuilder.psexplorer import PTPS


def main():
    parser = argparse.ArgumentParser(description='Calculate compositions in grid')
    parser.add_argument('project', type=str,
                        help='psbuilder project file')
    parser.add_argument('--numT', type=int, default=51,
                        help='number of T steps')
    parser.add_argument('--numP', type=int, default=51,
                        help='number of P steps')
    args = parser.parse_args()
    ps = PTPS(args.project)
    sys.exit(ps.calculate_composition(numT=args.numT, numP=args.numP))


if __name__ == "__main__":
    main()
