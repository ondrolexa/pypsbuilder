#!/usr/bin/env python
# -*- coding: utf-8 -*-
from os import path
from setuptools import setup, find_packages

CURRENT_PATH = path.abspath(path.dirname(__file__))

with open(path.join(CURRENT_PATH, 'README.md')) as readme_file:
    readme = readme_file.read()

with open(path.join(CURRENT_PATH, 'CHANGELOG.md')) as changelog_file:
    changelog = changelog_file.read()

requirements = [
    'numpy',
    'matplotlib>=3',
    'scipy',
    'networkx',
    'shapely>=2',
    'tqdm'
]

setup(
    name='pypsbuilder',
    version='2.3.6',
    description="THERMOCALC front-end for constructing and analyzing PT pseudosections",
    long_description=readme + '\n\n' + changelog,
    long_description_content_type="text/markdown",
    author="Ondrej Lexa",
    author_email='lexa.ondrej@gmail.com',
    url='https://github.com/ondrolexa/pypsbuilder',
    license="MIT",
    python_requires=">=3.8",
    packages=find_packages(),
    package_data={'pypsbuilder.images': ['*.png']},
    entry_points="""
    [console_scripts]
    ptbuilder=pypsbuilder.psbuilders:ptbuilder
    txbuilder=pypsbuilder.psbuilders:txbuilder
    pxbuilder=pypsbuilder.psbuilders:pxbuilder
    psshow=pypsbuilder.psexplorer:ps_show
    psiso=pypsbuilder.psexplorer:ps_iso
    psgrid=pypsbuilder.psexplorer:ps_grid
    psdrawpd=pypsbuilder.psexplorer:ps_drawpd
    tcinit=pypsbuilder.tcinit:tcprojinit
    """,
    install_requires=requirements,
    zip_safe=False,
    keywords='pypsbuilder',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Scientific/Engineering',
        'Topic :: Utilities'
    ]
)
