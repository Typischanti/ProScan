# Pro Scan

Professional film scanning, modelled on the Fujifilm Frontier workflow. Made for
the Reflecta CrystalScan 7200; other Reflecta/PIE scanners (CrystalScan, ProScan,
DigitDia) use the same driver. Nikon Coolscan, Plustek OpticFilm and Epson
Perfection scanners with a film unit work through the system's SANE backends,
without infrared dust cleaning or multi-exposure; Epson flatbeds scan their whole
film area at 1600 dpi. These have not been tried on the real devices yet. Terms: [GLOSSARY.md](GLOSSARY.md). Decisions:
[docs/adr/](docs/adr/). UI design: [docs/design/](docs/design/) (open
`Pro Scan Mockups.dc.html`).

Needs the Arch packages `sane`, `python-numpy`, `python-opencv`, `python-tifffile`
and `pyside6`. The patched scanner driver ships in `proscan/driver/`.

## Status

Start: **Pro Scan** in the app menu, or `proscan` in a terminal (`~/.local/bin/proscan`).

Works: the window (roll start and settings, preview with Enter/Esc, raw scan with
infrared and multi-exposure and a progress bar, frame strip, 12-up grid, number-pad
correction keys with colour keys per tone range (Num 2: whole frame, highlights, midtones,
shadows), crop and straighten, 90° rotation (T / Shift+T), undo per frame,
rescan, scanner failure, German/English), the development (film base per frame,
borrowed or chosen with B; Frontier look and faithful look for colour negative,
black-and-white negative and colour positive), and exports: TIFF 16 bit with an
embedded profile (sRGB, Adobe RGB, ProPhoto), JPEG (sRGB) and raw DNG, written
2 s after the last change to a frame. Roll folders live in `~/Bilder/Pro Scan/`.

Not yet: film stock profiles, the monitor's colour profile on screen (sRGB is
assumed), mouse dragging in crop mode, and a USB reset for a hung scanner.

Command-line scanning still works (`proscan neu …`, `proscan scan …`).

Tests (never touch the scanner):

    python -m unittest discover tests
