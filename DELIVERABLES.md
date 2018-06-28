# Acceptance criteria/project deliverables


## Criterium

- [] Variable represented as a directory. When coordinates follow CF Convention, variable should be split into subdirectories along time and vertical axes (e.g. each time/vertical coordinate represented as a subdirectory).
- [] Regular Variable’s data represented at least as a binary file; additional representations (text, png) are welcome but optional.
- [] Dimension Variable’s data represented as an editable text file containing a list of coordinate values
- [] Renaming a variable directory renames corresponding variable in NetCDF
- [] Copying a variable directory creates new variable in NetCDF
- [] Deleting attribute text file removes corresponding attribute from NetCDF
- [] Renaming attribute text file renames corresponding attribute in NetCDF
- [] Creating new attribute text file creates new attribute in NetCDF
- [] Editing contents of attribute text file modifies value of attribute in NetCDF
- [] Changes do not result in inconsistent dataset: e.g. renaming Dimension Variable should also rename the corresponding dimension and vice versa
- [] Must run on Linux (SuSE)
- [] Must run on native system and in virtual environment
- [] Must be able to read NetCDF3 and NetCDF4-classic files
- [] Must be able to output NetCDF3 and NetCDF4-classic files
- [] Must be able to define/modify variable types (e.g. double ->float)
- [] Must have an option to include / exclude scaling factors and offset (user-specified and automatic)
- [] Must be able to run from a script (e.g. python)


