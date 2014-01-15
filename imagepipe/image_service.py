# -*- coding: utf-8 -*-

"""Twisted XML-RPC service implementation"""

import base64
import json
import os
import signal
import traceback
import uuid

from twisted.application import service
from twisted.internet import defer, reactor, threads
from twisted.web import server, xmlrpc
import txzmq

from imagepipe import config
from imagepipe import image_io


class Error(Exception):
    """Base class for service errors"""
    pass


class ClientError(Error):
    """Indicates errors triggered by invalid client data"""
    pass


class ServerError(Error):
    """Indicates service processing errors"""
    pass


class ImageService(service.Service):
    """Initializer for the XMLRPC server and zeromq-based replication"""

    def __init__(self, conf_path):
        self._conf_path = conf_path
        self._settings = None
        self._xmlrpc_port = None
        self._xmlrpc_server = None
        self._zmq_factory = None
        self._pub_connection = None
        self._sub_connection = None
        self._replication_id = None

    def _init_settings(self):
        """Load configuration"""
        settings = config.read(self._conf_path)
        config.check(settings)
        self._settings = settings  # Set after validation
        reactor.suggestThreadPoolSize(self._settings['images']['io_threads'])

    def _init_replication(self):
        """Set up replication endpoints

        This creates a local (pub) and remote (sub) zeromq sockets and
        generates an unique identifier to distinguish replication messages sent
        by different publisher.
        """
        self._zmq_factory = txzmq.ZmqFactory()

        if self._settings['replication']['publish']:
            pub_endpoint = txzmq.ZmqEndpoint(
                'bind', self._settings['replication']['publish'])
            self._pub_connection = txzmq.ZmqPubConnection(self._zmq_factory,
                                                          pub_endpoint)
        if self._settings['replication']['subscribe']:
            sub_endpoint = txzmq.ZmqEndpoint(
                'connect', self._settings['replication']['subscribe'])
            self._sub_connection = txzmq.ZmqSubConnection(self._zmq_factory,
                                                          sub_endpoint)
        if not self._replication_id:
            self._replication_id = uuid.uuid4()

    def _init_server(self):
        """Set up server socket"""
        self._xmlrpc_server = XMLRPCServer(
            self._settings, self._pub_connection, self._sub_connection,
            self._replication_id)

        self._xmlrpc_port = reactor.listenTCP(
            self._settings['network']['port'],
            server.Site(self._xmlrpc_server),
            interface=self._settings['network']['interface'])

    @defer.inlineCallbacks
    def _signal(self, signum, frame):
        """Signal handler"""
        if signum == signal.SIGHUP:
            print 'Received SIGHUP, reloading.'

            port = self._settings['network']['port']
            interface = self._settings['network']['interface']
            publish = self._settings['replication']['publish']
            subscribe = self._settings['replication']['subscribe']

            try:
                self._init_settings()
            except Exception:
                traceback.print_exc()
                return

            self._xmlrpc_server.settings = self._settings

            reload_server = False
            if (self._settings['network']['port'] != port or
                    self._settings['network']['interface'] != interface):
                reload_server = True

            reload_replication = False
            if (self._settings['replication']['publish'] != publish or
                    self._settings['replication']['subscribe'] != subscribe):
                reload_replication = True

            if reload_replication:
                # The server can publish messages after the factory is shutdown
                # (and before it is created again) which in turn leads to an
                # exception; we prevent this by removing pub_connection from
                # the server first
                self._xmlrpc_server.pub_connection = None
                self._zmq_factory.shutdown()
                self._init_replication()

                if not reload_server:
                    self._xmlrpc_server.pub_connection = self._pub_connection
                    self._xmlrpc_server.sub_connection = self._sub_connection
                    return

            if reload_server:
                yield self._xmlrpc_port.stopListening()
                self._init_server()

    def startService(self):
        """Set up service"""
        signal.signal(signal.SIGHUP, self._signal)
        self._init_settings()
        self._init_replication()
        self._init_server()
        service.Service.startService(self)

    def stopService(self):
        """Tear down service"""
        self._xmlrpc_server.pub_connection = None
        self._zmq_factory.shutdown()
        service.Service.stopService(self)


class XMLRPCServer(xmlrpc.XMLRPC):
    """XMLRPC server for handling image manipulation calls"""

    def __init__(self, settings, pub_connection, sub_connection,
                 replication_id):
        self.settings = settings
        self.pub_connection = pub_connection
        self.sub_connection = sub_connection
        self._replication_id = replication_id

        if self.sub_connection:
            self.sub_connection.subscribe('')
            self.sub_connection.gotMessage = self._replication_process

        xmlrpc.XMLRPC.__init__(self)

    def _ebRender(self, failure):
        """Translate exceptions to XMLRPC faults"""
        if isinstance(failure.value, xmlrpc.Fault):
            return failure.value

        print failure

        if failure.type == TypeError:
            message = '[1000] Invalid parameters'
        elif failure.type == ClientError:
            message = '[1000] ' + failure.getErrorMessage()
        elif failure.type == ServerError:
            message = '[1001] ' + failure.getErrorMessage()
        else:
            message = '[1002] Internal error'

        return xmlrpc.Fault(self.FAILURE, message)

    def _replication_publish(self, replication_id, method, *args):
        """Send replication message

        Each message contains the publisher's replication id, the RPC method
        call and method's arguments. The message is JSON encoded on the wire.
        """
        if self.pub_connection:
            message = {'id': replication_id.hex,
                       'method': method,
                       'args': args}
            self.pub_connection.publish(json.dumps(message))

    @defer.inlineCallbacks
    def _replication_process(self, json_str, tag=''):
        """Handle received replication message and execute a local _api_*
        method"""
        try:
            message = json.loads(json_str)
            if ('id' not in message or 'method' not in message or
                    'args' not in message):
                raise ValueError()
            replication_id = uuid.UUID(hex=message['id'])
        except Exception:
            traceback.print_exc()
            print "Received bogus message: %s" % (json_str,)
            return

        # Skip own messages
        if replication_id == self._replication_id:
            return

        method = getattr(self, '_api_' + message['method'], None)
        if not method:
            print "Received unknown method %s from %s" % (message['method'],
                                                          replication_id,)
            return

        print '%s@%s' % (message['method'], replication_id)

        yield method(*message['args'])
        self._replication_publish(replication_id, message['method'],
                                  *message['args'])

    @defer.inlineCallbacks
    def _api_store_image(self, image, path, fmt=None, size=None,
                         composite=0, crop=0):
        """Store image and apply transformations

        Arguments:
        image -- image data, encoded in base64
        path -- destination path, relative to images.path from configuration
        fmt -- format of the destination image, e.g. 'png', 'gif'
        size -- size of the destination image, [width, height]
        composite -- set to 1 if destination image should be resized and
                     overlapped over transparent one to both conform with the
                     size specification and keep the original aspect ratio
        crop -- set to 1 if destination image should be cropped to conform with
                the size specification

        The below arguments will result in storing a single image resized to
        500x500px.

            path = 'x/y/z/image.jpg'
            size = [500, 500]

        Multiple versions of the same image can be stored at once by providing
        a dictionary in the place of the size argument. Consider the following
        example:

            path = 'x/y/z/image.jpg'
            size = {'': [500, 500],  # no suffix
                    '_medium': [250, 250],
                    '_small': [50, 50]}

        This will result in creation of three images:

            x/y/z/image.jpg, 500x500px
            x/y/z/image_medium.jpg, 250x250px
            x/y/z/image_small.jpg, 50x50px

        A dictionary can also be provided in the place of format, composite and
        crop arguments. The keys must equal the ones from the size dictionary.
        If single values are provided they affect all created images.
        """
        try:
            blob = base64.decodestring(image)
        except Exception:
            raise ClientError('Invalid image encoding, should be base64')

        normalized_path = image_io.normalize_path(
            self.settings['images']['path'] + '/' + path,
            self.settings['images']['path'])

        if not normalized_path:
            raise ClientError("Invalid path(s)")

        if size:
            if not isinstance(size, dict):
                size = {'': size}

            if not isinstance(fmt, dict):
                fmt = dict([(item[0], fmt) for
                            item in size.items()])

            if not isinstance(composite, dict):
                composite = dict([(item[0], composite) for
                                  item in size.items()])

            if not isinstance(crop, dict):
                crop = dict([(item[0], crop) for
                             item in size.items()])

            (dirs, filename) = os.path.split(normalized_path)
            parts = filename.split('.')

            for suffix, dimension in size.items():
                if not isinstance(dimension, list) or len(dimension) != 2:
                    raise ClientError("Invalid dimension specification, "
                                      "should be a list with two elements "
                                      "(width and height)")
                dimension = [int(n) for n in dimension]

                if suffix in fmt:
                    if fmt[suffix]:
                        if not isinstance(fmt[suffix], basestring):
                            raise ClientError("Invalid format specification, "
                                              "should be a string")
                        fmt[suffix] = fmt[suffix].lower()
                else:
                    fmt[suffix] = None

                # Add a suffix and replace the original extension if format
                # was specified
                if len(parts) == 1:
                    suffixed_path = dirs + '/' + filename + suffix
                    if fmt[suffix]:
                        suffixed_path += '.' + fmt[suffix]
                else:
                    suffixed_path = (dirs + '/' + '.'.join(parts[:-1]) +
                                    suffix + '.')
                    if fmt[suffix]:
                        suffixed_path += fmt[suffix]
                    else:
                        suffixed_path += parts[-1]

                try:
                    yield threads.deferToThread(
                        image_io.store, blob=blob, path=suffixed_path,
                        fmt=fmt[suffix], dimension=dimension,
                        composite=composite[suffix], crop=crop[suffix],
                        umask=self.settings['images']['umask'],
                        convert=self.settings['imagemagick']['convert'],
                        env=self.settings['imagemagick']['env'])
                except Exception:
                    traceback.print_exc()
                    raise ServerError("Unable to store image(s), see log for "
                                      "details")
        else:
            if fmt:
                if not isinstance(fmt, basestring):
                    raise ClientError("Invalid format specification, should "
                                      "be a string")
                # Replace the original extension according to the format
                parts = normalized_path.split('.')
                if len(parts) == 1:
                    parts.append(fmt)
                else:
                    parts[-1] = fmt
                normalized_path = '.'.join(parts)

            if composite or crop:
                raise ClientError("Composite and crop options require a size "
                                  "specification")

            try:
                yield threads.deferToThread(
                    image_io.store, blob=blob, path=normalized_path,
                    fmt=fmt, umask=self.settings['images']['umask'],
                    convert=self.settings['imagemagick']['convert'],
                    env=self.settings['imagemagick']['env'])
            except Exception:
                traceback.print_exc()
                raise ServerError("Unable to store image(s), see log for "
                                  "details")

    @defer.inlineCallbacks
    def _api_delete_image(self, path):
        """Delete image

        Arguments:
        path -- path of the image or a list of paths
        """
        if not isinstance(path, list):
            paths = [path]
        else:
            paths = path

        for path in paths:
            if not isinstance(path, basestring):
                raise ClientError("Invalid path specification, should be a "
                                  "string")

            normalized_path = image_io.normalize_path(
                self.settings['images']['path'] + '/' + path,
                self.settings['images']['path'])

            if not normalized_path:
                raise ClientError("Invalid path(s)")

            try:
                yield threads.deferToThread(
                    image_io.delete, path=normalized_path)
            except Exception:
                traceback.print_exc()
                raise ServerError("Unable to delete image(s), see log for "
                                  "details")

    @defer.inlineCallbacks
    def _api_move_image(self, src_path, dst_path):
        """Move image from source to destination path

        Arguments:
        src_path -- the source path or a list of paths
        dst_path -- the destination path or a list of paths

        In case of multiple paths both lists must equal in length.
        """
        if not isinstance(src_path, list):
            src_path = [src_path]

        if not isinstance(dst_path, list):
            dst_path = [dst_path]

        if len(src_path) != len(dst_path):
            raise ClientError("Number of source paths should match number of "
                              "destination paths")

        for i in xrange(len(src_path)):
            normalized_src_path = image_io.normalize_path(
                self.settings['images']['path'] + '/' + src_path[i],
                self.settings['images']['path'])

            normalized_dst_path = image_io.normalize_path(
                self.settings['images']['path'] + '/' + dst_path[i],
                self.settings['images']['path'])

            if not normalized_src_path or not normalized_dst_path:
                raise ClientError("Invalid path(s)")

            try:
                yield threads.deferToThread(
                    image_io.move, src_path=normalized_src_path,
                    dst_path=normalized_dst_path,
                    umask=self.settings['images']['umask'])
            except Exception:
                traceback.print_exc()
                raise ServerError("Unable to move image(s), see log for "
                                  "details")

    @defer.inlineCallbacks
    def xmlrpc_store_image(self, image, path, format=None, size=None,
                           composite=0, crop=0):
        """Handle store_image RPC

        See XMLRPCServer._api_store_image for explanation of the arguments.
        """
        yield self._api_store_image(image, path, format, size, composite, crop)
        self._replication_publish(self._replication_id, 'store_image', image,
                                  path, format, size, composite, crop)
        defer.returnValue('OK')

    @defer.inlineCallbacks
    def xmlrpc_delete_image(self, path):
        """Handle delete_image RPC

        See XMLRPCServer._api_delete_image for explanation of the arguments.
        """
        yield self._api_delete_image(path)
        self._replication_publish(self._replication_id, 'delete_image',
                                  path)
        defer.returnValue('OK')

    @defer.inlineCallbacks
    def xmlrpc_move_image(self, src_path, dst_path):
        """Handle move_image RPC

        See XMLRPCServer._api_move_image for explanation of the arguments.
        """
        yield self._api_move_image(src_path, dst_path)
        self._replication_publish(self._replication_id, 'move_image', src_path,
                                  dst_path)
        defer.returnValue('OK')
