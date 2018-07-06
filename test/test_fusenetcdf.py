# Tests for the fuse netcdf project
import unittest

from fusenetcdf.NetCDFFUSE import PotentialNetCDFFile

class testFuseNetcdf(unittest.TestCase):

    # Set up test file object
    path = "trial/ECMWF_ERA-40_subset.nc"
    ncfile = PotenitalNetCDFFile(path)
    
    def test_testNetCDF(self):
      """
          Test that the netCDF file checker returns correct
          truthy values.
      """
      self.assertTrue(ncfile.testNetCDF(path))

if __name__=='__main__':
    unittest.main()


