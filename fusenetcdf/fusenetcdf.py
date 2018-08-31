#!/usr/bin/env python

"""
Represent and manipulate contents of a NetCDF dataset
using a filesystem metaphor.

https://github.com/dvalters/fuse-netcdf

Developed during ECMWF Summer of Weather Code (2018).
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


class DimNamesAsTextFiles(object):

    def __init__(self, sep='\n'):
        self._sep = sep

    def size(self, dimnames):
        return len(self.encode(dimnames))

    def encode(self, dimnames):
        """ Return text representation of a list of dimension names"""
        s = self._sep.join(dimnames)
        if not s or s[-1] == '\n':
            return s
        return s + '\n'

    def decode(self, dimnames_repr):
        """ Convert text representation back to data """
        if not dimnames_repr:
            return []
        return dimnames_repr.strip().split(self._sep)


#
# NetCDF filesystem implementation
#

class NCFS(object):
    """
    Main object for netCDF-filesytem operations
    """
    def __init__(self, dataset, vardata_repr, attr_repr, dimnames_repr):
        self.dataset = dataset
        # plugin for generating Variable's data representations
        self.vardata_repr = vardata_repr
        # plugin for generation Atributes representations
        self.attr_repr = attr_repr
        # plugin for generating a list of variable's dimensions
        self.dimnames_repr = dimnames_repr
        # store mount time, for file timestamps
        self.mount_time = time.time()

    def is_var_dir(self, path):
        """ Test if path is a valid Variable directory path """
        potential_vardir = self.get_varname(path)
        # Don't return True if it is a Global Attribute
        if potential_vardir not in self.getncGlobalAttrs():
            return re.search('^/[^/]+$', path) is not None
        else:
            return False

    def is_var_data(self, path):
        """ Test if path is a vaild path to Variable data representation
            TODO: data representation could be a file or a directory.
        """
        dirname, basename = os.path.split(path)
        return self.is_var_dir(dirname) and basename == 'DATA_REPR'

    def is_var_dimensions(self, path):
        """ Test if path is a valid path for Variable's 'DIMENSIONS' file """
        dirname, basename = os.path.split(path)
        return self.is_var_dir(dirname) and basename == 'DIMENSIONS'

    def rename_dim_and_dimvar(self, old_name, new_name):
        if new_name == old_name:
            return
        self.dataset.renameDimension(old_name, new_name)
        try:
            # rename Dimension Variable (if exists)
            self.dataset.renameVariable(old_name, new_name)
        except KeyError:
            pass

    def rename_dims_and_dimvars(self, old_names, new_names):
        """ Rename dimensions and corresponding dimension variables """
        # number of dimensions should remain the same; if it is
        # different, print warning message and abort renaming.
        if len(old_names) != len(new_names):
            log.warn("number of dimensions of a variable cannot change")
            raise ValueError(
                    'old and new dimension list must have the same lenght')
        # Simulate renaming to check if it results in duplicates.
        # This would cause NetCDF to abort; instead we cancel renaming.
        # We also add temporary prefix to dimension names
        # - otherwise SWAPPING dimension names would not work.
        # Maybe there's a better way to do it...
        dimnames = [x for x in self.dataset.dimensions]
        for old in old_names:
            dimnames = [
                    'RENAMING_' + x if x == old else x for x in dimnames]
        old_names_tmp = ['RENAMING_' + x for x in old_names]
        for old, new in zip(old_names_tmp, new_names):
            dimnames = [new if x == old else x for x in dimnames]
        # Check for duplicates; abort renaming if duplicates found
        if len(dimnames) != len(set(dimnames)):
            raise ValueError(
                    'renaming would result in duplicated dimension names')
        # Renaming is safe - do it.
        for old in old_names:
            self.rename_dim_and_dimvar(old, 'RENAMING_' + old)
        for old, new in zip(old_names_tmp, new_names):
            self.rename_dim_and_dimvar(old, new)

    def is_var_attr(self, path):
        """ Test if path is a valid path for Variable's Attribute """
        if '.Trash' in path:
            return False
        if re.search('^/[^/]+/[^/]+$', path) is not None:
            return not (self.is_var_data(path) or self.is_var_dimensions(path))

    def is_global_attr(self, path):
        """ Test if path is a valid path for a Dataset's Global Attributes"""
        potential_glob_attr = self.get_global_attr_name(path)
        log.debug("Checking if global attr: {}".format(potential_glob_attr))
        # if potential_glob_attr in self.getncGlobalAttrs():
        if potential_glob_attr not in self.getncVariables():
            log.debug("Checking if global attr {} in Dataset".format(
                      potential_glob_attr))
            return re.search('^/[^/]+$', path) is not None
        else:
            return False

    def exists(self, path):
        """ Test if path exists """
        if (self.is_var_dir(path) or
                self.is_var_data(path) or
                self.is_var_dimensions(path)):
            return self.get_variable(path) is not None
        elif self.is_global_attr(path):
            log.debug("Exists method: Checking glob attr {}".format(path))
            return self.get_global_attr(path) is not None
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

    @classmethod
    def get_varname(cls, path):
        """
        Return NetCDF variable name, given its path.
        The path can be variable, attribute, data repr or dimensions path
        """
        return path.lstrip('/').split('/', 1)[0]

    @classmethod
    def get_global_attr_name(cls, path):
        """
        Return NetCDF global attribute name, given its path.
        The path can be variable, attribute, data repr or dimensions path
        """
        return path.lstrip('/').split('/', 1)[0]

    @classmethod
    def get_attrname(cls, path):
        """ Return attribute name, given its path """
        return path.split('/')[-1]

    def get_variable(self, path):
        """ Return NetCDF Variable object, given its path, or None """
        varname = self.get_varname(path)
        return self.dataset.variables.get(varname, None)

    def get_global_attr(self, path):
        """Return global attribute"""
        global_attr_name = self.get_global_attr_name(path)
        try:
            return self.dataset.getncattr(global_attr_name)
        except AttributeError:
            return None

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

    def get_var_dimnames(self, path):
        """ Return NetCDF Variable Dimensions """
        varname = self.get_varname(path)
        var = self.dataset.variables.get(varname, None)
        if var is None:
            return None
        return var.dimensions

    def set_var_attr(self, path, value):
        """
        Set value of an attribute, given it's path.
        If attribute doesn't exist it will be created.
        """
        stripped_value = value.rstrip()  # \n should be stripped by default
        attrname = self.get_attrname(path)
        var = self.get_variable(path)
        var.setncattr(attrname, stripped_value)

    def set_global_attr(self, path, value):
        stripped_value = value.rstrip()  # \n should be stripped by default
        glob_attrname = self.get_global_attr_name(path)
        self.dataset.setncattr(glob_attrname, stripped_value)

    def del_var_attr(self, path):
        attrname = self.get_attrname(path)
        var = self.get_variable(path)
        var.delncattr(attrname)

    def del_global_attr(self, path):
        glob_attr_name = self.get_global_attr_name(path)
        self.dataset.delncattr(glob_attr_name)

    def getncVariables(self):
        """ Return the names of NetCDF variables in the file"""
        return [item.encode('utf-8') for item in self.dataset.variables]

    def getncAttrs(self, path):
        """ Return name of NetCDF attributes, given variable's path """
        varname = self.get_varname(path)
        attrs = self.dataset.variables[varname].ncattrs()
        return [attr for attr in attrs]

    def getncGlobalAttrs(self):
        """ Return a list of the Dataset's global attributes"""
        glob_attrs = self.dataset.ncattrs()
        return [glob_attr.encode('utf-8') for glob_attr in glob_attrs]

    def rename_var_attr(self, old, new):
        """ Renames a variable attribute """
        cur_var = self.get_variable(old)
        # print cur_var
        old_attr_name = self.get_attrname(old)
        new_attr_name = self.get_attrname(new)
        cur_var.renameAttribute(old_attr_name, new_attr_name)

    def rename_global_attr(self, old, new):
        """ Renames a global attribute """
        old_attr_name = self.get_global_attr_name(old)
        new_attr_name = self.get_global_attr_name(new)
        self.dataset.renameAttribute(old_attr_name, new_attr_name)

    def rename_variable(self, old, new):
        """Renames a variale (i.e. a directory)"""
        # cur_var = self.get_variable(old)
        # print(cur_var)
        old_var_name = self.get_varname(old)
        new_var_name = self.get_varname(new)
        self.dataset.renameVariable(old_var_name, new_var_name)
        # if this is a Dimension Variable,
        # also rename corresponding dimension
        if old_var_name in self.dataset.dimensions:
            self.dataset.renameDimension(old_var_name, new_var_name)

    def set_variable(self, newvariable):
        """Creates a variable in the dataset if it does not exist"""
        self.dataset.createVariable(newvariable, datatype='i')

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
        elif self.is_global_attr(path):
            # make sensible statdict entry for global attrs
            global_attr = self.get_global_attr(path)
            statdict["st_size"] = self.attr_repr.size(global_attr)
        elif self.is_var_dimensions(path):
            dimnames = self.get_var_dimnames(path)
            statdict["st_size"] = self.dimnames_repr.size(dimnames)
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
        # If we are in the top-level directory of the mountpoint:
        if path == "":
            # Get a list of netCDF variables and the global attrs
            all_variables = self.getncVariables()
            global_attributes = self.getncGlobalAttrs()
            return (['.', '..'] + all_variables + global_attributes)
        # If we are in a variable directory
        elif path in self.dataset.variables:
            local_attrs = self.getncAttrs(path)
            return ['.', '..'] + local_attrs + ["DATA_REPR"] + ["DIMENSIONS"]
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
        elif self.is_global_attr(path):
            glob_attr = self.get_global_attr(path)
            return self.attr_repr(glob_attr)[offset:offset+size]
        elif self.is_var_data(path):
            var = self.get_variable(path)
            return self.vardata_repr(var)[offset:offset+size]
        elif self.is_var_dimensions(path):
            dimnames = self.get_var_dimnames(path)
            return self.dimnames_repr.encode(dimnames)[offset:offset+size]
        else:
            raise InternalError('read(): unexpected path %s' % path)

    def create(self, path, mode):
        if self.is_var_attr(path):
            self.set_var_attr(path, '')
        elif self.is_global_attr(path):
            self.set_global_attr(path, '')
        else:
            raise InternalError('create(): unexpected path %s' % path)
        return 0

    def mkdir(self, path, mode):
        """Directories are variables in the ncfs"""
        log.debug("Attempting mkdir with %s" % path)
        if self.is_var_dir(path):
            log.debug("is_dir_true!")
            self.set_variable(path)   # pass data type here? (default is int)
        else:
            raise InternalError('Cannot create a variable (directory) here: %s'
                                % path)
        return 0

    def write(self, path, buf, offset, fh=0):
        if self.is_var_attr(path):
            attr = self.get_var_attr(path)
            attr = write_to_string(attr, buf, offset)
            self.set_var_attr(path, attr)
            return len(buf)
        elif self.is_global_attr(path):
            glob_attr = self.get_global_attr(path)
            glob_attr = write_to_string(glob_attr, buf, offset)
            self.set_global_attr(path, glob_attr)
            return len(buf)
        elif self.is_var_dimensions(path):
            old_dimnames = self.get_var_dimnames(path)
            # generate string representation of existing dimesion names
            new_dimnames_repr = self.dimnames_repr.encode(old_dimnames)
            # update (part of) string representation of dimension names
            new_dimnames_repr = write_to_string(new_dimnames_repr, buf, offset)
            # convert updated string representation back to list of names
            new_dimnames = self.dimnames_repr.decode(new_dimnames_repr)
            try:
                self.rename_dims_and_dimvars(old_dimnames, new_dimnames)
            except ValueError:
                # ignore invalid edit
                pass
            return len(buf)
        else:
            raise InternalError('write(): unexpected path %s' % path)

    @classmethod
    def truncate(cls, path, length, fh=None):
        """ Truncate a file that is being writtem to, i.e. when
        removing lines etc. Note that truncate is also called when
        the size of the file is being extended as well as shrunk"""
        return 0

    def rename(self, old, new):
        """
        Rename a component of a netcdf variable
        """
        # Rename a variable attribute
        if self.is_var_attr(old):
            self.rename_var_attr(old, new)
        # Rename a variable
        elif self.is_var_dir(old):
            self.rename_variable(old, new)
        elif self.is_global_attr(old):
            self.rename_global_attr(old, new)
        # Otherwise, inform that this is not implemented.
        else:
            raise InternalError('rename(): not implemented for this op on %s'
                                % old)
        return 0

    def unlink(self, path):
        if self.is_var_attr(path):
            self.del_var_attr(path)
        elif self.is_var_dir(path):
            raise InternalError('unlink(): does not support deleting variable')
        elif self.is_global_attr(path):
            self.del_global_attr(path)
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

    def rename(self, old, new):
        log.debug("RENAMING olditem: {}, newitem: {}".format(old, new))
        return self.ncfs.rename(old, new)

    def mkdir(self, path, mode):
        log.debug("CREATING directory: {}".format(path))
        return self.ncfs.mkdir(path, mode)

    @classmethod
    def truncate(cls, path, length, fh):
        """Used when shortening files etc. (I.e. removing lines) """
        return cls.ncfs.truncate(path, length, fh)
        # return 0

    def unlink(self, path):
        return self.ncfs.unlink(path)

    def write_buf(self, path, buf, off, fh):
        return 0
 
    @classmethod
    def chmod(cls, path, mode):
        return 0

    """
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
    # create plugins for generating data, atribute, dimension representations
    vardata_repr = VardataAsFlatTextFiles(fmt='%f')
    attr_repr = AttributesAsTextFiles()
    dimnames_repr = DimNamesAsTextFiles()
    # create main object implementing NetCDF filesystem functionality
    ncfs = NCFS(dataset, vardata_repr, attr_repr, dimnames_repr)
    # create FUSE Operations (does it need to be a separate class?)
    ncfs_operations = NCFSOperations(ncfs)
    # launch!
    FUSE(ncfs_operations, cmdline.mountpoint, nothreads=True, foreground=True)


if __name__ == "__main__":
    main()
