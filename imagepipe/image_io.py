# -*- coding: utf-8 -*-

"""Image handling functions"""

import os
import shutil
import subprocess

from twisted.python import log
import unidecode


class Error(Exception):
    """Base class for processing errors"""
    pass


class ImageMagickError(Error):
    """Indicates imagemagick call failures"""
    pass


def _append_frame(input_path, output_path, fmt):
    """Append frame selection to input if output is not a gif"""
    if os.path.splitext(output_path)[1] != '.gif' and fmt != 'gif':
        # First frame only
        return input_path + "[0]"
    else:
        return input_path


def _resize_magick(convert, input_path, output_path, dimension=None, fmt=None):
    """Assemble convert command

    This command resizes the input but keeps the original aspect ratio.
    """
    input_path = _append_frame(input_path, output_path, fmt)
    cmd = [convert, input_path]
    if dimension:
        cmd.append("-resize")
        cmd.append("%dx%d>" % (dimension[0], dimension[1]))
    if fmt:
        cmd.append("%s:%s" % (fmt, output_path))
    else:
        cmd.append(output_path)
    return cmd


def _composite_magick(convert, input_path, output_path, dimension, fmt=None):
    """Assemble convert command

    This command overlaps input over a transparent image to both keep the
    original aspect ratio and conform with the given dimension.
    """
    input_path = _append_frame(input_path, output_path, fmt)
    cmd = [convert, "-size",
           ("%dx%d" % (dimension[0], dimension[1])),
           "xc:none", "null:", input_path, "-resize",
           ("%dx%d>" % (dimension[0], dimension[1])),
           "-gravity", "center", "-layers", "composite"]
    if fmt:
        cmd.append("%s:%s" % (fmt, output_path))
    else:
        cmd.append(output_path)
    return cmd


def _crop_magick(convert, input_path, output_path, dimension, fmt=None):
    """Assemble convert command

    This command crops the image to the given dimension but keeps the original
    aspect ratio.
    """
    input_path = _append_frame(input_path, output_path, fmt)
    cmd = [convert, input_path, "-resize",
           ("%dx%d^" % (dimension[0], dimension[1])),
           "-gravity", "center", "-crop",
           ("%dx%d+0+0!" % (dimension[0], dimension[1])),
           "+repage"]
    if fmt:
        cmd.append("%s:%s" % (fmt, output_path))
    else:
        cmd.append(output_path)
    return cmd


def _imagemagick_convert(blob, magick, env):
    """Execute imagemagick's convert with the specified parameters"""
    log.msg(" ".join(magick))
    process = subprocess.Popen(magick, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               close_fds=True, env=env)
    stderr = process.communicate(blob)[1]
    if process.returncode != 0:
        if stderr:
            message = unidecode.unidecode(stderr).strip()
            raise ImageMagickError(message)
        else:
            raise ImageMagickError()


def normalize_path(path, starts_with=None):
    """Collapses redundant separators and up-level references

    The starts_with argument can be provided to check if a path is relative to
    a given prefix. If it is not None is returned.
    """
    path = os.path.normpath(path)
    if starts_with and not path.startswith(starts_with):
        return None
    return path


def create_dirs(path):
    """Create the directory given by path with all intermediate ones"""
    if path and not os.path.isdir(path):
        os.makedirs(path)


def store(blob, path, fmt=None, dimension=None, composite=None, crop=None,
          umask=None, convert='/usr/bin/convert', env=None):
    """Store the image on disk

    This pipes the image blob through one of the available imagemagick's
    convert calls depending on the requested transformations or writes it
    directly if no transformations were requested.
    """
    if umask != None:
        previous_umask = os.umask(umask)
    else:
        previous_umask = None

    try:
        create_dirs(os.path.dirname(path))

        if composite:
            _imagemagick_convert(
                blob, _composite_magick(convert, '-', path, dimension, fmt),
                env)
        elif crop:
            _imagemagick_convert(
                blob, _crop_magick(convert, '-', path, dimension, fmt), env)
        elif fmt or dimension:
            _imagemagick_convert(
                blob, _resize_magick(convert, '-', path, dimension, fmt), env)
        else:
            image = open(path, 'wb')
            image.write(blob)
            image.close()
    finally:
        if previous_umask:
            os.umask(previous_umask)


def delete(path):
    """Delete image from disk"""
    try:
        os.unlink(path)
    except OSError:
        pass


def move(src_path, dst_path, umask=None):
    """Move image from source to destination"""
    if umask != None:
        previous_umask = os.umask(umask)
    else:
        previous_umask = None

    try:
        create_dirs(os.path.dirname(dst_path))
        shutil.move(src_path, dst_path)
    finally:
        if previous_umask:
            os.umask(previous_umask)
