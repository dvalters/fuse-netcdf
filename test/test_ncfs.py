import unittest
from fusenetcdf.fusenetcdf import NCFS
from netCDF4 import Dataset


class TestIsVarDir(unittest.TestCase):

    def setUp(self):
        self.ncfs = NCFS(None, None, None)

    def test_is_var_dir_1(self):
        self.assertTrue(self.ncfs.is_var_dir('/abcd'))

    def test_is_var_dir_2(self):
        self.assertFalse(self.ncfs.is_var_dir('/abcd/def'))

    def test_is_var_dir_3(self):
        self.assertFalse(self.ncfs.is_var_dir('/'))

    def test_is_var_dir_4(self):
        self.assertFalse(self.ncfs.is_var_dir('/abcd/DATA_REPR'))


class TestIsVarData(unittest.TestCase):

    def setUp(self):
        self.ncfs = NCFS(None, None, None)

    def test_is_var_data_1(self):
        self.assertFalse(self.ncfs.is_var_data('/abcd'))

    def test_is_var_data_2(self):
        self.assertFalse(self.ncfs.is_var_data('/abcd/def'))

    def test_is_var_data_3(self):
        self.assertFalse(self.ncfs.is_var_data('/'))

    def test_is_var_data_4(self):
        self.assertTrue(self.ncfs.is_var_data('/abcd/DATA_REPR'))


class TestIsVarAttribute(unittest.TestCase):

    def setUp(self):
        self.ncfs = NCFS(None, None, None)

    def test_is_var_attr_1(self):
        self.assertFalse(self.ncfs.is_var_attr('/abcd'))

    def test_is_var_attr_2(self):
        self.assertTrue(self.ncfs.is_var_attr('/abcd/def'))

    def test_is_var_attr_3(self):
        self.assertFalse(self.ncfs.is_var_attr('/'))

    def test_is_var_attr_4(self):
        self.assertFalse(self.ncfs.is_var_attr('/abcd/DATA_REPR'))

    def test_is_var_attr_5(self):
        self.assertFalse(self.ncfs.is_var_attr('/abcd/dimensions'))


class FakeVariable(object):
    def getncattr(self, name):
        if name == 'fooattr':
            return 'bar'
        else:
            raise AttributeError()


class FakeDataset(object):
    variables = {'foovar': FakeVariable()}


class TestExists(unittest.TestCase):

    def setUp(self):
        dataset = FakeDataset()
        self.ncfs = NCFS(dataset, None, None)

    def test_exists_1(self):
        self.assertTrue(self.ncfs.exists('/foovar'))

    def test_exists_2(self):
        self.assertTrue(self.ncfs.exists('/foovar/fooattr'))

    def test_exists_3(self):
        self.assertFalse(self.ncfs.exists('/foovar/fooattr/foo'))

    def test_exists_4(self):
        self.assertTrue(self.ncfs.exists('/'))

    def test_exists_5(self):
        self.assertTrue(self.ncfs.exists('/foovar/DATA_REPR'))

    def test_exists_6(self):
        self.assertTrue(self.ncfs.exists('/foovar/dimensions'))


def create_test_dataset_1():
    ds = Dataset('test.nc', mode='w', diskless=True, format='NETCDF4')
    ds.createDimension('x', 3)
    ds.createDimension('y', 3)
    ds.createVariable('foovar', float, dimensions=('x', 'y'))
    v = ds.variables['foovar']
    v.setncattr('fooattr', 'abc')
    return ds


class TestWrite(unittest.TestCase):

    def setUp(self):
        self.ds = create_test_dataset_1()
        self.ncfs = NCFS(self.ds, None, None)

    def tearDown(self):
        self.ds.close()

    def test_writing_to_existing_attr(self):
        self.ncfs.write('/foovar/fooattr', '123', offset=0)
        self.assertEqual(self.ds.variables['foovar'].fooattr, '123')

    def test_creating_new_attr(self):
        self.ncfs.create('/foovar/xyz', mode=int('0100644', 8))
        self.assertEqual(self.ds.variables['foovar'].xyz, '')

    def test_appending_to_existing_attr(self):
        self.ncfs.write('/foovar/fooattr', '123', offset=3)
        self.assertEqual(self.ds.variables['foovar'].fooattr, 'abc123')

    def test_deleting_existing_attr(self):
        self.ncfs.unlink('/foovar/fooattr')
        self.assertRaises(AttributeError,
                          self.ds.variables['foovar'].getncattr,
                          'foovar')
