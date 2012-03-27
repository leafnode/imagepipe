# -*- coding: utf-8 -*-

"""Configuration handling functions"""

import cStringIO

import configobj
import validate


_spec = """
[network]
interface = string(default='0.0.0.0')
port = integer(default=8085)

[replication]
publish = string(default=None)
subscribe = string(default=None)

[images]
path = string()
umask = integer(default=0022)
io_threads = integer(default=1)

[imagemagick]
convert = string(default='/usr/bin/convert')
[[env]]
"""


class Error(Exception):
    """Base class for configuration errors"""
    pass


class ValidationError(Error):
    """Indicates missing section or setting"""
    pass


def read(conf_path):
    """Create a configuration object from cont_path"""
    configspec = configobj.ConfigObj(cStringIO.StringIO(_spec))
    return configobj.ConfigObj(conf_path, configspec=configspec,
                               file_error=True)


def check(config):
    """Validate configuration according to _spec"""
    test = config.validate(validate.Validator(), preserve_errors=True)

    for entry in configobj.flatten_errors(config, test):
        section_list, key, error = entry
        if error == False:
            if not key:
                message = ("Section '%s' not defined" % (
                    '[' + '] -> ['.join(section_list) + ']'))
            else:
                message = ("Setting '%s' not defined" % (
                    '[' + '] -> ['.join(section_list) + '] -> ' + str(key)))
            raise ValidationError(message)
        else:
            raise error
