# fuse-netcdf
ESoWC project for the netcdf-fusepy utility

See the wiki for proposal, workplan, other notes etc. https://github.com/dvalters/fuse-netcdf/wiki


## Usage

This is currently a work in progress, but the basic usage at the testing stage is as follows:

```bash
python fusenetcdf.py <netcdf file folder> <mountpoint>
```

The `<netcdf file folder>` should be the path to your netcdf file. 

You should create an empty folder which will be your mountpoint at `<mountpoint>`



## Development resources

Example of the fusepy module in use here (w/o netCDF)  https://github.com/dvalters/Python-miscellany/blob/master/fusepy.ipynb

Blogpost example: https://medium.com/the-python-corner/writing-a-fuse-filesystem-in-python-5e0f2de3a813

Which is based on this example... https://github.com/skorokithakis/python-fuse-sample

