# -*- coding: utf-8 -*-

"""A XML-RPC service for storing images (twistd plugin)"""

from twisted import plugin
from twisted.application import service
from twisted.python import usage
from zope import interface

from imagepipe import image_service


class Options(usage.Options):
    """Plugin options"""
    optParameters = [['conf', 'c', 'imagepipe.ini', 'Configuration file']]


class ServiceMaker(object):
    """Service bootstrap"""
    interface.implements(service.IServiceMaker, plugin.IPlugin)
    tapname = "imagepipe"
    description = "A XML-RPC service for storing images."
    options = Options

    def makeService(self, options):
        """Returns the service object derived from
        twisted.application.service.Service"""
        return image_service.ImageService(options['conf'])


serviceMaker = ServiceMaker()
