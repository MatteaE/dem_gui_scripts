Here are four cross-platform Python GUI programs which facilitate working with DEMs.
They are mostly based on xdem and geoutils.

In naming and logical order:

dem_coreg_gui               Coregister a DEM to a reference, with unstable terrain mask
dh_debias_pleiades_gui      Correct North-South undulation bias of a Pléiades dh map
dh_filter_gui               Elevation-band SD filtering of outliers within polygons in a dh map
dh_hypso_gui                Compute gapfilled (idw or hypso) mean change over polygons as well as Hugonnet2022 uncertainty of mean elevation change


To compile for Windows: e.g.
> python -m nuitka --onefile --windows-console-mode=disable --enable-plugin=tk-inter dem_coreg_gui.pyw

Enrico Mattea, 17.02.2025
