#!/usr/bin/env python
import sys
import argparse
from pypsbuilder.psexplorer import PTPS

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=str,
                        help="psbuilder project file")
    parser.add_argument("phase", type=str,
                        help="phase used for contouring")
    parser.add_argument("expr", type=str,
                        help="expression evalutaed to calculate values")
    parser.add_argument("-f", "--filled", action="store_true",
                    help="filled contours")
    args = parser.parse_args()
    print('Running psexplorer...')
    ps = PTPS(args.project)
    sys.exit(ps.isopleths(args.phase, args.expr, filled=args.filled))

if __name__ == "__main__":
    main()
