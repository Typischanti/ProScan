"""Exporting a roll's frames in the formats chosen for that roll."""
from . import capture, dng


def file_stem(roll, number):
    return f'{roll.details["name"]}_{number:02d}'


def export_frame(roll, number):
    """Write the frame's exports; returns the written paths."""
    # shortcut: only the raw export exists yet; developed TIFF/JPEG come with the development pipeline
    export = roll.settings['export']
    folder = roll.export_folder
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    if export['dng']:
        path = folder / (file_stem(roll, number) + '.dng')
        raw = capture.load_raw(roll.frame_dir(number), export['dng_dust_cleaned'])
        dng.write(path, raw, roll.details, number)
        written.append(path)
    return written
