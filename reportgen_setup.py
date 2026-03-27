#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Excel到Docx自动化报告生成系统安装配置
"""

from setuptools import setup, find_packages
import os

# 读取版本信息
version_file = os.path.join('reportgen', '__version__.py')
version = {}
with open(version_file, 'r', encoding='utf-8') as f:
    exec(f.read(), version)

# 读取README
with open('README.md', 'r', encoding='utf-8') as f:
    long_description = f.read()

# 读取requirements
with open('requirements.txt', 'r', encoding='utf-8') as f:
    requirements = [line.strip() for line in f 
                   if line.strip() and not line.startswith('#')]

setup(
    name='reportgen',
    version=version['__version__'],
    description='Excel到Docx自动化医疗报告生成系统',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Medical Report Team',
    author_email='',
    url='',
    packages=find_packages(exclude=['tests', 'tests.*']),
    include_package_data=True,
    install_requires=requirements,
    entry_points={
        'console_scripts': [
            'reportgen=reportgen.cli:cli',
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Healthcare Industry',
        'Topic :: Scientific/Engineering :: Medical Science Apps.',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
    python_requires='>=3.9',
)


