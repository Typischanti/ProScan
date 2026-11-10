# Pro Scan

Film scanning that works like a lab: a Fujifilm Frontier-style workflow for
negatives and slides. You load one frame, check its position in a quick
preview, and Pro Scan scans it at full resolution. It then develops the frame
into a finished picture and exports it. Corrections are made with the number
pad, frame by frame, the way lab operators do it.

The interface is in German or English (switch it in the top bar).

## Scanners

| Scanner | Infrared dust cleaning | Multi-exposure | Raw scan |
|---|---|---|---|
| Reflecta CrystalScan 7200 | yes | yes | 3600 dpi |
| Other Reflecta/PIE scanners (CrystalScan, ProScan, DigitDia) | yes | yes | 3600 dpi |
| Nikon Coolscan | – | – | 3600 dpi |
| Plustek OpticFilm | – | – | 3600 dpi |
| Epson Perfection with a film unit | – | – | 1600 dpi, whole film area |

Only the CrystalScan 7200 has been tested. The others are set up from the
options their SANE driver reports and have not been tried on real devices.

Supported film: colour negative, black-and-white negative and colour slides
(colour positive).

## Installation

See [INSTALL.md](INSTALL.md) for Linux, macOS and Windows (through WSL 2). In
short: Python 3.12 or newer, SANE, and the Python packages numpy, OpenCV,
tifffile and PySide6. Start it with `python3 -m proscan` from the project
folder, or from the app menu once you've added the menu entry.

## Scanning a roll

1. **Start a roll.** Give it a name and a film type; everything else is
   optional: film stock, ISO, push/pull, camera, lens, date, lab, notes. A new
   roll starts with the last roll's settings. Picking the film stock from its list sets
   the film type and ISO, and the stock's film profile follows from its name; any other
   stock can be typed. Previous rolls can be reopened
   from the same screen.
2. **Load a frame** into the scanner and press **Enter**. Pro Scan makes a quick
   600 dpi preview, only so you can check that the frame sits right.
3. **Enter** scans it, **Esc** lets you load it again. A progress bar shows the
   scan. With multi-exposure on, a frame is scanned twice.
4. The frame appears developed and is **exported automatically**. Load the
   next one and repeat.

You can correct any frame at any time, during the roll or later. Rolls also
open without a scanner connected.

## Correcting a frame

Every frame starts with an automatic correction. The number pad changes it
(the number keys on the main keyboard work too):

| Key | Does |
|---|---|
| Num **+** / **−** | Density: darker / lighter |
| **H** / **Shift+H** | Brightness: midtones lighter / darker (black and white stay) |
| **F** / **Shift+F** | Saturation more / less, subtractive like film: stronger colours get deeper and darker |
| **V** / **Shift+V** | Vibrance: like saturation, but muted colours change most and strong ones (skin, orange) least |
| Num **7** / **4** | More / less cyan |
| Num **8** / **5** | More / less magenta |
| Num **9** / **6** | More / less yellow |
| Num **2** | Colour keys act on: whole frame → highlights → midtones → shadows |
| Num **3** / **1** | Gradation: harder / softer |
| Num **×** / **÷** | Sharpness 0–5 (default 2) |
| **0** | Back to the automatic correction (the scene stays) |

As at a lab: if a print looks too blue, add yellow (Num 9). If it's too dark,
press Num −. Colour keys don't exist for black-and-white film.

Other keys:

| Key | Does |
|---|---|
| **← →** | Previous / next frame |
| **G** | 12-up grid of the roll |
| **A** | Crop and straighten (see below) |
| **T** / **Shift+T** | Turn 90° clockwise / counter-clockwise |
| **B** | Choose which frame's film base to use |
| **P** | Presets (see below) |
| Hold **Space** | Before: the frame with only the automatic correction; let go to see yours |
| Hold **Z** | Loupe: the frame at full resolution, 1:1, around the mouse (as exported; ready after a few seconds) |
| **Ctrl+U**, **U** | Copy a frame's automatic correction, apply it to another frame (for a sequence of one scene: they then print alike) |
| **Shift+U** | The frame's own automatic correction again |
| **N**, then a click | Grey point: the clicked grey or white surface prints neutral, the colours of the whole frame follow. A frame can have several (N again); while picking, rings show them, and a click on a ring removes it. **Shift+N** removes all |
| **L** | Colours from another frame: **← →** choose, **Enter** apply, **Del** own colours, **Esc** cancel. Only the colour balance is taken; the brightness stays the frame's own |
| **W** | Clipping warning on/off: pure white shows red, pure black blue, with their share under the picture |
| **Ctrl+S** | Save the frame's scene and keys as your own preset |
| **R** | Rescan the frame (keeps its correction) |
| **Ctrl+C**, **Ctrl+V** | Copy a frame's correction, paste it onto another frame |
| **Ctrl+Shift+V** | Paste it onto every frame of the roll |
| **Ctrl+Z**, **Ctrl+Shift+Z** | Undo / redo, per frame |
| **Ctrl+E** | Export the frame again |
| **Ctrl+L** | Calibrate the scanner's light with the empty film holder (once; see below) |
| **Ctrl+K** | Contact sheet on paper: the whole roll on one JPEG in the export folder (`<roll>_Kontaktbogen.jpg`) |
| **Ctrl+Shift+K** | Contact sheet as black film strips with sprocket holes (`<roll>_Kontaktbogen_Film.jpg`) |
| **Ctrl+,** | Roll settings |
| **Ctrl+N**, **Ctrl+O** | New roll, open roll |
| **F1** | All keys |

Keys while cropping (after **A**):

| Key | Does |
|---|---|
| Mouse | Drag inside the crop to move it, a corner to resize it (an edge too when free) |
| Arrows | Move the crop |
| Shift+arrows | Make it larger or smaller |
| **F** | Switch between fixed 3:2 and free proportions |
| **[** / **]** | Straighten in 0.1° steps (up to ±5°) |
| **Delete** | Back to the full frame |
| **Enter** / **Esc** | Keep / discard the change |

A new frame starts with the previous frame's crop.

Everything is saved as you go; there is no save button.

## Presets

**P** opens a list in the panel, each entry with a small picture of the frame
as it would look. **↑ ↓** choose, **Enter** applies, **Esc** closes.

- **Scenes** shape the automatic correction for a kind of picture: Standard,
  Portrait, Landscape, Backlit, Snow & beach, Night, Indoor light. Your key
  values stay on top of the scene.
- **Corrections** set the keys to fixed values: Overexposed, Underexposed,
  Fluorescent light, Softer, Harder. The scene stays.
- **Own presets** hold a scene and key values together. Save one from the
  current frame with **Ctrl+S**; **Delete** in the list removes it. They are
  kept in `~/.config/proscan/presets.json` and work in every roll.

Presets apply to one frame. To use one on many frames, apply it once, then copy
with **Ctrl+C** and paste with **Ctrl+V** or **Ctrl+Shift+V**. On
black-and-white film, the colour-only presets (Indoor light, Fluorescent light)
are hidden.

## Roll settings

Set when starting a roll, changed later with **Ctrl+,**. They apply to the whole roll:

- **Look:** *Frontier* (default) is punchy and warm, like a lab print. *Faithful*
  (Filmgetreu) is gentler and closer to the film itself. *Film data* (Filmdaten) develops
  colour negatives from the film maker's published data (see below): bright and clean,
  with a blue sky, fresh green and rich but natural colour.
- **Multi-exposure** (on by default): a second, longer pass for more shadow
  detail. Takes longer. Only on Reflecta/PIE scanners.
- **Exports:**
  - TIFF 16 bit in sRGB, Adobe RGB (default) or ProPhoto;
  - JPEG (sRGB);
  - raw DNG, dust-cleaned or as scanned.
- **Export folder:** by default the roll's `Export` folder.

## The film data look

For colour negatives, the look *Film data* works the way the film and a lab print really do:

1. From the scan it computes how much dye each colour layer of the film holds. Your scanner's
   colour bands for this were fitted on 120 real frames of a CrystalScan 7200.
2. The film stock's characteristic curves give the light that reached each layer in the
   camera. A grey surface comes out grey at every brightness, whatever the film's quirks
   (Portra 800's green, for example).
3. The frame is then printed on virtual Kodak Portra Endura paper, balanced like at a lab:
   the film's cast goes, some of the frame's own colour stays (warm afternoon light stays warm),
   and the paper's black is neutral with slightly warm shadows.

The film stock is taken from the roll's film stock name: Kodak Gold 200, Ultramax 400,
Portra 160/400/800, Ektar 100, Fujicolor C200, Pro 400H and Superia X-TRA 400. Any other
name is developed as Gold 200. Black-and-white film and slides get the faithful look.
The number pad, scenes and presets work as in the other looks. The first frame of a film stock
takes about 2 seconds longer while its tables are built.

Data: film and paper curves and spectra from the [spektrafilm](https://github.com/andreavolpato/agx-emulsion)
project by Andrea Volpato, digitised from the Kodak and Fujifilm data sheets, and the CIE 1931
standard observer ([CIE 018:2019](https://doi.org/10.25039/CIE.DS.xvudnb9b)); both CC BY-SA 4.0.
Pro Scan's compact copy is `proscan/data/films.json`, under the same licence.

## Where your files are

Each roll is a folder in `~/Bilder/Pro Scan/<roll name>/`:

| Path | Holds |
|---|---|
| `Export/` | The finished files: `<roll>_01.tif`, `.jpg`, `.dng`, … |
| `Bilder/01/`, `Bilder/02/`, … | The raw scan of each frame (kept, so you can re-develop at any time) |
| `Ersetzt/` | Old raw scans replaced by a rescan. Delete them yourself when you no longer need them |
| `roll.json` | Roll details, settings and every frame's correction |

The exports are written 2 seconds after your last change to a frame. They're
also written when you switch frames or close the app. The roll details go into
each file's metadata.

## Good to know

- **Film base (FB):** for negatives, Pro Scan measures the clear film at the
  frame's edges to remove the orange mask. If a frame shows no clear film, it
  borrows the film base of the nearest frame that does. The strip then shows an
  **FB** badge; press **B** to pick a different frame.
- **Dust cleaning** uses the infrared channel. It isn't possible with
  black-and-white film, because the silver blocks infrared.
- **If the scanner stops responding**, the frame stays loaded: switch the scanner
  off and on, then retry with Enter.
- **Calibrating the light (Ctrl+L):** a scanner can light the frame unevenly (the
  CrystalScan 7200 is even to 1 % over most of the frame; only the outermost edges,
  where the film base is measured, get less light). Insert the
  film holder **empty** and press Ctrl+L: Pro Scan scans it at a short exposure
  (about a minute) and from then on evens out every scan, on screen and in all
  exports. Once is enough; it applies to all rolls and is kept in
  `~/.config/proscan/licht.npy`. Afterwards, the open roll is measured again and
  re-exported; other rolls are re-measured when opened. Reflecta/PIE scanners only.
- **Film stock:** if the roll's film stock contains "Portra 800" (e.g. "Kodak Portra 800"), its green and
  blue are matched to red in contrast. Without it, Portra 800 prints greys and skin yellow-green.
  "Cinestill 400D" gets its flatter red raised the same way; without it, skies and stone print cold and cyan.
- **Learned film profiles:** grey points (**N**) teach Pro Scan a film stock. From four grey points on a
  roll, on surfaces at least one and a half stops apart (a dark wall and a white shirt, say), it fits the
  stock's profile, uses it for the whole roll and keeps it in `~/.config/proscan/filmprofile.json` for
  later rolls with the same film stock name. More grey points, from dark to white, make it more exact;
  several can sit on one frame. The roll settings (Ctrl+,) show which film profile the roll uses and
  can forget a learned one.
  The Film data look does not use film profiles.
- **Histogram:** the panel shows the developed frame's red, green and blue tones, dark to
  light, above the keys.
- **Photo metadata:** camera, lens, ISO, date taken and the film stock (as a keyword) are
  written into the TIFF and JPEG exports in the standard XMP fields photo programs read
  (Lightroom, digiKam). Dates are taken as precisely as entered: "Oktober 2025", "3.10.2025"
  or just a year.
- **A hung scanner** is reset over USB right away; Enter then tries the scan again.
- **Raw scans are large:** about 260 MB per frame at 3600 dpi, so a 36-exposure roll needs around 10 GB.

## Not done yet

- Built-in film stock profiles beyond Portra 800 and Cinestill 400D: film base and cast differ too much from roll to roll (three
  Gold 200 rolls: up to 40 % in blue), so each roll is measured on its own. Only the colour layers'
  contrast is a property of the film stock; it is known for Portra 800 and Cinestill 400D so far, each fitted on one roll.
- The monitor's colour profile on screen: sRGB is assumed, so on a wide-gamut monitor
  colours look more saturated, as in most image viewers.

## For developers

- Terms used in the code and UI: [GLOSSARY.md](GLOSSARY.md).
- Design decisions: [docs/adr/](docs/adr/).
- UI mockups: [docs/design/](docs/design/) (open `Pro Scan Mockups.dc.html`).
- The patched Reflecta driver and its patches: `proscan/driver/`.
- Scanning from the command line: `python3 -m proscan neu …`, `python3 -m proscan scan …`.
- Finding a roll's dust again with the current detection, from the saved infrared, and re-exporting
  every frame: `python3 -m proscan staub "<roll name>"`.

Tests (they never touch the scanner):

```bash
python3 -m unittest discover tests
```
