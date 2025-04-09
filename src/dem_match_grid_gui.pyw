# This is a small GUI interface to call xdem grid matching of a DEM to a reference.
# It is cross-platform and handles xdem exceptions nicely (error textboxes).
# Author: Enrico Mattea.
# Last change: 2025/04/08.


# Modules for GUI
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading


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


def run_processing(file_paths, progress_bar_window, progress_bar, progress_bar_label, root):

    # Hide main window during processing, to avoid potential mess.
    root.withdraw()

    # Begin with some progress! We update the progress bar on the main thread.
    progress_bar.after(0, update_progress_bar, progress_bar, 10)




    # Import all needed modules. We do it only here so that the GUI loads faster.
    progress_bar.after(0, update_progress_label, progress_bar_label, "Loading modules...")
    from xdem import DEM

    # Modules to define output file path.
    from os.path import abspath as path_abspath, basename as path_basename, dirname as path_dirname, join as path_join
    from re import sub

    # Module for error handling.
    from traceback import format_exc

    progress_bar.after(0, update_progress_bar, progress_bar, 5)




    progress_bar.after(0, update_progress_label, progress_bar_label, "Loading input data...")
    try:
        # Load the reference DEM whose grid will be matched.
        ref_dem = DEM(file_paths[0])
        progress_bar.after(0, update_progress_bar, progress_bar, 2)
        # Load the DEM whose grid will match the reference.
        tba_dem = DEM(file_paths[1])
        progress_bar.after(0, update_progress_bar, progress_bar, 2)
    except Exception as error:
        exceptionlast = format_exc().splitlines()[-1]
        handle_error(f"There was an error loading the input data:\n\n{exceptionlast}\n\nNo output was generated, please correct the error and run the program again.\n\nClick OK to exit.", progress_bar_window, root)




    progress_bar.after(0, update_progress_label, progress_bar_label, "Matching the grids...")
    try:
        tba_newgrid_dem = tba_dem.reproject(ref = ref_dem)
        progress_bar.after(0, update_progress_bar, progress_bar, 71)
    except Exception as error:
        exceptionlast = format_exc().splitlines()[-1]
        handle_error(f"There was an error matching the grid:\n\n{exceptionlast}\n\nNo output was generated, please correct the error and run the program again.\n\nClick OK to exit.", progress_bar_window, root)




    progress_bar.after(0, update_progress_label, progress_bar_label, "Writing output...")
    out_dirpath=path_dirname(file_paths[1])
    out_fn=sub("(\.[\w]{1,})$", r"_matched.tif", path_basename(file_paths[1])) # Add _matched just before the file extension.
    out_path=path_join(path_abspath(out_dirpath), out_fn)

    try:
        tba_newgrid_dem.save(out_path)
        progress_bar.after(0, update_progress_bar, progress_bar, 10)
    except Exception as error:
        exceptionlast = format_exc().splitlines()[-1]
        handle_error(f"There was an error saving the output of grid matching:\n\n{exceptionlast}\n\nThe output could be missing or wrong, please correct the error and run the program again.\n\nClick OK to exit.", progress_bar_window, root)




    progress_bar_window.destroy()  # Close the progress window when the task is done
    messagebox.showinfo("Processing finished", "Processing finished successfully. The output file is located here:\n\n" + out_path + "\n\nClick OK to exit.")
    root.quit()



def start_process(file_paths, progress_bar_window, progress_bar, progress_bar_label, root):
    """Start the long-running function in a separate thread"""
    progress_bar_window.deiconify()  # Show the progress window
    progress_bar_window.attributes("-topmost", 1) # Bring the progress window to top

    # Run the long-running function in a separate thread to keep UI responsive
    threading.Thread(target=run_processing, args=(file_paths, progress_bar_window, progress_bar, progress_bar_label, root), daemon=True).start()


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
    root.title("DEM grid matching")

    file_paths = [None, None]  # Store paths of the two selected files

    # Configure grid
    root.grid_rowconfigure(0, weight=1)
    root.grid_rowconfigure(1, weight=0)  # For the process button
    root.grid_columnconfigure(0, weight=0)  # For labels
    root.grid_columnconfigure(1, weight=1)  # For entry fields
    root.grid_columnconfigure(2, weight=0)  # For buttons

    # Title and text above file selectors
    title_label = tk.Label(root, text="Matching of DEM grid to a reference, using xdem", font=("Helvetica", 16))
    title_label.grid(row=0, column=0, columnspan=3, pady=5)

    info_label = tk.Label(root, text="Please select the DEM to use as reference grid and the DEM that will be processed to that grid, then click on \"Start processing\".", anchor="w")
    info_label.grid(row=1, column=0, columnspan=3, padx=10, pady=5, sticky="w")

    # File selectors
    file_selector_labels = ["Reference grid DEM", "DEM to be processed"]
    entries = []
    for idx, label in enumerate(file_selector_labels):
        lbl = tk.Label(root, text=label, anchor="w")
        lbl.grid(row=idx+2, column=0, padx=10, pady=5, sticky="w")

        entry = tk.Entry(root, width=100)
        entry.grid(row=idx+2, column=1, padx=5, pady=5, sticky="ew")
        entries.append(entry)

        # Bind the entry change to the callback function
        entry.bind("<KeyRelease>", lambda e, idx=idx: on_entry_change(entries[idx], file_paths, process_button, idx))

        btn = tk.Button(root, text="Browse", command=lambda idx=idx: file_selector(entries[idx], file_paths, process_button, idx))
        btn.grid(row=idx+2, column=2, padx=5, pady=5)

    # Button to trigger the process
    process_button = tk.Button(root, text="Start processing", state=tk.DISABLED,
                                command=lambda: start_process(file_paths, progress_bar_window, progress_bar, progress_bar_label, root))
    process_button.grid(row=4, column=0, columnspan=3, pady=10)

    # Progress dialog window (hidden initially)
    progress_bar_window = tk.Toplevel(root)
    progress_bar_window.withdraw()  # Initially hide the progress window
    progress_bar_window.title("Processing progress")

    progress_bar_label = tk.Label(progress_bar_window, text="Processing...")
    progress_bar_label.pack(pady=10)

    progress_bar = ttk.Progressbar(progress_bar_window, orient="horizontal", length=300, mode="determinate")
    progress_bar.pack(pady=20)

    # Start the Tkinter main loop
    root.mainloop()


if __name__ == "__main__":
    create_main_window()
