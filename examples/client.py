#!/usr/bin/python -u
# -*- coding: utf-8 -*-

"""Example client for imagepipe"""

import base64
import os
import re
import cStringIO
import sys
import urllib
import xmlrpclib
from optparse import OptionParser

if __name__ == '__main__':
    parser = OptionParser(usage='usage: %prog [options]')
    parser.add_option('--host', dest='host', default='127.0.0.1',
                      help='service host (default: %default)', metavar='HOST')
    parser.add_option('--port', dest='port', default=8085,
                      help='service port (default: %default)', metavar='PORT')
    parser.add_option('-i', '--image', dest='image_path',
                      help='upload an image specified by PATH', metavar='PATH')
    parser.add_option('-u', '--url', dest='image_url',
                      help='fetch and upload an image from specified URL',
                      metavar='URL')
    parser.add_option('-d', '--delete', action='append', dest='image_delete',
                      help=('delete remote image specified by PATH, multiple '
                            '-d options can be specified'),
                      metavar='PATH')
    parser.add_option('-m', '--move', action='append', dest='image_move',
                      help=('move remote image specified by SRC_PATH to '
                            'DST_PATH, multiple -m options can be specified'),
                      metavar='"SRC_PATH DST_PATH"')
    parser.add_option('--remote-path', dest='image_remote_path',
                      help='force uploaded file path', metavar='PATH')
    parser.add_option('--size', action='append', dest='image_size',
                      help=('resize uploaded file and add the given suffix to '
                            'file name, if format or composite/crop is given '
                            '(optional), the appropriate global options are '
                            'ignored, multiple --size options can be '
                            'specified'),
                      metavar=('"SUFFIX WIDTH HEIGHT [FORMAT] '
                              '[composite|crop]"'))
    parser.add_option('--format', dest='image_format',
                      help='force uploaded file format', metavar='FORMAT')
    parser.add_option('--composite', action='store_true',
                      dest='image_composite', default=False, help=(
                      'when resizing match the image dimension to specified '
                      'size with a transparent background (gif and png only)'))
    parser.add_option('--crop', action='store_true', dest='image_crop',
                      default=False, help=(
                      'when resizing match the image dimension to specified '
                      'size with cropping the excess parts'))

    (options, args) = parser.parse_args()

    if not options.host or not options.port or (
            not options.image_path and not options.image_url and
            not options.image_delete and not options.image_move):
        parser.print_help()
        sys.exit(1)

    local_path = options.image_path
    if options.image_url:
        local_path = urllib.urlretrieve(options.image_url)[0]

    xmlrpc = xmlrpclib.ServerProxy(
        'http://' + options.host + ':' + str(options.port) + '/',
        allow_none=1)

    if local_path:
        remote_path = os.path.basename(local_path)
        if options.image_url:
            remote_path = options.image_url.split('/')[-1]
        if options.image_remote_path:
            remote_path = options.image_remote_path

        fmt = None
        if options.image_format:
            fmt = options.image_format

        composite = 0
        if options.image_composite:
            composite = 1

        crop = 0
        if options.image_crop:
            crop = 1

        size = None
        multi_format = None
        multi_composite = None
        multi_crop = None

        if options.image_size:
            size = {}
            multi_format = {}
            multi_composite = {}
            multi_crop = {}
            for image_size in options.image_size:
                params = re.split('\s+', image_size)
                size[params[0]] = [params[1], params[2]]

                if len(params) > 3:
                    multi_format[params[0]] = params[3]

                if len(params) > 4:
                    if params[4] == 'composite':
                        multi_composite[params[0]] = 1
                    if params[4] == 'crop':
                        multi_crop[params[0]] = 1

        if multi_format:
            fmt = multi_format

        if multi_composite:
            composite = multi_composite

        if multi_crop:
            crop = multi_crop

        image = cStringIO.StringIO()
        base64.encode(open(local_path, 'r'), image)

        print "xmlrpc.store_image(..., %s, %s, %s, %s, %s)" % (
            repr(remote_path), repr(fmt), repr(size), repr(composite),
            repr(crop))
        print xmlrpc.store_image(image.getvalue(), remote_path, fmt, size,
                                 composite, crop)

    elif options.image_delete:
        remote_path = options.image_delete
        print "xmlrpc.delete_image(%s)" % repr(remote_path)
        print xmlrpc.delete_image(remote_path)

    elif options.image_move:
        remote_src_path = []
        remote_dst_path = []

        for image_move in options.image_move:
            (src_path, dst_path) = re.split('\s+', image_move)
            remote_src_path.append(src_path)
            remote_dst_path.append(dst_path)

        print "xmlrpc.move_image(%s, %s)" % (repr(remote_src_path),
                                             repr(remote_dst_path))
        print xmlrpc.move_image(remote_src_path, remote_dst_path)
