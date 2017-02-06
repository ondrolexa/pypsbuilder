#!/usr/bin/env python
# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read().replace('.. :changelog:', '')

requirements = [
    'numpy',
    'matplotlib'
]

setup(
    name='pypsbuilder',
    version='2.0.7',
    description="Simplistic THERMOCALC front-end for constructing PT pseudosections",
    long_description=readme + '\n\n' + history,
    author="Ondrej Lexa",
    author_email='lexa.ondrej@gmail.com',
    url='https://github.com/ondrolexa/pypsbuilder',
    packages=find_packages(),
    package_data={'pypsbuilder.images': ['*.png']},
    entry_points="""
    [console_scripts]
    psbuilder=pypsbuilder.psbuilder:main
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
