from setuptools import setup, find_packages

requirements = [
    'numpy',
    'matplotlib',
    'networkx'
]

setup(
    name='pypsbuilder',
    version='2.0.2',
    description="Simplistic THERMOCALC front-end for constructing PT pseudosections",
    author="Ondrej Lexa",
    author_email='lexa.ondrej@gmail.com',
    url='https://github.com/ondrolexa/pypsbuilder',
    packages=find_packages(),
    package_data={'pypsbuilder.images': ['*.png']},
    entry_points={
        'console_scripts': [
            'psbuilder=pypsbuilder.psbuilder:main'
        ]
    },
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
