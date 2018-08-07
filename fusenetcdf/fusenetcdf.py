#!/usr/bin/env python

"""
Exploring ideas for ESoWC project:
https://github.com/dvalters/fuse-netcdf
"""

import os
import sys
import netCDF4 as ncpy
import re
import time
import numpy
import inspect
import argparse
import logging as log
from fuse import FUSE, FuseOSError, Operations
from errno import EACCES, ENOENT


class InternalError(Exception):
    pass


class NotFoundError(Exception):
    pass


def memoize(function):
    """
    Caching decorator; caches return
    values of the decorated function.
    """
    memo = {}

    def wrapper(*args):
        if args in memo:
            return memo[args]
        else:
            rv = function(*args)
            memo[args] = rv
            return rv
    return wrapper


def write_to_string(string, buf, offset):
    """
    Implements someting like string[offset:offset+len(buf)] = buf
    (which is not be possible as strings are immutable).
    """
    string = list(string)
    buf = list(buf)
    string[offset:offset+len(buf)] = buf
    return ''.join(string)


#
# Data Representation plugins
#


class VardataAsBinaryFiles(object):

    def __init__(self):
        pass

    def size(self, variable):
        """ Return size (in bytes) of data representation """
        return len(self(variable))

    @memoize
    def __call__(self, variable):
        """ Return Variable's data representation """
        data = variable[:].tobytes()
        return data


class VardataAsFlatTextFiles(object):

    def __init__(self, fmt='%f'):
        self._fmt = fmt

    def size(self, variable):
        """ Return size (in bytes) of data representation """
        return len(self(variable))

    @memoize
    def __call__(self, variable):
        """ Return Variable's data representation """
        return ''.join(numpy.char.mod(
            '{}\n'.format(self._fmt), variable[:].flatten()))


class AttributesAsTextFiles(object):

    def __init__(self):
        pass

    def size(self, attr):
        return len(self(attr))

    def __call__(self, attr):
        """ Return array of bytes representing attribute's value """
        s = str(attr)
        # do not append a newline if attribute is
        # empty or if it already ends with a newline
        if not s or s[-1] == '\n':
            return s
        return s + '\n'


#
# NetCDF filesystem implementation
#

class NCFS(object):
    """
    Main object for netCDF-filesytem operations
    """
    def __init__(self, dataset, vardata_repr, attr_repr):
        self.dataset = dataset
        # plugin for generating Variable's data representations
        self.vardata_repr = vardata_repr
        # plugin for generation Atributes representations
        self.attr_repr = attr_repr
        # store mount time, for file timestamps
        self.mount_time = time.time()

    def is_var_dir(self, path):
        """ Test if path is a valid Variable directory path """
        return re.search('^/[^/]+$', path) is not None

    def is_var_data(self, path):
        """ Test if path is a vaild path to Variable data representation
            TODO: data representation could be a file or a directory.
        """
        dirname, basename = os.path.split(path)
        return self.is_var_dir(dirname) and basename == 'DATA_REPR'

    def is_var_dimensions(self, path):
        """ Test if path is a valid path for Variable's 'dimensions' file """
        dirname, basename = os.path.split(path)
        return self.is_var_dir(dirname) and basename == 'dimensions'

    def is_var_attr(self, path):
        """ Test if path is a valid path for Variable's Attribute """
        if '.Trash' in path:
            return False
        if re.search('^/[^/]+/[^/]+$', path) is not None:
            return not (self.is_var_data(path) or self.is_var_dimensions(path))

    def exists(self, path):
        """ Test if path exists """
        if (self.is_var_dir(path) or
                self.is_var_data(path) or
                self.is_var_dimensions(path)):
            return self.get_variable(path) is not None
        elif self.is_var_attr(path):
            return self.get_var_attr(path) is not None
        elif path == '/':
            return True
        else:
            return False

    def is_dir(self, path):
        """ Test if path corresponds to a directory-like object """
        return self.is_var_dir(path) or path == '/'

    def is_blacklisted(self, path):
        """ Test if a special file/directory """
        return '.Trash' in path

    def is_file(self, path):
        """ Test if path corresponds to a file-like object """
        return not self.is_dir(path)

    def get_varname(self, path):
        """
        Return NetCDF variable name, given its path.
        The path can be variable, attribute, data repr or dimensions path
        """
        return path.lstrip('/').split('/', 1)[0]

    def get_attrname(self, path):
        """ Return attribute name, given its path """
        return path.split('/')[-1]

    def get_variable(self, path):
        """ Return NetCDF Variable object, given its path, or None """
        varname = self.get_varname(path)
        return self.dataset.variables.get(varname, None)

    def get_var_attr(self, path):
        """ Return NetCDF Attribute object, given its path, or None """
        varname = self.get_varname(path)
        attrname = self.get_attrname(path)
        var = self.dataset.variables.get(varname, None)
        if var is None:
            return None
        try:
            return var.getncattr(attrname)
        except AttributeError:
            return None

    def set_var_attr(self, path, value):
        """
        Set value of an attribute, given it's path.
        If attribute doesn't exist it will be created.
        """
        attrname = self.get_attrname(path)
        var = self.get_variable(path)
        var.setncattr(attrname, value)

    def del_var_attr(self, path):
        attrname = self.get_attrname(path)
        var = self.get_variable(path)
        var.delncattr(attrname)

    def getncAttrs(self, path):
        """ Return name of NetCDF attributes, given variable's path """
        varname = self.get_varname(path)
        attrs = self.dataset.variables[varname].ncattrs()
        return [attr for attr in attrs]

    @classmethod
    def makeIntoDir(cls, statdict):
        """Update the statdict if the item in the VFS should be
        presented as a directory
        """
        statdict["st_mode"] = statdict["st_mode"] ^ 0o100000 | 0o040000
        for i in [[0o400, 0o100], [0o40, 0o10], [0o4, 0o1]]:
            if (statdict["st_mode"] & i[0]) != 0:
                statdict["st_mode"] = statdict["st_mode"] | i[1]
        return statdict

    def getattr(self, path):
        """The getattr callback is in charge of reading the metadata of a
            given path, this callback is always called before any operation
            made on the filesystem.

        We are telling FUSE that the current entry is a file
        or a directory using the stat struct.
        In general, if the entry is a directory, st_mode have to be set
        to S_IFDIR and st_nlink to 2, while if it is a file, st_mode have
        to be set to S_IFREG (that stands for regular file) and st_nlink
        to 1. Files also require that the st_size (the full file size) is
        specified.
        """
        # default attributes, correspond to a regular file
        statdict = dict(
                st_atime=self.mount_time,
                st_ctime=self.mount_time,
                st_gid=os.getgid(),
                st_mode=33188,  # file
                st_mtime=self.mount_time,
                st_nlink=1,
                st_size=4096,
                st_uid=os.getuid())
        if path == "/":
            statdict = self.makeIntoDir(statdict)
        elif self.is_blacklisted(path):
            return statdict
        elif not self.exists(path):
            log.debug('getattr: %s does not exist' % path)
            raise FuseOSError(ENOENT)
        elif self.is_var_dir(path):
            statdict = self.makeIntoDir(statdict)
            statdict["st_size"] = 4096
        elif self.is_var_attr(path):
            attr = self.get_var_attr(path)
            statdict["st_size"] = self.attr_repr.size(attr)
        elif self.is_var_data(path):
            var = self.get_variable(path)
            statdict["st_size"] = self.vardata_repr.size(var)
        else:
            # this should never happen
            raise InternalError('getattr: unexpected path {}'.format(path))
        return statdict

    def getxattr(self, name):
        """ for now it is fake """
        return 'foo'

    def removexattr(self, name):
        return 0

    def readdir(self, path):
        """Overrides readdir.
        Called when ls or ll and any other unix command that relies
        on this operation to work.
        """
        path = path.lstrip("/")
        if path == "":
            # Return a list of netCDF variables
            return (['.', '..'] + [item.encode('utf-8')
                    for item in self.dataset.variables])
        elif path in self.dataset.variables:
            local_attrs = self.getncAttrs(path)
            return ['.', '..'] + local_attrs + ["DATA_REPR"]
        else:
            return ['.', '..']

    def access(self, mode):
        if self.dataset_file is not None:
            path = self.dataset_file
            # If we can execute it, we should be able to read it too
            if mode == os.X_OK:
                mode = os.R_OK
        if not os.access(path, mode):
            raise FuseOSError(EACCES)

    def open(self, path, flags):
        if not self.is_file(path):
            return ENOENT
        return 0

    def read(self, path, size, offset):
        if self.is_var_attr(path):
            attr = self.get_var_attr(path)
            return self.attr_repr(attr)[offset:offset+size]
        elif self.is_var_data(path):
            var = self.get_variable(path)
            return self.vardata_repr(var)[offset:offset+size]
        else:
            raise InternalError('read(): unexpected path %s' % path)

    def create(self, path, mode):
        if self.is_var_attr(path):
            self.set_var_attr(path, '')
        else:
            raise InternalError('create(): unexpected path %s' % path)
        return 0

    def write(self, path, buf, offset, fh=0):
        if self.is_var_attr(path):
            attr = self.get_var_attr(path)
            attr = write_to_string(attr, buf, offset)
            self.set_var_attr(path, attr)
            return len(buf)
        else:
            raise InternalError('write(): unexpected path %s' % path)

    def unlink(self, path):
        if self.is_var_attr(path):
            self.del_var_attr(path)
        else:
            raise InternalError('unlink(): unexpected path %s' % path)
        return 0

    def close(self, fh):
        pass


class NCFSOperations(Operations):
    """Inherit from the base fusepy Operations class"""

    def __getattribute__(self, name):
        """ Intercept and print all method calls """
        attr = object.__getattribute__(self, name)
        if hasattr(attr, '__call__'):
            def newfunc(*args, **kwargs):
                func_args = [repr(x) for x in args]
                func_kwargs = ['{}={}'.format(k, repr(v)) for k, v in kwargs]
                func_args.extend(func_kwargs)
                # print  name of the function and argument values
                log.debug('{}({})'.format(name, ', '.join(func_args)))
                result = attr(*args, **kwargs)
                # print return value
                # log.debug('{}() returned {}'.format(name, repr(result)))
                return result
            return newfunc
        else:
            return attr

    def __init__(self, ncfs):
        self.ncfs = ncfs

    """These are the fusepy module methods that are overridden
    in this class. Any method not overridden here means that
    the default fusepy API method will be used.

    (See the fusepy.Operations class)

    Note these are not exactly the same as the C libs for FUSE

    """
    def acccess(self, path, mode):
        self.ncfs.access(mode)

    def read(self, path, size, offset, fh):
        return self.ncfs.read(path, size, offset)

    def write(self, path, data, offset):
        return self.ncfs.write(path, data, offset)

    def getattr(self, path, fh=None):
        return self.ncfs.getattr(path)

    def getxattr(self, path, name):
        return self.ncfs.getxattr(name)

    def removexattr(self, path, name):
        return self.ncfs.removexattr(name)

    def listxattr(self, path):
        return self.ncfs.listxattr()

    def readdir(self, path, fh):
        return self.ncfs.readdir(path)

    def release(self, path, fh):
        return self.ncfs.close(fh)

    def statfs(self, path):
        # Need to think about this one some more...
        stv = os.statvfs(path)
        return dict(
            (key, getattr(stv, key)) for key in (
             'f_bavail', 'f_bfree',
             'f_blocks', 'f_bsize', 'f_favail', 'f_ffree', 'f_files',
             'f_flag', 'f_frsize', 'f_namemax'))

    def open(self, path, flags):
        return self.ncfs.open(path, flags)

    def create(self, path, mode):
        return self.ncfs.create(path, mode)

    def write(self, path, buf, offset, fh):
        return self.ncfs.write(path, buf, offset, fh)

    def truncate(self, path, offset):
        return 0

    def unlink(self, path):
        return self.ncfs.unlink(path)

    def write_buf(self, path, buf, off, fh):
        return 0

    """
    rename = None
    symlink = None
    setxattr = None
    removexattr = None
    link = None
    mkdir = None
    mknod = None
    rmdir = None
    chmod = None
    chown = None
    create = None
    fsync = None
    flush = None
    """


def main():
    """
    This function is our Composition Root & we are using Pure DI (a.k.a.
    Poor Man's DI) - Ideally, this is the only place where we create all
    objects and wire everything together. This is the only place where
    global config params and commandline params/options are needed.

    http://blog.ploeh.dk/2011/07/28/CompositionRoot/ - great stuff
    on how to keep everything decoupled and write unit-testable code.
    """

    # Read config file, commandline parameters, options

    parser = argparse.ArgumentParser(
            description='Mount NetCDF filesystem',
            prog='fusenetcdf')

    parser.add_argument(
            dest='ncpath',
            metavar='PATH',
            help='NetCDF file to be mounted')

    parser.add_argument(
            dest='mountpoint',
            metavar='DIR',
            help='mount point directory (must exist)')

    parser.add_argument(
            '-v',
            dest='verbosity_level',
            action='count',
            default=0,
            help='be verbose (-vv for debug messages)')

    cmdline = parser.parse_args()

    # setup logging

    if cmdline.verbosity_level == 0:
        loglevel = log.ERROR
    elif cmdline.verbosity_level == 1:
        loglevel = log.INFO
    else:
        loglevel = log.DEBUG
    log.basicConfig(format='%(message)s', level=loglevel)

    # build the application

    # open file for reading and writing
    dataset = ncpy.Dataset(cmdline.ncpath, 'r+')
    # create plugins for generating data and atribute representations
    vardata_repr = VardataAsFlatTextFiles(fmt='%f')
    attr_repr = AttributesAsTextFiles()
    # create main object implementing NetCDF filesystem functionality
    ncfs = NCFS(dataset, vardata_repr, attr_repr)
    # create FUSE Operations (does it need to be a separate class?)
    ncfs_operations = NCFSOperations(ncfs)
    # launch!
    FUSE(ncfs_operations, cmdline.mountpoint, nothreads=True, foreground=True)


if __name__ == "__main__":
    main()
