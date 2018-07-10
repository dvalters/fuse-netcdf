#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fuse-netcdf project

This is the ESoWC project to create a mountable netcdf file
in user space using the fusepy and python-netcdf libraries

"""

import os
import sys
import netCDF4 as ncpy

from fuse import FUSE, FuseOSError, Operations
from threading import Lock
from errno import EACCES


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
        return super(NetCDFFUSE, self).__call__(operation, self.filerootdir + path, *args)

    class PotentialNetCDFFile:
        """
        Main object for netCDF-filesytem operations
        """
        def __init__(self, path):
            """
            self.dsattrs = { "user.ndim" : (lambda x : x.value.ndim), 
              "user.shape" : (lambda x : x.value.shape), 
              "user.dtype" : (lambda x : x.value.dtype), 
              "user.size" : (lambda x : x.value.size), 
              "user.itemsize" : (lambda x : x.value.itemsize), 
              "user.dtype.itemsize" : (lambda x : x.value.dtype.itemsize),}
            """
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
                        self.internalpath = "/".join(components[i-len(components):])
                        print(self.internalpath)
                        break
                        # Could handle this case better - I think it can be done better with 
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
                    print(path + " is netCDF")
                    return True
                except exc as e:
                    print(e)
            return False

        def __del__(self):
            if self.dataset_handle != None:
                try:
                    self.dataset_handle.close()
                except:
                    # needs a better soln!
                    pass

        def makeIntoDir(self, statdict):
            """Update the statdict if the item in the VFS should be
            presented as a directory
            """
            print("Making a statdict to create a folder structure!")
            statdict["st_mode"] = statdict["st_mode"] ^ 0o100000 | 0o040000
            for i in [ [ 0o400 , 0o100 ] , [ 0o40 , 0o10 ] , [ 0o4, 0o1 ] ]:
                if (statdict["st_mode"] & i[0]) != 0:
                    statdict["st_mode"] = statdict["st_mode"] | i[1]
            return statdict

        def getattr(self):
            """The getattr callback is in charge of reading the metadata of a given path,
               this callback is always called before any operation made on the filesystem.
            
            We are telling FUSE that the current entry is a file
            or a directory using the stat struct. 
            In general, if the entry is a directory, st_mode have to be set
            to S_IFDIR and st_nlink to 2, while if it’s a file, st_mode have 
            to be set to S_IFREG (that stands for regular file) and st_nlink to 1.
            Files also require that the st_size (the full file size) is specified.
            """
            if self.dataset_file != None:
                st = os.lstat(self.dataset_file)
            else:
                st = os.lstat(self.fullpath)
                statdict = dict((key, getattr(st, key)) for key in ('st_atime', 'st_ctime',
                    'st_gid', 'st_mode', 'st_mtime', 'st_nlink', 'st_size', 'st_uid'))
            if self.dataset_file != None:
                print("NETCDF_FILE:    ", self.dataset_file)
                print("INTERNALPATH: ", self.internalpath)
                if self.internalpath == "/":
                    print("at a filepath slash...")
                    statdict = self.makeIntoDir(statdict)
                elif self.internalpath == "":
                    print("WE ARE AT THE TOP: ", self.internalpath)
                    statdict = self.makeIntoDir(statdict)
                    statdict["st_size"] = 4096
                elif self.internalpath in self.ncVars:
                    print("WE ARE AT VARIABLE: ", self.internalpath)
                    statdict = self.makeIntoDir(statdict)
                    statdict["st_size"] = 4096
                elif "DATA_REPR" in self.internalpath:
                    print("WE ARE INSIDE A VARIABLE DIR: ", self.internalpath)
                    statdict["st_size"] = 0
            return statdict	

        def getxattr(self, name):
            raise NotImplementedError()

        def getncVars(self, ncfile):
            """Returns the variables in a netcdf file"""
            dset = ncpy.Dataset(ncfile, 'r')
            return dset.variables

        def getncAttrs(self, nc_var):
            """Returns a list of attributes for a variable (nc_var)"""
            attrs = self.dataset_handle.variables[nc_var].ncattrs()
            print("ATTRIBUTES: ", attrs)
            return attrs

        def listdir(self):
            """Overrides readdir.
            Called when ls or ll and any other unix command that relies 
            on this operation to work.
            """
            if self.dataset_handle == None:
                return ['.', '..'] + [name.encode('utf-8') for name in os.listdir(self.fullpath)]
            elif self.internalpath == "":
                # Return a list of netCDF variables
                return ['.', '..'] + [item.encode('utf-8') for item in self.ncVars]
            elif self.internalpath in self.ncVars:
                print("GETTING ATTRIBUTES...")
                local_attrs = self.getncAttrs(self.internalpath)
                print("ATTRS: ", local_attrs)
                return ['.', '..'] + local_attrs + ["DATA_REPR"]
            else:
                return ['.', '..'] 
        
        def listxattr(self):
            raise NotImplementedError()

        def access(self, mode):
            path = self.fullpath
            if self.dataset_file != None:
                path = self.dataset_file
            # If we can execute it, we should be able to read it too
            if mode == os.X_OK:
                mode == os.R_OK
            if not os.access(path, mode):
                raise FuseOSError(EACCES)
            
        def read(self, size, offset, fh, lock):
            if self.dataset_handle == None or self.internalpath == "/":
                with lock:
                    os.lseek(fh, offset, 0)
                    return os.read(fh, size)
            if isinstance(self.dataset_handle[self.internalpath], ncpy.Dataset):
                return self.dataset_handle[self.internalpath].value.tostring()[offset:offset+size]

        def open(self, flags):
            if self.dataset_handle == None or self.internalpath == "/":
                return os.open(self.fullpath, flags)
            return 0

        def close(self, fh):
            if self.dataset_handle == None or self.internalpath == "/":
                return os.close(fh)
            return 0
      
        """These are the fusepy module methods that are overridden
        in this class. Any method not overridden here means that
        the default fusepy API method will be used. 

        (See the fusepy.Operations class)

        Note these are not exactly the same as the C libs for FUSE
          
        """
        def acccess(self, path, mode):
            self.PotentialNetCDFFile(path).access(mode)

        def read(self, path, size, offset, fh):
            return self.PotentialNetCDFFile(path).read(size, offset, fh, self.readwritelock)

        def getattr(self, path, fh=None):
            return self.PotentialNetCDFFile(path).getattr()
      
        def getxattr(self, path, name):
            return self.PotentialNetCDFFile(path).getxattr(name)

        def listxattr(self, path):
            return self.PotentialNetCDFFile(path).listxattr()

        def readdir(self, path, fh):
            return self.PotentialNetCDFFile(path).listdir()

        def release(self, path, fh):
            return self.PotentialNetCDFFile(path).close(fh)

        def statfs(self, path):
            # Need to think about this one some more...
            raise NotImplementedError()

        def open(self, path, flags):
            return self.PotentialNetCDFFile(path).open(flags)

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
    fuse = FUSE(NetCDFFUSE(sys.argv[1]), sys.argv[2])
    # fuse = FUSE(NetCDFFUSE(sys.argv[1]), sys.argv[2], foreground=True) # for debugging

