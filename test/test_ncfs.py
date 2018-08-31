import unittest
from fusenetcdf.fusenetcdf import NCFS
from netCDF4 import Dataset
from fusenetcdf.fusenetcdf import DimNamesAsTextFiles


class FakeVariable(object):
    def getncattr(self, name):
        if name == 'fooattr':
            return 'bar'
        else:
            raise AttributeError()


class FakeDataset(object):

    variables = {'foovar': FakeVariable()}

    def ncattrs(self):
        return {'attr1': 'val1', 'attr2': 'val2'}


class TestIsVarDir(unittest.TestCase):

    def setUp(self):
        self.ncfs = NCFS(FakeDataset(), None, None, None)

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
        self.ncfs = NCFS(FakeDataset(), None, None, None)

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
        self.ncfs = NCFS(FakeDataset(), None, None, None)

    def test_is_var_attr_1(self):
        self.assertFalse(self.ncfs.is_var_attr('/abcd'))

    def test_is_var_attr_2(self):
        self.assertTrue(self.ncfs.is_var_attr('/abcd/def'))

    def test_is_var_attr_3(self):
        self.assertFalse(self.ncfs.is_var_attr('/'))

    def test_is_var_attr_4(self):
        self.assertFalse(self.ncfs.is_var_attr('/abcd/DATA_REPR'))

    def test_is_var_attr_5(self):
        self.assertFalse(self.ncfs.is_var_attr('/abcd/DIMENSIONS'))


class TestIsVariableDimensions(unittest.TestCase):

    def setUp(self):
        self.ncfs = NCFS(FakeDataset(), None, None, None)

    def test_is_var_dimensions_1(self):
        self.assertTrue(self.ncfs.is_var_dimensions('/abcd/DIMENSIONS'))

    def test_is_var_dimensions_2(self):
        self.assertFalse(self.ncfs.is_var_dimensions('/abcd/DATA_REPR'))


class TestExists(unittest.TestCase):

    def setUp(self):
        self.ncfs = NCFS(FakeDataset(), None, None, None)

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
        self.assertTrue(self.ncfs.exists('/foovar/DIMENSIONS'))


def create_test_dataset_1():
    ds = Dataset('test.nc', mode='w', diskless=True, format='NETCDF4')
    # create Dimensions
    ds.createDimension('x', 3)
    ds.createDimension('y', 3)
    # create a Dimension Variable (yes just one)
    ds.createVariable('x', int, dimensions=('x'))
    ds.variables['x'][:] = [1, 2, 3]
    # create a Variable
    ds.createVariable('foovar', float, dimensions=('x', 'y'))
    v = ds.variables['foovar']
    v.setncattr('fooattr', 'abc')
    # create global attribute
    ds.setncattr('attr1', 'attrval1')
    return ds


class TestWrite(unittest.TestCase):

    def setUp(self):
        self.ds = create_test_dataset_1()
        self.ncfs = NCFS(self.ds, None, None, None)

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
        self.assertTrue('fooattr' not in self.ds.variables['foovar'].ncattrs())



class TestGlobalAttrs(unittest.TestCase):

    def setUp(self):
        self.ds = create_test_dataset_1()
        self.ncfs = NCFS(self.ds, None, None, None)

    def tearDown(self):
        self.ds.close()

    def test_creating_new_global_attr(self):
        self.ncfs.create('/attr2', mode=int('0100644', 8))
        self.assertTrue('attr2' in self.ds.ncattrs())

    def test_writing_to_existing_global_attr(self):
        self.ncfs.write('/attr1', 'newattr1val', offset=0)
        self.assertEqual(self.ds.getncattr('attr1'), 'newattr1val')

    def test_writing_to_existing_global_attr_2(self):
        self.ncfs.write('/attr1', 'x', offset=0)
        self.assertEqual(self.ds.getncattr('attr1'), 'xttrval1')

    def test_is_global_attr_on_existing_attr(self):
        self.assertTrue(self.ncfs.is_global_attr('/attr1'))

    def test_is_global_attr_on_nonexisting_attr(self):
        self.assertTrue(self.ncfs.is_global_attr('/attr99'))

    def test_get_global_attr(self):
        self.assertTrue(self.ncfs.get_global_attr('/attr1') is not None)

    def test_exist_on_global_attr(self):
        self.assertTrue(self.ncfs.exists('/attr1'))

    def test_is_var_dir_on_existing_global_attr(self):
        self.assertFalse(self.ncfs.is_var_dir('/attr1'))

    def test_deleting_existing_global_attr(self):
        self.ncfs.unlink('/attr1')
        self.assertFalse('attr1' in self.ds.ncattrs())


class TestDimNamesAsTextFiles(unittest.TestCase):

    def setUp(self):
        self.mapping = DimNamesAsTextFiles()

    def test_encode(self):
        dimnames = [u'longitude', u'latitude', u'time']
        expected_repr = 'longitude\nlatitude\ntime\n'
        self.assertMultiLineEqual(
                self.mapping.encode(dimnames), expected_repr)

    def test_encode_with_custom_separator(self):
        mapping = DimNamesAsTextFiles(sep=', ')
        dimnames = [u'longitude', u'latitude', u'time']
        expected_repr = 'longitude, latitude, time\n'
        self.assertMultiLineEqual(mapping.encode(dimnames), expected_repr)

    def test_encode_empty_list(self):
        dimnames = []
        expected_repr = ''
        self.assertMultiLineEqual(
                self.mapping.encode(dimnames), expected_repr)

    def test_decode(self):
        dimnames_repr = 'longitude\nlatitude\ntime\n'
        expected_dimnames = [u'longitude', u'latitude', u'time']
        self.assertEqual(
                self.mapping.decode(dimnames_repr), expected_dimnames)

    def test_decode_with_custom_separator(self):
        mapping = DimNamesAsTextFiles(sep=', ')
        dimnames_repr = 'longitude, latitude, time\n'
        expected_dimnames = [u'longitude', u'latitude', u'time']
        self.assertEqual(mapping.decode(dimnames_repr), expected_dimnames)

    def test_decode_empty_string(self):
        dimnames_repr = ''
        expected_dimnames = []
        self.assertEqual(self.mapping.decode(dimnames_repr), expected_dimnames)

    def test_size(self):
        dimnames = [u'x', u'y', u'z']
        self.assertEqual(self.mapping.size(dimnames), 6)


class TestDimensions(unittest.TestCase):

    def setUp(self):
        self.ds = create_test_dataset_1()
        dimnames_repr = DimNamesAsTextFiles()
        self.ncfs = NCFS(self.ds, None, None, dimnames_repr)

    def tearDown(self):
        self.ds.close()

    def test_reading_dimensions(self):
        expected = 'x\ny\n'
        self.assertMultiLineEqual(
                str(self.ncfs.read('/foovar/DIMENSIONS', 4, 0)), expected)

    def test_renaming_all_dimensions(self):
        self.ncfs.write('/foovar/DIMENSIONS', 'lon\nlat\n', 0, 0)
        expected = (u'lon', u'lat')
        # were dimensions renamed?
        self.assertEqual(self.ds.variables['foovar'].dimensions, expected)
        # was the 'x' Dimension Variable renamed to 'lon'?
        self.assertTrue('lon' in self.ds.variables)

    def test_renaming_some_dimensions(self):
        self.ncfs.write('/foovar/DIMENSIONS', 'x\nlat\n', 0, 0)
        expected = (u'x', u'lat')
        # were dimensions renamed?
        self.assertEqual(self.ds.variables['foovar'].dimensions, expected)
        # is the 'x' Dimension Variable still named 'x'?
        self.assertTrue('x' in self.ds.variables)

    def test_ignoring_invalid_edits(self):
        # if new list has wrong number of dimensions, ingore the change
        self.ncfs.write('/foovar/DIMENSIONS', 'a\nb\nc\n', 0, 0)
        expected = (u'x', u'y')
        self.assertEqual(self.ds.variables['foovar'].dimensions, expected)

    def test_renaming_dimension_variable(self):
        self.ncfs.rename('/x', 'lon')
        # did renaming Dimension Variable also renamed corresponding Dimension?
        self.assertFalse('x' in self.ds.variables)
        self.assertTrue('lon' in self.ds.variables)
        self.assertFalse('x' in self.ds.dimensions)
        self.assertTrue('lon' in self.ds.dimensions)

    def test_swapping_dimension_names(self):
        self.ncfs.write('/foovar/DIMENSIONS', 'y\nx\n', 0, 0)
        self.assertEqual(self.ds.variables['foovar'].dimensions, (u'y', u'x'))
        # did the 'x' Dimension Variable name change to 'y' ?
        self.assertFalse('x' in self.ds.variables)
        self.assertTrue('y' in self.ds.variables)

    def test_duplicate_names(self):
        self.ncfs.write('/foovar/DIMENSIONS', 'y\ny\n', 0, 0)
        # was this edit ignored?
        self.assertEqual(self.ds.variables['foovar'].dimensions, (u'x', u'y'))
