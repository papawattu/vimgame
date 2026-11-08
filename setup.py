from setuptools import setup, find_packages

setup(
    name='vimgame',
    version='0.1.0',
    packages=find_packages(where='src'),
    include_package_data=True,
    install_requires=[],
    entry_points={
        'console_scripts': [
            'vim-motion-trainer = vim_motion_trainer:main',
        ],
    },
)