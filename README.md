# Pro Scan

Professional film scanning for the Reflecta CrystalScan 7200, modelled on the
Fujifilm Frontier workflow. Terms: [GLOSSARY.md](GLOSSARY.md). Decisions:
[docs/adr/](docs/adr/). UI design: [docs/design/](docs/design/) (open
`Pro Scan Mockups.dc.html`).

Needs the Arch packages `sane`, `python-numpy`, `python-opencv`, `python-tifffile`
and `pyside6`. The patched scanner driver ships in `proscan/driver/`.

## Status

Start: **Pro Scan** in the app menu, or `proscan` in a terminal (`~/.local/bin/proscan`).

Works: the window (roll start and settings, preview with Enter/Esc, raw scan with
infrared and multi-exposure, frame strip, 12-up grid, number-pad correction keys,
crop and straighten, undo per frame, rescan, scanner failure, German/English),
dust detection, roll folders in `~/Bilder/Pro Scan/`, and raw export (DNG).

Not yet: the real development (the screen uses a simple first inversion; the
Frontier look and Filmgetreu come next), TIFF/JPEG export, choosing a frame's
film base, the monitor's colour profile, and mouse dragging in crop mode.

Command-line scanning still works (`proscan neu …`, `proscan scan …`).

Tests (never touch the scanner):

    python -m unittest discover tests
