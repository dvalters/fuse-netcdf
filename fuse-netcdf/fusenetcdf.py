# -*- coding: utf-8 -*-
#!/usr/bin/env python

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
  """Inherit from the base fusepy Operations class"""
  def __init__(self, filerootdir):
    self.filerootdir = os.path.realpath(filerootdir)
    self.readwritelock = Lock()

  def __call__(self, operation, path, *args):
    return super(NetCDFFUSE, self).__call__(operation, self.filerootdir + path, *args)

  class PotentialNetCDFFile:
    def __init__(self, path):
      self.dsattrs = { "user.ndim" : (lambda x : x.value.ndim), 
        "user.shape" : (lambda x : x.value.shape), 
        "user.dtype" : (lambda x : x.value.dtype), 
        "user.size" : (lambda x : x.value.size), 
        "user.itemsize" : (lambda x : x.value.itemsize), 
        "user.dtype.itemsize" : (lambda x : x.value.dtype.itemsize),}
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
            print self.internalpath
            break

        # handle this case better - I think it can be done better with 
        # the os path methods

    def testNetCDF(self, path):
      if os.path.isfile(path):
        try:
          # Also test for netCDF version here?
          self.dataset_handle = ncpy.Dataset(path, "r")
          self.dataset_file = path
          self.ncVars = self.getncVars(path)
          print path + " is netCDF"
          return True
        except exc as e:
          print e
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
      print "Making a statdict!"
      statdict["st_mode"] = statdict["st_mode"] ^ 0100000 | 0040000
      for i in [ [ 0400 , 0100 ] , [ 040 , 010 ] , [ 04, 01 ] ]:
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
        #import pdb; pdb.set_trace()
        if self.dataset_file != None:
          st = os.lstat(self.dataset_file)
        else:
          st = os.lstat(self.fullpath)
        statdict = dict((key, getattr(st, key)) for key in ('st_atime', 'st_ctime',
                'st_gid', 'st_mode', 'st_mtime', 'st_nlink', 'st_size', 'st_uid'))
        if self.dataset_file != None:
          #print "NEXUSHANDLE:  ", self.dataset_handle
          print "NEXUSFILE:    ", self.dataset_file
          print "INTERNALPATH: ", self.internalpath
          if self.internalpath == "/":
            print "at a filepath slash..."
            #import pdb; pdb.set_trace()
            statdict = self.makeIntoDir(statdict)
            #elif isinstance(self.dataset_handle[self.internalpath],h5py.Group):
            #	statdict = self.makeIntoDir(statdict)
            #	statdict["st_size"] = 0
            #elif isinstance(self.dataset_handle[self.internalpath],h5py.Dataset):
            #	ob=self.dataset_handle[self.internalpath].value
            #	statdict["st_size"] = ob.size * ob.itemsize
            #elif isinstance(self.dataset_handle[self.internalpath], ncpy.Dataset):
          elif self.internalpath == "":
            print "WE ARE AT THE TOP: ", self.internalpath
            statdict = self.makeIntoDir(statdict)
            statdict["st_size"] = 0
          elif self.internalpath in self.ncVars:
            print "WE ARE AT VARIABLE: ", self.internalpath
            
        return statdict	

    def getxattr(self, name):
      raise NotImplementedError()

    def getncVars(self, ncfile):
      """Returns the variables in a netcdf file"""
      dset = ncpy.Dataset(ncfile, 'r')
      return dset.variables

    def listdir(self):
      """Overrides readdir
      """
      if self.dataset_handle == None:
        return ['.', '..'] + [name.encode('utf-8') for name in os.listdir(self.fullpath)]
      elif self.internalpath == "":
        # Return a list of netCDF variables
        return ['.', '..'] + [item.encode('utf-8') for item in self.ncVars]
      else:
        return ['.', '..'] + ['foo']
#      else:
#        items = self.dataset_handle[self.internalpath].items()
#        return ['.', '..'] + [item[0].encode('utf-8')  for item in items]
    
    def listxattr(self):
      raise NotImplementedError()

    def access(self, mode):
      path = self.fullpath
      if self.dataset_file != None:
        path = self.dataset_file
        # If we can execute it, we should be able to read it too
        if mode ==  os.X_OK:
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


"""
At the minute, the netCDF file has to be in a parent folder,
but this can be changed in future, i.e. just point to a single .nc file
"""
if __name__ == "__main__":
  if len(sys.argv) != 3:
    print("Usage: %s <netcdf file folder> <mountpoint>" % sys.argv[0])
    sys.exit(1)
  #fuse = FUSE(NetCDFFUSE(sys.argv[1]), sys.argv[2])
  fuse = FUSE(NetCDFFUSE(sys.argv[1]), sys.argv[2], foreground=True) # for debugging


