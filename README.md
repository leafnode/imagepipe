imagepipe
=========

This is a XML-RPC service for storing and resizing images on the fly.

It is implemented using the Twisted framework and supports replication with
the help of ZeroMQ. Images are resized using ImageMagick's convert tool.

This service can be deployed on multiple servers and combined with a HTTP
server to create a high-availability image serving cluster.


Requirements
============

    pip install configobj
    pip install Twisted
    pip install Unidecode
    pip install pyzmq  # requires libzmq from http://www.zeromq.org
    pip install txZMQ

For Debian:

    aptitude install python-configobj
    aptitude install python-twisted
    aptitude install python-unidecode  # wheezy
    aptitude install libzmq-dev  # squeeze-backports, wheezy
    aptitude install python-zmq  # wheezy
    pip install txZMQ


Running
=======

    python setup.py install
    cp imagepipe.ini.dist imagepipe.ini
    twistd -n imagepipe -c imagepipe.ini


Configuration
=============

The following parameters can be set in the configuration file:

    [network]
    # The network interface and port to listen on for XML-RPC calls
    interface = 0.0.0.0
    port = 8085
    
    [replication]
    # Where should other instances connect to replicate data from this one
    publish = tcp://0.0.0.0:8086
    # publish = ipc:///tmp/imagepipe.sock
    
    # Where should this instance connect to replicate data from another one
    # subscribe = tcp://127.0.0.1:9086
	
    [images]
    # The root path for stored images
    path = /tmp
	
    # Umask applied on the created images and intermediate directories
    umask = 18 #0022
	
    # Number of threads performing image manipulations (convert instances)
    io_threads = 1
	
    [imagemagick]
    convert = /usr/bin/convert
    # See http://www.imagemagick.org/script/resources.php#environment
    [[env]]
    MAGICK_THREAD_LIMIT = 1
    MAGICK_TIME_LIMIT = 60


Requests
========

Storing images
--------------

    store_image(image, path, fmt=None, size=None, composite=0, crop=0)
        
    image -- image data, encoded in base64
    path -- destination path, relative to images.path from configuration
    fmt -- format of the destination image, e.g. 'png', 'gif'
    size -- size of the destination image, [width, height]
    composite -- set to 1 if destination image should be resized and
                 overlapped over transparent one to both conform with the
                 size specification and keep the original aspect ratio
    crop -- set to 1 if destination image should be cropped to conform with
            the size specification

The below arguments will result in storing a single image resized to 500x500px.

    path = 'x/y/z/image.jpg'
    size = [500, 500]

Multiple versions of the same image can be stored at once by providing a
dictionary in the place of the size argument. Consider the following example:

    path = 'x/y/z/image.jpg'
    size = {'': [500, 500],  # no suffix
            '_medium': [250, 250],
            '_small': [50, 50]}

This will result in creation of three images:

    x/y/z/image.jpg, 500x500px
    x/y/z/image_medium.jpg, 250x250px
    x/y/z/image_small.jpg, 50x50px

A dictionary can also be provided in the place of format, composite and crop
arguments. The keys must equal the ones from the size dictionary. If single
values are provided they affect all created images.

Deleting images
---------------

    delete_image(path)
	
    path -- path of the image or a list of paths

Moving images
-------------

    move_image(src_path, dst_path)
	
    src_path -- the source path or a list of paths
    dst_path -- the destination path or a list of paths

In case of multiple paths both lists must equal in length.


Resize methods
==============

All of the resize methods retain the original aspect ratio but each one
produces a different image.

By default the following ImageMagick arguments are used:

    convert INPUT -resize WIDTHxHEIGHT> OUTPUT

Only the longest dimension will conform to the required width or height,
depending on the size of the input image.

Composition can be used to force the required dimensions:

    convert -size WIDTHxHEIGHT xc:none null: INPUT -resize WIDHTxHEIGHT> -gravity center -layers composite OUTPUT

This will overlap the resized image over a transparent one. Obviously this
works only if the output is formatted as GIF or PNG.

Cropping can also be used to force the required dimensions but does so by
removing excessive parts of the image after resizing.

    convert INPUT -resize WIDTHxHEIGHT^ -gravity center -crop WIDHTxHEIGHT+0+0! +repage OUTPUT


Performance overview
====================

Benchmarks show that modifying MAGICK_THREAD_LIMIT has no significant impact
on conversion speedup. But it can slow down conversion if multiple images are
processed concurrently.

High concurrency rates can be achieved by setting MAGICK_THREAD_LIMIT to 1 and
increasing io_threads instead. Setting io_threads to match the number of cpu
cores available to the system is a good starting point.
