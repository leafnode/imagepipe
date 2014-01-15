#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

setup(name='imagepipe',
      version='2.1.0',
      maintainer='Lukasz Kawczynski',
      maintainer_email='n@neuroid.pl',
      packages=['imagepipe'],
      data_files=[
          ('twisted/plugins', ['twisted/plugins/imagepipe_plugin.py'])
      ],
      install_requires=['configobj', 'pyzmq', 'Twisted', 'txzmq', 'Unidecode'])

# Refresh Twisted plugin cache
from twisted.plugin import IPlugin, getPlugins
list(getPlugins(IPlugin))
