from setuptools import setup

requirements = [
    'pyqt5',
    'numpy',
    'matplotlib'
]

test_requirements = [
    'pytest',
    'pytest-cov',
    'pytest-faulthandler',
    'pytest-mock',
    'pytest-qt',
    'pytest-xvfb',
]

setup(
    name='pypsbuilder',
    version='2.0.0',
    description="simplistic THERMOCALC front-end for constructing PT pseudosections",
    author="Ondrej Lexa",
    author_email='lexa.ondrej@gmail.com',
    url='https://github.com/ondrolexa/pypsbuilder',
    packages=['pypsbuilder', 'pypsbuilder.images',
              'pypsbuilder.tests'],
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
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
    test_suite='tests',
    tests_require=test_requirements
)
