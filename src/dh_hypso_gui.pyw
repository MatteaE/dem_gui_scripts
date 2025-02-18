# This is a small GUI program (xdem-based) to compute normalized hypsometric mean dh change over glacier polygons
# as well as the corresponding integrated uncertainty (Hugonnet framework).
# It is cross-platform and handles xdem exceptions nicely (error textboxes).
# Author: Enrico Mattea.
# Last change: 2025/02/18.



# Modules for GUI
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading

# Needed by more than one function, so we import it here
import numpy as np

def handle_error(exception_message, progress_bar_window, root):
    """Handles exceptions by showing the error message and quitting the program."""
    progress_bar_window.destroy()
    messagebox.showerror("Processing error", exception_message)
    root.quit()


def update_progress_bar(progress_bar, step):
    current_value = progress_bar["value"]
    new_value = min(current_value + step, 100)
    progress_bar["value"] = new_value
    return new_value


def update_progress_label(progress_label, text):
    """Update the progress text in the progress window"""
    progress_label.config(text=text)


# We work with a dh of class dDEM, on which we can run the (hypsometric or IDW) interpolation.
def dh_interpolate(dh_r, dem_ref_r, poly_v, interp_type):
    poly_r = ~poly_v.create_mask(raster = dh_r)
    dh_proc_r = dh_r.copy()
    dh_proc_r.set_mask(poly_r)

    # If the Numpy array is fully masked, it means we have no valid data within
    # our polygon, thus we have no interpolation to do and we return an empty grid.
    if (dh_r.data[~poly_r.data.data]).mask.all():
        return(dh_proc_r)

    dh_proc_interp_arr = dh_proc_r.interpolate(method=interp_type, reference_elevation=dem_ref_r, mask=poly_v)
    dh_proc_interp_r = dh_proc_r.copy(new_array = dh_proc_interp_arr)
    return(dh_proc_interp_r)




# Run the full Hugonnet2022 uncertainty workflow (heteroscedasticity and variogram modeling).
# Returns: error standardization factor, parameters of the fitted variogram, dh_err map,
# all ready to apply to the uncertainty of single polygons.
# This function advances the progress bar by 26 % .
def analyze_uncertainties(dh_r, dem_ref_r, unstable_polys_v, file_paths, progress_bar, progress_bar_label):

    import xdem

    # To plot integrated variogram
    import matplotlib.pyplot as plt

    # To save the plot
    from os.path import dirname as path_dirname, join as path_join

    progress_bar.after(0, update_progress_label, progress_bar_label, "Preparing input to compute uncertainty...")
    unstable_mask_r = unstable_polys_v.create_mask(dh_r)

    slope, aspect, planc, profc = xdem.terrain.get_terrain_attribute(dem=dem_ref_r, attribute=["slope", "aspect", "planform_curvature", "profile_curvature"])

    # Convert to arrays, masking out unstable terrain.
    dh_arr = dh_r[~unstable_mask_r].filled(np.nan)
    slope_arr = slope[~unstable_mask_r].filled(np.nan)
    planc_arr = planc[~unstable_mask_r].filled(np.nan)
    profc_arr = profc[~unstable_mask_r].filled(np.nan)
    maxc_arr = np.maximum(np.abs(planc_arr), np.abs(profc_arr))

    progress_bar.after(0, update_progress_bar, progress_bar, 15)
    progress_bar.after(0, update_progress_label, progress_bar_label, "Binning slope and curvature...")
    custom_bin_slope = np.unique(
        np.concatenate(
            [
                np.nanquantile(slope_arr, np.linspace(0, 0.95, 20)),
                np.nanquantile(slope_arr, np.linspace(0.96, 0.99, 5)),
                np.nanquantile(slope_arr, np.linspace(0.991, 1, 10)),
            ]
        )
    )

    custom_bin_curvature = np.unique(
        np.concatenate(
            [
                np.nanquantile(maxc_arr, np.linspace(0, 0.95, 20)),
                np.nanquantile(maxc_arr, np.linspace(0.96, 0.99, 5)),
                np.nanquantile(maxc_arr, np.linspace(0.991, 1, 10)),
            ]
        )
    )

    df = xdem.spatialstats.nd_binning(
        values=dh_arr,
        list_var=[slope_arr, maxc_arr],
        list_var_names=["slope", "maxc"],
        statistics=["count", np.nanmedian, xdem.spatialstats.nmad],
        list_var_bins=[custom_bin_slope, custom_bin_curvature],
    )

    unscaled_dh_err_fun = xdem.spatialstats.interp_nd_binning(
        df, list_var_names=["slope", "maxc"], statistic="nmad", min_count=30
    )
    dh_err_stable = unscaled_dh_err_fun((slope_arr, maxc_arr))


    zscores, dh_err_fun = xdem.spatialstats.two_step_standardization(
        dh_arr, list_var=[slope_arr, maxc_arr], unscaled_error_fun=unscaled_dh_err_fun
    )


    # This is again maximum curvature, but with a different array shape.
    maxc = np.maximum(np.abs(profc), np.abs(planc))
    dh_err = dh_r.copy(new_array=dh_err_fun((slope.data, maxc.data)))
    # End heteroscedasticity modeling -------------------------------------------------------------

    # Begin variogram modeling --------------------------------------------------------------------
    z_dh = dh_r.data / dh_err

    # Filter out unstable terrain and large outliers.
    z_dh.data[unstable_mask_r.data] = np.nan
    z_dh.data[np.abs(z_dh.data) > 4] = np.nan

    scale_fac_std = xdem.spatialstats.nmad(z_dh.data)
    z_dh = z_dh / scale_fac_std


    progress_bar.after(0, update_progress_bar, progress_bar, 8)
    progress_bar.after(0, update_progress_label, progress_bar_label, "Sampling variogram...")
    df_vgm = xdem.spatialstats.sample_empirical_variogram(
        values=z_dh.data.squeeze(), estimator = "dowd", gsd=dh_r.res[0], subsample=300, n_variograms=10, random_state=42
    )

    maxfev = 10000
    func_sum_vgm, params_vgm = xdem.spatialstats.fit_sum_model_variogram(
        list_models=["Exponential", "Exponential"], empirical_variogram=df_vgm, maxfev=maxfev
    )


    # Integrate variogram over various surface areas
    areas = [4000 * 2 ** (i) for i in range(3,15,1)]
    stderr_vgm_list = []
    for area in areas:

        # print(f"Area: {area:.0f} m²")
        # Number of effective samples integrated over the area.
        # This is the contribution from the variogram.
        # Numerator is 1 because we use the standardized error, whose mean is 1.
        neff_vgm = xdem.spatialstats.number_effective_samples(area, params_vgm)
        stderr_vgm = 1 / np.sqrt(neff_vgm)
        stderr_vgm_list.append(stderr_vgm)


    # Compute Monte-Carlo sampling of the integrated error, to be
    # plotted alongside the error estimated with the variogram models.
    # We do this using the standardized error, to be comparable with
    # the variogram results.
    progress_bar.after(0, update_progress_bar, progress_bar, 7)
    progress_bar.after(0, update_progress_label, progress_bar_label, "Validation with patches method...")
    df_patches = xdem.spatialstats.patches_method(z_dh, gsd=dh_r.res[0], areas=areas)


    progress_bar.after(0, update_progress_bar, progress_bar, 4)
    progress_bar.after(0, update_progress_label, progress_bar_label, "Plot of uncertainty by area...")
    # Plot standardized uncertainty by averaging area and fully correlated variance.
    fig, ax = plt.subplots()

    plt.plot(np.asarray(areas) / 1000000, stderr_vgm_list, label = "Modeled variogram")

    plt.scatter(
        df_patches.exact_areas.values / 1000000,
        df_patches.nmad.values,
        label="Empirical estimate",
        color="black",
        marker="x",
    )
    plt.xlabel("Averaging area (km²)")
    plt.ylabel("Uncertainty in the mean standardized elevation difference [-]")
    plt.xscale("log")
    plt.yscale("log")
    plt.legend(loc="lower left")
    plt.savefig(path_join(path_dirname(file_paths[0]), "std_uncertainty_by_area.png"))
    plt.close()

    progress_bar.after(0, update_progress_bar, progress_bar, 2)

    return((scale_fac_std, params_vgm, dh_err))




# Compute integrated dh change uncertainty over a single polygon
# using the calculated variogram from analyze_uncertainties().
def compute_poly_uncertainty(gl_poly_cur_v, dh_r, params_vgm, scale_fac_std, dh_err):

    import xdem
    import numpy as np

    gl_poly_mask = gl_poly_cur_v.create_mask(dh_r)

    # If the Numpy array is fully masked, it means we have no valid data within
    # our polygon, thus we skip the rest of processing for the current polygon.
    if (dh_r.data[gl_poly_mask.data]).mask.all():
        return(np.nan)

    else:

        # Compute number of effective samples for the polygon according to the current variogram model.
        poly_neff = xdem.spatialstats.neff_circular_approx_numerical(
            area=gl_poly_cur_v.ds.area.values[0], params_variogram_model=params_vgm
        )
        poly_z_err_vgm       = 1 / np.sqrt(poly_neff)

        # Destandardize the spatially integrated uncertainty based on the measurement error dependent on slope and
        # maximum curvature. This yields the uncertainty into the mean elevation change for the selected polygon.
        fac_poly_dh_err = scale_fac_std * np.nanmean(dh_err[gl_poly_mask.data])
        poly_dh_err = fac_poly_dh_err * poly_z_err_vgm

        # Disabled here: rescale poly dh err considering factor of 5 for gaps.
        # This is the formula of Dussaillant et al. (2018) for uncertainty of gaps.
        # We don't use it anymore since it does not account for heteroscedasticity:
        # instead, we directly multiply by 5 the dh_err map on gaps.
        # We have verified that the result is anyway very similar.
        # poly_cells_n = np.sum(gl_poly_mask.data.data)
        # poly_valid_cells_n = np.sum(gl_poly_mask.data.data & ~dh_r.get_mask())
        # poly_valid_fraction = poly_valid_cells_n / poly_cells_n
        # poly_dh_err = poly_dh_err * (5 * (1 - poly_valid_fraction) + poly_valid_fraction)

        return(poly_dh_err)




def run_processing(file_paths, interpolation_method, progress_bar_window, progress_bar, progress_bar_label, root):
    """
    Gap-fill the DEM with the chosen method,
    compute mean dh over each polygon,
    run Hugonnet2022 uncertainty analysis,
    compute per-polygon integrated uncertainty.
    We write:
    (1) the gap-filled dh grid,
    (2) the plot with variogram and patches method,
    (3) a vector file with two new columns (mean dh and mean dh err)
    """

    # Hide main window during processing, to avoid potential mess.
    root.withdraw()

    # Begin with some progress! We update the progress bar on the main thread.
    # Progress bar goes to 10 %.
    progress_bar.after(0, update_progress_bar, progress_bar, 10)




    # Import all needed modules. We do it only here so that the GUI loads faster.
    progress_bar.after(0, update_progress_label, progress_bar_label, "Loading modules...")
    from datetime import datetime
    from geoutils import Vector
    import xdem

    # Modules to define output file path.
    from os.path import abspath as path_abspath, basename as path_basename, dirname as path_dirname, join as path_join
    from re import sub

    # Module for error handling.
    from traceback import format_exc

    # Progress bar goes to 15 %.
    progress_bar.after(0, update_progress_bar, progress_bar, 5)



    # Load input data.
    # Progress bar goes to 23 %.
    progress_bar.after(0, update_progress_label, progress_bar_label, "Loading input data...")
    try:

        dh_r = xdem.dDEM(xdem.DEM(file_paths[0]), start_time=datetime(2000, 1, 1), end_time=datetime(2001, 1, 1)) # start and end time are required but unused.
        dh_r.load()

        dem_ref_r = xdem.DEM(file_paths[1])
        dem_ref_r.load()

        gl_polys_v = Vector(file_paths[2])

        unstable_polys_v = Vector(file_paths[3])
        progress_bar.after(0, update_progress_bar, progress_bar, 8)

    except Exception as error:
        exceptionlast = format_exc().splitlines()[-1]
        handle_error(f"There was an error loading the input data:\n\n{exceptionlast}\n\nNo output was generated, please correct the error and run the program again.\n\nClick OK to exit.", progress_bar_window, root)


    try:
        if not dh_r.georeferenced_grid_equal(dem_ref_r):
            progress_bar_window.attributes("-topmost", 0)
            messagebox.showinfo("Geotransform mismatch", "WARNING: the grids of elevation change and of the reference DEM have different georeferencing! I am reprojecting the DEM.\n\nClick OK to continue, but make sure that the input is as you want it.")
            progress_bar_window.attributes("-topmost", -1)
            dem_ref_r.reproject(ref = dh_r, resampling = "bilinear", inplace = True, memory_limit = 512)
    except Exception as error:
        exceptionlast = format_exc().splitlines()[-1]
        handle_error(f"There was an error reprojecting the reference DEM:\n\n{exceptionlast}\n\nNo output was generated, please correct the error and run the program again.\n\nClick OK to exit.", progress_bar_window, root)

    gl_poly_n = len(gl_polys_v.ds)
    if gl_poly_n == 0:
        handle_error(f"There are no valid glacier polygons in file {path_basename(file_paths[2])}, there is nothing to calculate. No output was generated, please check the glacier polygons file and run the program again.\n\nClick OK to exit.", progress_bar_window, root)


    # Gap-fill the dh map within each glacier polygon.
    # Progress bar goes to 50 %.
    step_cur = 27 / max(1, gl_poly_n) # We use max() just to avoid throwing an extra error in case gl_poly_n is 0 (since we have 2 threads)
    dh_gapfilled_r = dh_r.copy()     # This will be the gap-filled copy of the dh map.
    gl_polys_v.ds["dh_mean_m"] = np.nan # Add column to put the mean dh values
    for gl_poly_id in range(gl_poly_n):
        progress_bar.after(0, update_progress_label, progress_bar_label, f"Calculating mean change: {gl_poly_id+1} / {gl_poly_n}...")
        try:
            gl_poly_cur_v = Vector(gl_polys_v.ds.iloc[[gl_poly_id]])

            # Here use the method decided by the radio button
            dh_interp_cur_r = dh_interpolate(dh_r, dem_ref_r, gl_poly_cur_v, interpolation_method)


            dh_values_arr = dh_interp_cur_r.get_nanarray()
            dh_values_mask = dh_interp_cur_r.get_mask()

            # Compute and store mean dh change.
            dh_mean = np.nanmean(dh_values_arr)

            gl_polys_v.ds.loc[gl_poly_id, "dh_mean_m"] = dh_mean

            # Paste gap-filled data into the dh map, which we will later save.
            dh_gapfilled_r.data[~dh_values_mask] = dh_values_arr[~dh_values_mask]

            progress_bar.after(0, update_progress_bar, progress_bar, step_cur)

        except Exception as error:
            exceptionlast = format_exc().splitlines()[-1]
            handle_error(f"There was an error calculating the gap-filled mean for polygon number {gl_poly_id}:\n\n{exceptionlast}\n\nNo output was generated, please correct the error and run the program again.\n\nClick OK to exit.", progress_bar_window, root)



    progress_bar.after(0, update_progress_label, progress_bar_label, "Saving files with mean dh change...")
    # Save updated polygons file with added mean dh column.
    try:
        gl_polys_out_dirpath=path_dirname(file_paths[2])
        gl_polys_out_fn=sub("(\.[\w]{1,})$", r"_dh_mean_{}\1".format(interpolation_method), path_basename(file_paths[2])) # Add _dh_mean just before the file extension.
        gl_polys_out_path=path_join(path_abspath(gl_polys_out_dirpath), gl_polys_out_fn)
        gl_polys_v.save(gl_polys_out_path)
    except Exception as error:
        exceptionlast = format_exc().splitlines()[-1]
        handle_error(f"There was an error saving the glacier polygons file with mean dh information:\n\n{exceptionlast}\n\nPlease correct the error and run the program again.\n\nClick OK to exit.", progress_bar_window, root)



    # Save gapfilled dh file.
    # Progress bar goes to 54 %.
    try:
        dh_gapfilled_out_dirpath=path_dirname(file_paths[0])
        dh_gapfilled_out_fn=sub("(\.[\w]{1,})$", r"_gapfilled_{}\1".format(interpolation_method), path_basename(file_paths[0])) # Add _filter just before the file extension.
        dh_gapfilled_out_path=path_join(path_abspath(gl_polys_out_dirpath), dh_gapfilled_out_fn)
        dh_gapfilled_r.save(dh_gapfilled_out_path)
        progress_bar.after(0, update_progress_bar, progress_bar, 4)
    except Exception as error:
        exceptionlast = format_exc().splitlines()[-1]
        handle_error(f"There was an error saving the gap-filled map of mean elevation change:\n\n{exceptionlast}\n\nPlease correct the error and run the program again.\n\nClick OK to exit.", progress_bar_window, root)




    # Run Hugonnet2022 uncertainty analysis, to get the
    # parameters to estimate polygon-wise uncertainty.
    # Progress bar goes to 90 %.
    try:
        scale_fac_std, params_vgm, dh_err = analyze_uncertainties(dh_r, dem_ref_r, unstable_polys_v, file_paths, progress_bar, progress_bar_label)

        # Estimate the error over gaps: factor of 5.
        # We multiply by 5 each cell where the input
        # dh map has no data (Berthier et al., 2014).
        dh_err.data[dh_r.get_mask()] = 5 * dh_err.data[dh_r.get_mask()]


    except Exception as error:
        exceptionlast = format_exc().splitlines()[-1]
        handle_error(f"There was an error with the statistical calculation of uncertainty:\n\n{exceptionlast}\n\nUncertainty was NOT calculated (but the mean elevation change was). Please correct the error and run the program again.\n\nClick OK to exit.", progress_bar_window, root)



    # Compute uncertainty for each polygon.
    # Progress bar goes to 98 %.
    step_cur = 8 / max(1, gl_poly_n)
    gl_polys_v.ds["dh_mean_err_m"] = np.nan # Add column to put the mean dh error values
    for gl_poly_id in range(gl_poly_n):
        progress_bar.after(0, update_progress_label, progress_bar_label, f"Calculating uncertainty by glacier: {gl_poly_id+1} / {gl_poly_n}...")
        try:
            gl_poly_cur_v = Vector(gl_polys_v.ds.iloc[[gl_poly_id]])
            gl_poly_cur_dh_err = compute_poly_uncertainty(gl_poly_cur_v, dh_r, params_vgm, scale_fac_std, dh_err)

            gl_polys_v.ds.loc[gl_poly_id, "dh_mean_err_m"] = gl_poly_cur_dh_err

            progress_bar.after(0, update_progress_bar, progress_bar, step_cur)

        except Exception as error:
            exceptionlast = format_exc().splitlines()[-1]
            handle_error(f"There was an error calculating the uncertainty for polygon number {gl_poly_id}:\n\n{exceptionlast}\n\nUncertainty was NOT calculated (but the mean elevation change was). Please correct the error and run the program again.\n\nClick OK to exit.", progress_bar_window, root)


    # Save updated polygons file with added mean dh err column.
    # Progress bar goes to 100 %.
    progress_bar.after(0, update_progress_label, progress_bar_label, "Adding uncertainties to polygon file...")
    try:
        gl_polys_v.save(gl_polys_out_path)
        progress_bar.after(0, update_progress_bar, progress_bar, 2)
    except Exception as error:
        exceptionlast = format_exc().splitlines()[-1]
        handle_error(f"There was an error updating the glacier polygons file with mean dh error information:\n\n{exceptionlast}\n\nPlease correct the error and run the program again.\n\nClick OK to exit.", progress_bar_window, root)


    progress_bar_window.destroy()  # Close the progress window when the task is done
    messagebox.showinfo("Calculation finished", f"Calculation finished successfully. The output files are located here:\n\n" + path_dirname(gl_polys_out_path) + "\n\nClick OK to exit.")
    root.quit()




def start_process(file_paths, interpolation_method, progress_bar_window, progress_bar, progress_bar_label, root):
    """Start the long-running function in a separate thread"""
    progress_bar_window.deiconify()  # Show the progress window
    progress_bar_window.attributes("-topmost", 1) # Bring the progress window to top

    # Run the long-running function in a separate thread to keep UI responsive
    # interpolation_method.get() retrieves the value from the radio buttons.
    threading.Thread(target=run_processing, args=(file_paths, interpolation_method.get(), progress_bar_window, progress_bar, progress_bar_label, root), daemon=True).start()


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
    root.title("Calculation of mean elevation change")

    file_paths = [None, None, None, None]  # Store paths of the four selected files - dh map, reference DEM, glaciers shapefile, unstable terrain shapefile.

    # Configure grid.
    # We use a 4-column layout because the second radio button should be close to the first one, on the left.
    root.grid_rowconfigure(0, weight=1)
    root.grid_rowconfigure(1, weight=0)  # For the process button
    root.grid_columnconfigure(0, weight=0)  # For labels
    root.grid_columnconfigure(1, weight=1)  # For entry fields
    root.grid_columnconfigure(2, weight=20)  # For entry fields. weight=20 to have the second radio button on the left.
    root.grid_columnconfigure(3, weight=0)  # For buttons

    # Title and text above file selectors
    title_label = tk.Label(root, text="Compute mean elevation change over glacier polygons", font=("Helvetica", 16))
    title_label.grid(row=0, column=0, columnspan=4, pady=5)

    info_label = tk.Label(root, text="Please select:\n\n· the grid of elevation change\n· a reference DEM (no gaps!)\n· a shapefile with the glacier polygons for aggregation\n· a shapefile with unstable terrain\n· the interpolation method for the elevation change grid\n\nthen click on \"Start calculation\".\n", anchor="w", justify=tk.LEFT)
    info_label.grid(row=1, column=0, columnspan=4, padx=10, pady=5, sticky="w")

    # File selectors
    file_selector_labels = ["Elevation change grid", "Reference DEM", "Shapefile of glacier polygons", "Shapefile of unstable terrain"]
    entries = []
    for idx, label in enumerate(file_selector_labels):
        lbl = tk.Label(root, text=label, anchor="w")
        lbl.grid(row=idx+2, column=0, padx=10, pady=5, sticky="w")

        entry = tk.Entry(root, width=100)
        entry.grid(row=idx+2, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        entries.append(entry)

        # Bind the entry change to the callback function
        entry.bind("<KeyRelease>", lambda e, idx=idx: on_entry_change(entries[idx], file_paths, process_button, idx))

        btn = tk.Button(root, text="Browse", command=lambda idx=idx: file_selector(entries[idx], file_paths, process_button, idx))
        btn.grid(row=idx+2, column=3, padx=5, pady=5)


    # Radio buttons
    # Create a Tkinter variable to hold the selected radio button value
    interpolation_method = tk.StringVar(value="idw")  # Default to Option 1

    # Create buttons
    radios_lbl = tk.Label(root, text="Select interpolation method", anchor="w")
    radios_lbl.grid(row=6, column=0, padx=10, pady=5, sticky="w")
    radio1 = tk.Radiobutton(root, text="Inverse-distance weighting", variable=interpolation_method, value="idw")
    radio1.grid(row=6, column=1, pady=10, sticky="w")
    radio2 = tk.Radiobutton(root, text="Local hypsometric", variable=interpolation_method, value="local_hypsometric")
    radio2.grid(row=6, column=2, columnspan=2, pady=10, sticky="w")



    # Button to trigger the process
    process_button = tk.Button(root, text="Start calculation", state=tk.DISABLED,
                                command=lambda: start_process(file_paths, interpolation_method, progress_bar_window, progress_bar, progress_bar_label, root))
    process_button.grid(row=7, column=0, columnspan=4, pady=10)

    # Progress dialog window (hidden initially)
    progress_bar_window = tk.Toplevel(root)
    progress_bar_window.withdraw()  # Initially hide the progress window
    progress_bar_window.title("Calculation progress")

    progress_bar_label = tk.Label(progress_bar_window, text="Processing...")
    progress_bar_label.pack(pady=10)

    progress_bar = ttk.Progressbar(progress_bar_window, orient="horizontal", length=300, mode="determinate")
    progress_bar.pack(pady=20)

    # Start the Tkinter main loop
    root.mainloop()


if __name__ == "__main__":
    create_main_window()

