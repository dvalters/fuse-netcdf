#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fuse-netcdf project

This is the ESoWC project to create a mountable netcdf file
in user space using the fusepy and python-netcdf libraries

doc: http://www.ceda.ac.uk/static/media/uploads/ncas-reading-2015/
       10_read_netcdf_python.pdf

Thanks https://www.stavros.io/posts/python-fuse-filesystem/
https://github.com/libfuse/python-fuse

"""
from __future__ import with_statement, print_function

import os
import sys
import netCDF4
import netCDF4 as ncpy

from fuse import FUSE, FuseOSError, Operations
from threading import Lock
from errno import EACCES, ENOENT
DEBUG = True
DEBUG_LEVEL2 = False
# DEBUG = True


def attrs(name):
    cur = os.lstat(name)
    return dict((key, getattr(cur, key)) for key in (
        'st_size', 'st_gid', 'st_uid',
        'st_mode', 'st_mtime', 'st_atime', 'st_ctime', ))


def var_attr_name_to_str(var_attr_name, var):
    """Converts the attribute string to the variable attribute
    contents"""
    if var_attr_name == "scale_factor":
        return "%s\n" % var.scale_factor
    if var_attr_name == "add_offset":
        return "%s\n" % var.add_offset
    if var_attr_name == "units":
        return "%s\n" % var.units
    if var_attr_name == "long_name":
        return "%s\n" % var.long_name
    if var_attr_name == "missing_value":
        return "%s\n" % var.missing_value
    if var_attr_name == "_FillValue":
        return "%s\n" % var._FillValue
    return None


class NetCDFFUSE(Operations):
    """Inherit from the base fusepy Operations class

    This is a wrapper class that contains a subclass for
    mapping the netCDF file to filesystem operations.

    (There is probably a more elegant way of doing this
    - could be refactored lateer.)
    """

    def __init__(self, filerootdir):
        self.filerootdir = os.path.realpath(filerootdir)
        self.readwritelock = Lock()

    def __call__(self, operation, path, *args):
        return super(NetCDFFUSE, self).__call__(
            operation, self.filerootdir + path, *args)

    class NetCDFComponent:
        """
        Main object for performing operations on various
        NetCDF file components, e.g. variable, global attrs,
        variable attrs, etc.
        """
        def __init__(self, path):
            self.fullpath = path
            self.internalpath = "/"
            self.dataset_handle = None
            self.dataset_file = None
            self.ncVars = None

            # Check that there is a netCDF file
            if os.path.lexists(path):
                self.testNetCDF(path)
            else:
                components = path.split("/")
                for i in range(len(components), 0, -1):
                    test = "/".join(components[:i])
                    if self.testNetCDF(test):
                        self.internalpath = "/".join(
                            components[i - len(components):])
                        if DEBUG:
                            print(self.internalpath)
                        break
                        # Could handle this case better
                        # I think it can be done better with
                        # the os path methods

        def testNetCDF(self, path):
            """
            Check if the path is a netCDF file.
            """
            if os.path.isfile(path):
                try:
                    # Also test for netCDF version here?
                    self.dataset_handle = ncpy.Dataset(path, "r")
                    self.dataset_file = path
                    self.ncVars = self.getncVars(path)
                    if DEBUG_LEVEL2:
                        print(path + " is netCDF")
                        print(self.dataset_handle.dimensions.keys())
                        for key in self.dataset_handle.dimensions.keys():
                            print(self.dataset_handle.dimensions[key])
                        print(self.dataset_handle.variables.keys())
                        for key in self.dataset_handle.variables.keys():
                            var = self.dataset_handle.variables[key]
                            print(key, var)
                            print(var[:])
                    return True
                except AttributeError as e:
                    print(e)
                except RuntimeError as e:
                    print(e)
                except Exception as e:
                    print(e)
                    print(sys.exc_info()[0])
                return False

        def __del__(self):
            if self.dataset_handle is not None:
                try:
                    self.dataset_handle.close()
                except Exception as e:
                    # needs a better soln!
                    print(e)
                    pass

        @classmethod
        def makeIntoDir(cls, statdict):
            """Update the statdict if the item in the VFS should be
            presented as a directory
            """
            if DEBUG:
                print("#MSG: Making a statdict to create a folder structure!")
            statdict['st_mode'] = statdict['st_mode'] ^ 0o100000 | 0o040000
            for i in [[0o400, 0o100], [0o40, 0o10], [0o4, 0o1]]:
                if (statdict['st_mode'] & i[0]) != 0:
                    statdict['st_mode'] = statdict['st_mode'] | i[1]
            return statdict

        def getattr(self):
            """The getattr callback is in charge of reading the metadata of a
                given path, this callback is always called before any operation
                made on the filesystem.

            We are telling FUSE that the current entry is a file
            or a directory using the stat struct.
            In general, if the entry is a directory, st_mode have to be set
            to S_IFDIR and st_nlink to 2, while if it’s a file, st_mode have
            to be set to S_IFREG (that stands for regular file) and st_nlink
            to 1. Files also require that the st_size (the full file size) is
            specified.
            """
            if self.dataset_file is not None:
                st = os.lstat(self.dataset_file)
            else:
                st = os.lstat(self.fullpath)
            statdict = dict((key, getattr(st, key)) for key in
                            ('st_atime', 'st_ctime', 'st_gid', 'st_mode',
                             'st_mtime', 'st_nlink',
                             'st_size', 'st_uid'))
            if self.dataset_file is not None:
                if DEBUG:
                    print("NETCDF_FILE:    ", self.dataset_file)
                    print("INTERNALPATH: ", self.internalpath)
                if self.internalpath == "/":
                    if DEBUG:
                        print("at a filepath slash...")
                    statdict = self.makeIntoDir(statdict)
                elif self.internalpath == "":
                    if DEBUG:
                        print("WE ARE AT THE TOP: ", self.internalpath)
                    statdict = self.makeIntoDir(statdict)
                    statdict['st_size'] = 4096
                elif self.internalpath in self.ncVars:
                    if DEBUG:
                        print("WE ARE AT VARIABLE: ", self.internalpath)
                    statdict = self.makeIntoDir(statdict)
                    statdict['st_size'] = 4096

                # Are these next two cases now actually doing the same thing?
                elif "DATA_REPR" in self.internalpath:
                    if DEBUG:
                        print("WE ARE INSIDE A VARIABLE DIR (WITH DATA_REPR): ",
                              self.internalpath)
                    var = self.dataset_handle.variables[
                        self.internalpath.split('/')[0]]
                    # res = "%s" % var[:]
                    res = repr(var[:])
                    statdict['st_size'] = len(res)  # 0
                # Better way to do it?
                elif any(variable in self.internalpath for variable in self.ncVars):  # and '/' in self.internalpath:
                #elif '/' in self.internalpath:
                    if DEBUG:
                        print("WE ARE INSIDE A VARIABLE DIR: ", self.internalpath)
                    path, var_attr_name = self.internalpath.split('/')
                    print("#MSG: var, attr: ", path, var_attr_name)
                    print("Available attrs: ", self.dataset_handle.variables[path].ncattrs())
                    # Check not been given a not existent entry
                    if var_attr_name not in self.dataset_handle.variables[path].ncattrs():
                        print("ITEM NOT FOUND: ", var_attr_name, self.internalpath)
                        raise FuseOSError(ENOENT)
                    var = self.dataset_handle.variables[path]
                    res = var_attr_name_to_str(var_attr_name, var)
                    if res is not None:
                        statdict['st_size'] = len(res)
                else:
                    if DEBUG:
                        print("ITEM NOT FOUND: ", self.internalpath)
                    raise FuseOSError(ENOENT)
            return statdict

        def getxattr(self, name):
            """
            Gets the extended attributes for a file. See the linux programming
            man pages for xattr.
            """
            return "foo"
            '''
            if self.dataset_handle is None:
                return ""
            rawname = name[5:]
            if rawname in
            return rawname
            '''

        @classmethod
        def getncVars(cls, ncfile):
            """Returns the variables in a netcdf file"""
            dset = ncpy.Dataset(ncfile, 'r')
            return dset.variables

        def getncAttrs(self, nc_var):
            """Returns a list of attributes for a variable (nc_var)"""
            attrs = self.dataset_handle.variables[nc_var].ncattrs()
            if DEBUG:
                print("# MSG: ATTRIBUTES: ", attrs)
            return attrs

        def getncAttribute(self, nc_attr):
            """Return a string/bytes representation of a variable attribute"""
            pass

        def listdir(self):
            return self.readdir()

        def readdir(self):
            """Overrides readdir.
            Called when ls or ll and any other unix command that relies
            on this operation to work.
            """
            if self.dataset_handle is None:
                return (['.', '..'] +
                        [name.encode('utf-8')
                        for name in os.listdir(self.fullpath)])
            elif self.internalpath == "":
                # Return a list of netCDF variables
                return (['.', '..'] + [item.encode('utf-8')
                        for item in self.ncVars])
            elif self.internalpath in self.ncVars:
                if DEBUG:
                    print("# MSG: GETTING ATTRIBUTES...")
                local_attrs = self.getncAttrs(self.internalpath)
                if DEBUG:
                    print("# ATTRS: ", local_attrs)
                return ['.', '..'] + local_attrs + ["DATA_REPR"]
            else:
                return ['.', '..']

        def listxattr(self):
            raise NotImplementedError()

        def access(self, mode):
            path = self.fullpath
            if self.dataset_file is not None:
                path = self.dataset_file
                # If we can execute it, we should be able to read it too
                if mode == os.X_OK:
                    mode == os.R_OK
            if not os.access(path, mode):
                raise FuseOSError(EACCES)

        def read(self, size, offset, fh, lock):
            """
            Called when FUSE is reading the data from an opened file.
            So if we are opening a attribute file it should return
            a text (bytes?) representation of the contents of that file/
            """
            if self.dataset_handle is None or self.internalpath == "/":
                with lock:
                    os.lseek(fh, offset, 0)
                return os.read(fh, size)
            # import pprint
            # pp = pprint.PrettyPrinter(indent=4)
            for ign in ("/.paths", "/.git", ".paths", ".git",
                        # "/_FillValue",
                        ):
                if ign in self.internalpath:
                    self.internalpath = self.internalpath.replace(ign, "")
            var_attr_name = None
            if '/' in self.internalpath:
                self.internalpath, var_attr_name = self.internalpath.split('/')
                print("# VARIABLE ATTRIBUTE NAME", var_attr_name)
                # print(sys.exc_info()[0])
            # pp.pformat(self.internalpath)
            # pp.pformat(self.dataset_handle)
            print("# READ", size, offset, fh, "# INTERNAL PATH", self.internalpath)
            # if os.isatty(sys.stdout.fileno()):
            # print("# DH ", self.dataset_handle)
            # type 'netCDF4._netCDF4.Dataset'
            var = self.dataset_handle.variables[self.internalpath]
            res = "%s" % var
            # print("# DH[]", res)
            if var_attr_name is None:
                return res
            else:
                # Return a basic representation of the data in variable
                if var_attr_name == "DATA_REPR":
                    res = ""
                    for item in var:
                        # res += "%s, " % item
                        res += "\n" + repr(item)
                    return res[offset:offset+size-1] + "\n"
                if isinstance(var, netCDF4._netCDF4.Variable):
                    res = var_attr_name_to_str(var_attr_name, var)
                    if res is not None:
                        return res
                    try:
                        res = getattr(var, var_attr_name)
                        print("# try", res, var)
                        return res[offset:offset + size-1] + "\n"
                    # except AttributeError:
                    except Exception as e:
                        if DEBUG:
                            print(e)
                        print("# VARIABL ATTR NAME", var_attr_name)
                        res = repr(var)
                        return res[offset:offset + size-1] + "\n"
                print("# TYP", type(var), type(var_attr_name))
                return getattr(var, var_attr_name) + "\n"
            if isinstance(var, ncpy.Dataset):
                res = "%s" % self.dataset_handle[
                        self.internalpath].value.tostring()[offset:offset+size]
                return res[0:size - 2] + "\n"
            return "empty-none"

        def open(self, flags):
            if self.dataset_handle is None or self.internalpath == "/":
                res = os.open(self.fullpath, flags)
                print("# ISATTY", res.isatty())
                return res
            return 0

        def close(self, fh):
            if self.dataset_handle is None or self.internalpath == "/":
                return os.close(fh)
            return 0

    """These are the fusepy module methods that are overridden
    in this class. Any method not overridden here means that
    the default fusepy API method will be used.

    (See the fusepy.Operations class)

    Note these are not exactly the same as the C libs for FUSE

    """
    def acccess(self, path, mode):
        self.NetCDFComponent(path).access(mode)

    def read(self, path, size, offset, fh):
        return self.NetCDFComponent(path).read(
            size, offset, fh, self.readwritelock)

    def getattr(self, path, fh=None):
        # List of system dirs to ignore when getting attrs
        black = (
            ".xdg-volume-info",
            "/autorun", "/BDMV", "/AACS", "BDSVM", "/RCS", "/_strptime")
        st = attrs('.')
        for key in black:
            if path == key or key in path:
                return st
        return self.NetCDFComponent(path).getattr()

    def getxattr(self, path, name):
        return self.NetCDFComponent(path).getxattr(name)

    def listxattr(self, path):
        return self.NetCDFComponent(path).listxattr()

    def readdir(self, path, fh):
        # return self.NetCDFComponent(path).listdir()
        return self.NetCDFComponent(path).readdir()

    def release(self, path, fh):
        return self.NetCDFComponent(path).close(fh)

    def statfs(self, path):
        # Need to think about this one some more...
        stv = os.statvfs(path)
        # print("# DBG:", path, stv)
        return dict(
            (key, getattr(stv, key)) for key in (
             'f_bavail', 'f_bfree',
             'f_blocks', 'f_bsize', 'f_favail', 'f_ffree', 'f_files',
             'f_flag', 'f_frsize', 'f_namemax'))

    def open(self, path, flags):
        return self.NetCDFComponent(path).open(flags)

    truncate = None
    write = None
    rename = None
    symlink = None
    setxattr = None
    removexattr = None
    link = None
    mkdir = None
    mknod = None
    rmdir = None
    unlink = None
    chmod = None
    chown = None
    create = None
    fsync = None
    flush = None
    utimens = os.utime
    readlink = os.readlink


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: %s <netcdf file folder> <mountpoint>" % sys.argv[0])
        sys.exit(1)
    # fuse = FUSE(NetCDFFUSE(sys.argv[1]), sys.argv[2])
    fuse = FUSE(NetCDFFUSE(sys.argv[1]), sys.argv[2], foreground=True)
