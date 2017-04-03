#!/usr/bin/env python
import sys
import argparse
from pypsbuilder.psexplorer import PTPS


def main():
    parser = argparse.ArgumentParser(description='Generate drawpd file from project')
    parser.add_argument('project', type=str,
                        help='psbuilder project file')
    parser.add_argument('-a', '--areas', action='store_true',
                        help='export also areas', default=True)
    args = parser.parse_args()
    ps = PTPS(args.project)
    sys.exit(ps.gendrawpd(export_areas=args.areas))


if __name__ == "__main__":
    main()
