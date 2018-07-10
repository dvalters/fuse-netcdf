# Tests for the fuse netcdf project
import unittest

import fusenetcdf.fusenetcdf as fnc


class testFuseNetcdf(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        # Set up test file object
        self.PATH = "trial/ECMWF_ERA-40_subset.nc"
        self.NCFILE = fnc.NetCDFFUSE.PotentialNetCDFFile(self.PATH)

    def test_testNetCDF(self):
        """
        Test that the netCDF file checker returns correct
        truthy values.
        """
        self.assertTrue(self.NCFILE.testNetCDF(self.PATH))

if __name__ == '__main__':
    unittest.main()
