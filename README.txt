Here are four cross-platform Python GUI programs which facilitate working with DEMs.
They are mostly based on xdem and geoutils.

In naming and processing order:

dem_coreg_gui               Coregister a DEM to a reference, with unstable terrain mask
dh_debias_pleiades_gui      Correct North-South undulation bias of a Pléiades dh map, with unstable terrain mask
dh_filter_gui               Elevation-band SD filtering of outliers within polygons in a dh map
dh_hypso_gui                Compute gapfilled (idw or hypso) mean change over polygons as well as Hugonnet2022 uncertainty of mean elevation change


To install on Windows, double-click file setup.bat and let it work. It will prepare the right Python version and all required modules.
To install on Linux, use $ python -m pip install -r requirements.txt

To run a program on Windows, double-click on it (for example dem_coreg.vbs).
To run a program on Linux, use for example $ python src/dem_coreg_gui.pyw.

Enrico Mattea, 18.02.2025
