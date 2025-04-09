# This is a small GUI program to apply elevation-band-wise SD-based filtering of
# outliers on a dh map.
# It is cross-platform and handles geoutils exceptions nicely (error textboxes).
# The reference DEM (for the elevation bands) can have any georeferencing,
# it will be reprojected to the dh grid in case it is needed.
# Author: Enrico Mattea.
# Last change: 2025/02/12.


# Modules for GUI
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading

# Needed by more than one function
import numpy as np

def handle_error(exception_message, progress_bar_window, root):
    """Handles exceptions by showing the error message and quitting the program."""
    progress_bar_window.destroy()
    messagebox.showerror("Filtering error", exception_message)
    root.quit()


def update_progress_bar(progress_bar, step):
    current_value = progress_bar["value"]
    new_value = min(current_value + step, 100)
    progress_bar["value"] = new_value
    return new_value


def update_progress_label(progress_label, text):
    """Update the progress text in the progress window"""
    progress_label.config(text=text)


def filter_outliers_single(dh_r, dem_ref_r, poly_v, sd_coeff):
	"""
	Compute outlier-filtering mask for a raster elevation change map,
	based on standard deviation in elevation bands (derived from a reference DEM),
	within a single polygon.

	Parameters:
	- dh_r: geoutils.Raster map of elevation change to filter.
	- dem_ref_r: geoutils.Raster reference DEM raster map (for true elevation values). It must have the same shape as the dh map.
	- poly_v: single-row geoDataframe with the polygon within which the filtering is done.

	Returns:
	- mask_filter (a numpy array, same shape as the dh map, with True on outlier cells).
	"""


	# Rasterize the polygon vector to a raster mask of the same shape as the input rasters
	poly_r = ~poly_v.create_mask(raster = dh_r)

	# Set the mask on both the dh map and the DEM map using the rasterized mask.
	# We work on copies, otherwise we are altering the original data which we need to filter multiple polygons.
	dh_proc_r = dh_r.copy()
	dem_ref_proc_r = dem_ref_r.copy()

	# Save the original mask of dh, that is, the data gaps.
	# We need it to figure out how many new outliers we have removed.
	dh_gaps_mask_arr = dh_proc_r.get_mask()

	dh_proc_r.set_mask(poly_r)
	dem_ref_proc_r.set_mask(poly_r)

	# Extract reference DEM values (elevation) over the polygon mask.
	# This is a numpy array with same shape as the grids.
	dem_values_arr = dem_ref_proc_r.get_nanarray()

	# Generate eleband boundaries, aiming for 10 elebands with vertical extent not wider than 50 m
	elevation_min = np.nanmin(dem_values_arr)
	elevation_max = np.nanmax(dem_values_arr)
	elevation_range = elevation_max - elevation_min
	eleband_size = min(elevation_range / 10, 50)  # Ensure each eleband has a maximum vertical extent of 50 m
	eleband_mins = np.arange(elevation_min, elevation_max - eleband_size, eleband_size)
	eleband_maxs = eleband_mins + eleband_size
	eleband_mins[0] = eleband_mins[0] - 1 # Give floating-point safety margin to the extreme elebands
	eleband_maxs[-1] = eleband_maxs[-1] + 1
	eleband_n = len(eleband_mins)

	# We will use this mask (boolean array, same shape as the full dh map)
	# as filter corresponding to the current polygon.
	# We will update it for each elevation band.
	# True means remove a cell, False means keep.
	# We start with all False.
	poly_filter_mask_arr = np.zeros_like(dem_values_arr, dtype = bool)

	# Loop over each eleband to find outliers.
	for i in range(eleband_n):
		lower_bound = eleband_mins[i]
		upper_bound = eleband_maxs[i]

		# Find grid cells that fall within the current elevation eleband.
		eleband_mask_arr = (dem_values_arr > lower_bound) & (dem_values_arr <= upper_bound)

		# If there are more than 2 cells in this eleband, proceed
		# (otherwise hypsometric filtering is irrelevant).
		if np.sum(eleband_mask_arr) > 2:
			eleband_dh_values = dh_proc_r.data[eleband_mask_arr]

			# Compute the median and standard deviation of the dh values for this eleband
			eleband_dh_median = np.ma.median(eleband_dh_values)
			eleband_dh_sd = np.ma.std(eleband_dh_values, ddof = 1) # ddof = 1 for (N-1) denominator, consistent with R.

			# If the entire elevation band has no dh data, the median and sd are masked and are not suitable for calculation of the outlier mask.
			# In that case, we set them to 0 (there is nothing to filter here anyway).
			if np.ma.is_masked(eleband_dh_median):
				eleband_dh_median = 0
				eleband_dh_sd = 0

			# Identify outliers (values outside 3 standard deviations of the median).
			# We do this on the full grid, to preserve cell indexing.
			# dh_proc_r is anyway masked, so this is just a mask over
			# the glacier polygon - should be fast.
			# This is just a boolean numpy array.
			outlier_mask_arr = (np.abs(dh_proc_r - eleband_dh_median) > sd_coeff * eleband_dh_sd).get_nanarray()
			# Combine outlier_mask_arr with eleband_mask_arr, to find out what we should filter out in the current eleband.
			eleband_outlier_mask_arr = eleband_mask_arr & outlier_mask_arr

			# Add the new outlier values to the polygon mask.
			poly_filter_mask_arr = poly_filter_mask_arr | eleband_outlier_mask_arr

	# Remove from the filtering array all the cells which were already masked:
	# we want to know how many outliers we are discarding,
	# without considering the pre-existing data gaps.
	# So, we get an array which is True (outlier) where:
	# there is a missing value, and it is NOT in the initial dh_gaps_mask_arr.
	poly_filter_mask_arr = poly_filter_mask_arr & ~dh_gaps_mask_arr

	return(poly_filter_mask_arr)


def run_filtering(file_paths, sd_coeff, progress_bar_window, progress_bar, progress_bar_label, root):
    """
    Filter dh outliers in elevation bands, iterating over all the polygons of the given polygon file.
    file_paths has the paths to the dh grid, the reference DEM and he glacier polygons.
    """


    # Hide main window during processing, to avoid potential mess.
    root.withdraw()

    # Begin with some progress! We update the progress bar on the main thread.
    progress_bar.after(0, update_progress_bar, progress_bar, 10)




    # Import all needed modules. We do it only here so that the GUI loads faster.
    progress_bar.after(0, update_progress_label, progress_bar_label, "Loading modules...")
    from geoutils import Raster, Vector

    # Modules to define output file path.
    from os.path import abspath as path_abspath, basename as path_basename, dirname as path_dirname, join as path_join
    from re import sub

    # Module for error handling.
    from traceback import format_exc

    progress_bar.after(0, update_progress_bar, progress_bar, 5)




    progress_bar.after(0, update_progress_label, progress_bar_label, "Loading input data...")
    try:

        dh_r = Raster(file_paths[0])
        dh_r.load()
        progress_bar.after(0, update_progress_bar, progress_bar, 2)

        dem_ref_r = Raster(file_paths[1])
        dem_ref_r.load()
        progress_bar.after(0, update_progress_bar, progress_bar, 2)

        polys_v = Vector(file_paths[2])
        progress_bar.after(0, update_progress_bar, progress_bar, 11)

        # Make an untouched copy of the dh map, to which we will apply the filtering masks.
        dh_orig_r = dh_r.copy()

        # This will be the final filtering mask, filled progressively by each polygon.
        full_outliers_mask_arr = np.zeros_like(dh_orig_r.get_nanarray(), dtype = bool)
    except Exception as error:
        exceptionlast = format_exc().splitlines()[-1]
        handle_error(f"There was an error loading the input data:\n\n{exceptionlast}\n\nNo output was generated, please correct the error and run the program again.\n\nClick OK to exit.", progress_bar_window, root)


    try:
        if not dh_r.georeferenced_grid_equal(dem_ref_r):
            progress_bar_window.attributes("-topmost", 0) # Bring down the progress bar, to show the message box on top.
            messagebox.showinfo("Geotransform mismatch", "WARNING: the grids of elevation change and of the reference DEM have different georeferencing! I am reprojecting the DEM.\n\nClick OK to continue, but make sure that the input is as you want it.")
            progress_bar_window.attributes("-topmost", -1) # Bring back up the progress bar after user clicks OK.
            dem_ref_r.reproject(ref = dh_r, resampling = "bilinear", inplace = True, memory_limit = 512)
    except Exception as error:
        exceptionlast = format_exc().splitlines()[-1]
        handle_error(f"There was an error reprojecting the reference DEM:\n\n{exceptionlast}\n\nNo output was generated, please correct the error and run the program again.\n\nClick OK to exit.", progress_bar_window, root)

    poly_n = len(polys_v.ds)

    if poly_n == 0:
        handle_error(f"There are no valid polygons in file {path_basename(file_paths[2])}, there is no filtering to do. No output was generated, please check the polygons file and run the program again.\n\nClick OK to exit.", progress_bar_window, root)


    step_cur = 60 / max(1, poly_n) # Progress bar is at 30 %, after polygon filtering we will be at 90 %. We use max() just to avoid throwing an extra error in case poly_n is 0 (since we have 2 threads)
    for poly_id in range(poly_n):
        progress_bar.after(0, update_progress_label, progress_bar_label, f"Filtering: {poly_id+1} / {poly_n}...")
        try:
            poly_cur_v = Vector(polys_v.ds.iloc[[poly_id]])
        except Exception as error:
            exceptionlast = format_exc().splitlines()[-1]
            handle_error(f"There was an error selecting the polygon number {poly_id}:\n\n{exceptionlast}\n\nNo output was generated, please correct the error and run the program again.\n\nClick OK to exit.", progress_bar_window, root)

        try:
            poly_filter_mask_arr = filter_outliers_single(dh_r, dem_ref_r, poly_cur_v, sd_coeff)
        except Exception as error:
            exceptionlast = format_exc().splitlines()[-1]
            handle_error(f"There was an error filtering the dh map within polygon number {poly_id}:\n\n{exceptionlast}\n\nNo output was generated, please correct the error (check the input files!) and run the program again.\n\nClick OK to exit.", progress_bar_window, root)

        try:
            full_outliers_mask_arr = full_outliers_mask_arr | poly_filter_mask_arr
        except Exception as error:
            exceptionlast = format_exc().splitlines()[-1]
            handle_error(f"There was an error with the outliers found within polygon number {poly_id}:\n\n{exceptionlast}\n\nNo output was generated, please correct the error and run the program again.\n\nClick OK to exit.", progress_bar_window, root)
        progress_bar.after(0, update_progress_bar, progress_bar, step_cur)


    progress_bar.after(0, update_progress_label, progress_bar_label, "Writing output...")
    out_dirpath=path_dirname(file_paths[0])
    out_fn=sub("(\.[\w]{1,})$", r"_filter_{}\1".format(sd_coeff), path_basename(file_paths[0])) # Add _filter just before the file extension.
    out_path=path_join(path_abspath(out_dirpath), out_fn)


    dh_orig_r.set_mask(full_outliers_mask_arr)

    try:
        dh_orig_r.save(out_path)
        progress_bar.after(0, update_progress_bar, progress_bar, 10)
    except Exception as error:
        exceptionlast = format_exc().splitlines()[-1]
        handle_error(f"There was an error saving the output of filtering:\n\n{exceptionlast}\n\nThe output could be missing or wrong, please correct the error and run the program again.\n\nClick OK to exit.", progress_bar_window, root)




    progress_bar_window.destroy()  # Close the progress window when the task is done
    messagebox.showinfo("Filtering finished", f"Filtering finished successfully. Removed {np.sum(full_outliers_mask_arr)} outliers. The output file is located here:\n\n" + out_path + "\n\nClick OK to exit.")
    root.quit()



def start_process(file_paths, sd_coeff, progress_bar_window, progress_bar, progress_bar_label, root):
    """Start the long-running function in a separate thread"""
    progress_bar_window.deiconify()  # Show the progress window
    progress_bar_window.attributes("-topmost", 1) # Bring the progress window to top

    # Run the long-running function in a separate thread to keep UI responsive
    # sd_coeff.get() retrieves the value from the radio buttons.
    threading.Thread(target=run_filtering, args=(file_paths, sd_coeff.get(), progress_bar_window, progress_bar, progress_bar_label, root), daemon=True).start()


def file_selector(entry, file_paths, button, idx):
    """Open file dialog and update entry box and file_paths list"""
    file_path = filedialog.askopenfilename()
    if file_path:
        entry.delete(0, tk.END)
        entry.insert(0, file_path)
        file_paths[idx] = file_path
    check_button_state(file_paths, button)


def check_button_state(file_paths, button):
    """Enable/Disable the button based on file paths"""
    if all(file_paths):  # Check if all paths are selected
        button.config(state=tk.NORMAL)  # Enable button when all files are selected
    else:
        button.config(state=tk.DISABLED)  # Keep button disabled until all files are selected


def on_entry_change(entry, file_paths, button, idx):
    """Callback function to track changes in entries"""
    file_paths[idx] = entry.get().strip()  # Update the file path from the entry
    check_button_state(file_paths, button)


def create_main_window():
    """Create the main window with the UI components"""
    root = tk.Tk()
    root.title("Filtering of elevation change maps")

    file_paths = [None, None, None]  # Store paths of the three selected files

    # Configure grid
    root.grid_rowconfigure(0, weight=1)
    root.grid_rowconfigure(1, weight=0)  # For the process button
    root.grid_columnconfigure(0, weight=0)  # For labels
    root.grid_columnconfigure(1, weight=1)  # For entry fields
    root.grid_columnconfigure(2, weight=1)  # For entry fields.
    root.grid_columnconfigure(3, weight=20) # For entry fields. weight=20 to have the three radio buttons on the left.
    root.grid_columnconfigure(4, weight=0)  # For buttons
    # root.grid_columnconfigure(0, weight=0)  # For labels
    # root.grid_columnconfigure(1, weight=1)  # For entry fields
    # root.grid_columnconfigure(2, weight=0)  # For buttons

    # Title and text above file selectors
    title_label = tk.Label(root, text="Hypsometric filtering of a dh grid", font=("Helvetica", 16))
    title_label.grid(row=0, column=0, columnspan=5, pady=5)

    info_label = tk.Label(root, text="Please select the grid of elevation change that should be filtered, a reference DEM (no gaps!), and a shapefile with the glacier polygons that should be filtered, then click on \"Start filtering\".", anchor="w")
    info_label.grid(row=1, column=0, columnspan=5, padx=10, pady=5, sticky="w")

    # File selectors
    file_selector_labels = ["Elevation change grid", "Reference DEM", "Shapefile of glacier polygons"]
    entries = []
    for idx, label in enumerate(file_selector_labels):
        lbl = tk.Label(root, text=label, anchor="w")
        lbl.grid(row=idx+2, column=0, padx=10, pady=5, sticky="w")

        entry = tk.Entry(root, width=100)
        entry.grid(row=idx+2, column=1, columnspan=3, padx=5, pady=5, sticky="ew")
        entries.append(entry)

        # Bind the entry change to the callback function
        entry.bind("<KeyRelease>", lambda e, idx=idx: on_entry_change(entries[idx], file_paths, process_button, idx))

        btn = tk.Button(root, text="Browse", command=lambda idx=idx: file_selector(entries[idx], file_paths, process_button, idx))
        btn.grid(row=idx+2, column=4, padx=5, pady=5)


    # Radio buttons to select SD coefficient for filtering (1, 2, 3)
    # Create a Tkinter variable to hold the selected radio button value
    sd_coeff = tk.IntVar(value=3)  # Default to 3

    # Create buttons
    radios_lbl = tk.Label(root, text="Select SD coefficient", anchor="w")
    radios_lbl.grid(row=5, column=0, padx=10, pady=5, sticky="w")
    radio1 = tk.Radiobutton(root, text="1", variable=sd_coeff, value=1)
    radio1.grid(row=5, column=1, pady=10, sticky="w")
    radio2 = tk.Radiobutton(root, text="2", variable=sd_coeff, value=2)
    radio2.grid(row=5, column=2, pady=10, sticky="w")
    radio3 = tk.Radiobutton(root, text="3", variable=sd_coeff, value=3)
    radio3.grid(row=5, column=3, columnspan=2, pady=10, sticky="w")


    # Button to trigger the process
    process_button = tk.Button(root, text="Start filtering", state=tk.DISABLED,
                                command=lambda: start_process(file_paths, sd_coeff, progress_bar_window, progress_bar, progress_bar_label, root))
    process_button.grid(row=6, column=0, columnspan=5, pady=10)

    # Progress dialog window (hidden initially)
    progress_bar_window = tk.Toplevel(root)
    progress_bar_window.withdraw()  # Initially hide the progress window
    progress_bar_window.title("Filtering progress")

    progress_bar_label = tk.Label(progress_bar_window, text="Processing...")
    progress_bar_label.pack(pady=10)

    progress_bar = ttk.Progressbar(progress_bar_window, orient="horizontal", length=300, mode="determinate")
    progress_bar.pack(pady=20)

    # Start the Tkinter main loop
    root.mainloop()


if __name__ == "__main__":
    create_main_window()

