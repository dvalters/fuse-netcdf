#!/usr/bin/env python

"""
fuse-netcdf project

This is the ESoWC project to create a mountable netcdf file
in user space using the fusepy and python-netcdf libraries

"""

import os
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
      # Check that there is a netCDF file
      if os.path.lexists(path):
        self.testNetCDF(path)
      else:
        print("No File Found!")
        exit(1)
        # handle this case better!

    def testNetCDF(self, path):
      is os.path.isfile(path):
        try:
          # Also test for netCDF version here?
          self.dataset_handle = ncpy.Dataset(path, "r")
          return True
        except:
          pass
        return False

    def __del__(self):
      if self.dataset_handle != None
        try:
          self.dataset_handle.close()
        except:
          # needs a better soln!
          pass

    def makeIntoDir(self, statdict):
      raise NotImplementedError()

    def gettattr(self):
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

  def read(self, path, size, offset, fh, self.readwritelock):
    return 



"""
At the minute, the netCDF file has to be in a parent folder,
but this can be changed in future
"""
if __name__ == "__main__":
  if len(argv) != 3:
    print("Usage: %s <netcdf file folder> <mountpoint>" % argv[0]
    exit(1)
  fuse = FUSE(NetCDFFUSE(argv[1]), argv[2])


