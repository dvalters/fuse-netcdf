#!/usr/bin/env python

"""
fuse-netcdf project

This is the ESoWC project to create a mountable netcdf file
in user space using the fusepy and python-netcdf libraries

"""

import os
import sys
import netCDF4 as ncpy

from fuse import FUSE, FuseOSError, Operations, LoggingMixIn
from threading import Lock


class NetCDFFUSE(Operations):
  """Inherit from the base fusepy Operations class"""
  def __init__(self, filerootdir):
    self.filerootdir = os.path.realpath(filerootdir)
    self.readwritelock = Lock()

  def __call__(self, operation, path, *args):
    return super(NetCDFFUSE, self).__call__(operation, self.filerootdir + path, *args)

  class PotentialNetCDFFile:
    def __init__(self, path):
      self.data_attrs = {}
      self.fullpath = path
      self.internalpath = "/"
      self.dataset_handle = None
      self.dataset_file = None
      # Check that there is a netCDF file
      if os.path.lexists(path):
        self.testNetCDF(path)
      else:
        print("No File Found!")
        exit(1)
        # handle this case better!

    def testNetCDF(self, path):
      if os.path.isfile(path):
        try:
          # Also test for netCDF version here?
          self.dataset_handle = ncpy.Dataset(path, "r")
          self.dataset_file = path
          return True
        except:
          pass
        return False

    def __del__(self):
      if self.dataset_handle != None:
        try:
          self.dataset_handle.close()
        except:
          # needs a better soln!
          pass

    def makeIntoDir(self, statdict):
      raise NotImplementedError()

    def getattr(self):
      raise NotImplementedError()

    def getxattr(self, name):
      raise NotImplementedError()

    def listxattr(self):
      raise NotImplementedError()

    def listdir(self):
      raise NotImplementedError()

    def access(self, mode):
      raise NotImplementedError()

    def read(self):
      raise NotImplementedError()

    def open(self):
      raise NotImplementedError()

    def close(self):
      raise NotImplementedError()

  def acccess(self, path, mode):
    self.PotentialNetCDFFile(path).access(mode)

  def read(self, path, size, offset, fh):
    return self.PotentialNetCDFFile(path).read(size, offset, fh, self.readwritelock)

  def getattr(self, path, name):
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


