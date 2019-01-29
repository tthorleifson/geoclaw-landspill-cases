#! /usr/bin/env python
# -*- coding: utf-8 -*-
# vim:fenc=utf-8
#
# Copyright © 2018 Pi-Yueh Chuang <pychuang@gwu.edu>
#
# Distributed under terms of the MIT license.

"""
Write to NetCDF4 file with CF convention
"""

import os
import sys
import numpy
import netCDF4
import datetime
import argparse
from clawpack import pyclaw
from pphelper import get_bounding_box, interpolate


if __name__ == "__main__":

    # CMD argument parser
    parser = argparse.ArgumentParser(
        description="Create a NC file with CF convention.")

    parser.add_argument(
        'case', metavar='case', type=str, help='the name of the case')

    parser.add_argument(
        '--level', dest="level", action="store", type=int,
        help='use data from a specific AMR level (default: finest level)')

    parser.add_argument(
        '--frame-bg', dest="frame_bg", action="store", type=int,
        help='customized start farme no. (default: 0)')

    parser.add_argument(
        '--frame-ed', dest="frame_ed", action="store", type=int,
        help='customized end farme no. (default: get from setrun.py)')

    # process arguments
    args = parser.parse_args()

    # get case path
    casepath = os.path.abspath(args.case)

    # get the abs path of the repo
    repopath = os.path.dirname(os.path.abspath(__file__))

    # check case dir
    if not os.path.isdir(casepath):
        print("Error: case folder {} does not exist.".format(casepath),
              file=sys.stderr)
        sys.exit(1)

    # check setup.py
    setrunpath = os.path.join(casepath, "setrun.py")
    if not os.path.isfile(setrunpath):
        print("Error: case folder {} does not have setrun.py.".format(casepath),
              file=sys.stderr)
        sys.exit(1)

    # check soln dir
    outputpath = os.path.join(casepath, "_output")
    if not os.path.isdir(outputpath):
        print("Error: output folder {} does not exist.".format(outputpath),
              file=sys.stderr)
        sys.exit(1)

    # load setup.py
    sys.path.insert(0, casepath) # add case folder to module search path
    import setrun # import the setrun.py

    rundata = setrun.setrun() # get ClawRunData object

    # computational domain
    x_domain_bg = rundata.clawdata.lower[0]
    x_domain_ed = rundata.clawdata.upper[0]
    y_domain_bg = rundata.clawdata.lower[1]
    y_domain_ed = rundata.clawdata.upper[1]

    # number of frames
    if args.frame_ed is not None:
        frame_ed = args.frame_ed + 1
    elif rundata.clawdata.output_style == 1:
        frame_ed = rundata.clawdata.num_output_times
        if rundata.clawdata.output_t0:
            frame_ed += 1
    elif rundata.clawdata.output_style == 2:
        frame_ed = len(rundata.clawdata.output_times)
    elif rundata.clawdata.output_style == 3:
        frame_ed = int(rundata.clawdata.total_steps /
                       rundata.clawdata.output_step_interval)
        if rundata.clawdata.output_t0:
            frame_ed += 1

    # starting frame no.
    if args.frame_ed is not None:
        frame_bg = args.frame_bg
    else:
        frame_bg = 0

    # process target level
    if args.level is None:
        args.level = rundata.amrdata.amr_levels_max

    # NC file path and name
    ncfilename = os.path.join(casepath, "{}_level{:02}.nc".format(args.case, args.level))

    # find bounding box we're going to use for NC data
    xleft, xright, ybottom, ytop = get_bounding_box(
        outputpath, frame_bg, frame_ed, args.level)

    # get the resolution at the target level
    dx = (x_domain_ed - x_domain_bg) / rundata.clawdata.num_cells[0]
    dx /= numpy.prod(rundata.amrdata.refinement_ratios_x[:args.level])
    dy = (y_domain_ed - y_domain_bg) / rundata.clawdata.num_cells[1]
    dy /= numpy.prod(rundata.amrdata.refinement_ratios_y[:args.level])

    # get the target coordinates based on dx, dy w/ flexibility of rounding err
    x = numpy.arange(xleft+dx/2., xright+dx/2, dx)
    y = numpy.arange(ybottom+dy/2., ytop+dy/2, dy)

    # revise the upper limit
    xright = x[-1]
    ytop = y[-1]

    # get the number of cells in the bounding box
    nx = x.size
    ny = y.size

    # dry tolerance
    threshold = rundata.geo_data.dry_tolerance


    # create a NC file and root group
    print("Creating NC file: {}".format(ncfilename))
    rootgrp = netCDF4.Dataset(
        filename=ncfilename, mode="w",
        encoding="utf-8", format="NETCDF4")

    # set up dimension
    nc_ntime = rootgrp.createDimension("time", None)
    nc_nx = rootgrp.createDimension("x", nx)
    nc_ny = rootgrp.createDimension("y", ny)

    # create variables
    nc_times = rootgrp.createVariable("time", numpy.float64, ("time",))
    nc_x = rootgrp.createVariable("x", numpy.float64, ("x",))
    nc_y = rootgrp.createVariable("y", numpy.float64, ("y",))
    nc_depth = rootgrp.createVariable(
        "depth", numpy.float64, ("time", "y", "x"),
        fill_value=-9999., zlib=True, complevel=9)
    nc_mercator = rootgrp.createVariable("mercator", 'S1')

    # global attributes
    rootgrp.title = args.case
    rootgrp.institution = "N/A"
    rootgrp.source = "N/A"
    rootgrp.history = "Created " + str(datetime.datetime.now().replace(microsecond=0))
    rootgrp.reference = ""
    rootgrp.comment = ""
    rootgrp.Conventions = "CF-1.7"

    # variable: time
    nc_times.units = "sec"
    nc_times.axis = "T"
    nc_times.long_name = "Simulation times"

    # variable: x
    nc_x.units = "m"
    nc_x.long_name = "X-coordinate in EPSG:3857 WGS 84"
    nc_x.standard_name = "projection_x_coordinate"
    nc_x[:] = x

    # variable: y
    nc_y.units = "m"
    nc_y.long_name = "Y-coordinate in EPSG:3857 WGS 84"
    nc_y.standard_name = "projection_y_coordinate"
    nc_y[:] = y

    # variable attributes: depth
    nc_depth.units = "m"
    nc_depth.long_name = "Oil Depth"
    nc_depth.grid_mapping = "mercator"

    # variable attributes: mercator
    nc_mercator.grid_mapping_name = "mercator"
    nc_mercator.long_name = "CRS definition"
    nc_mercator.longitude_of_projection_origin =0.0
    nc_mercator.standard_parallel = 0.0
    nc_mercator.false_easting = 0.0
    nc_mercator.false_northing = 0.0
    nc_mercator.spatial_ref = \
        "PROJCS[\"WGS_1984_Web_Mercator_Auxiliary_Sphere\"," + \
            "GEOGCS[\"GCS_WGS_1984\"," + \
                "DATUM[\"D_WGS_1984\"," + \
                    "SPHEROID[\"WGS_1984\",6378137.0,298.257223563]]," + \
                "PRIMEM[\"Greenwich\",0.0]," + \
                "UNIT[\"Degree\",0.017453292519943295]]," + \
            "PROJECTION[\"Mercator_Auxiliary_Sphere\"]," + \
            "PARAMETER[\"False_Easting\",0.0]," + \
            "PARAMETER[\"False_Northing\",0.0]," + \
            "PARAMETER[\"Central_Meridian\",0.0]," + \
            "PARAMETER[\"Standard_Parallel_1\",0.0]," + \
            "PARAMETER[\"Auxiliary_Sphere_Type\",0.0]," + \
            "UNIT[\"Meter\",1.0]]"
    nc_mercator.GeoTransform = "{} {} 0 {} 0 {}".format(xleft, dx, ytop, -dy)

    # interpolate solution and write to NC file
    for fno in range(frame_bg, frame_ed):

        print("Frame No.", fno)

        # determine whether to read aux
        auxpath = os.path.join(outputpath, "fort.a"+"{}".format(fno).zfill(4))
        if os.path.isfile(auxpath):
            aux = True
        else:
            aux = False
        if os.path.isfile("./_output/fort.a" + "{}".format(fno).zfill(4)):
            aux = True

        soln = pyclaw.Solution()
        soln.read(fno, outputpath, file_format="binary", read_aux=aux)

        nc_times[fno-frame_bg] = soln.state.t
        nc_depth[fno-frame_bg, :, :] = interpolate(
            soln, x, y, level=args.level, nodatavalue=-9999.)

    print("Closing NC file {}".format(ncfilename))
    rootgrp.close()
