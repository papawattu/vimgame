from setuptools import find_packages, setup

setup(
    name='vimgame',
    version='0.1.0',
    packages=find_packages(include=['src', 'src.*']),
    py_modules=['vim_motion_trainer'],
    include_package_data=True,
    package_data={'src.content': ['content.json']},
    install_requires=[],
    entry_points={
        'console_scripts': [
            'vim-motion-trainer = vim_motion_trainer:main',
        ],
    },
)
