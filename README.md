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
   roll starts with the last roll's settings. Previous rolls can be reopened
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
| **Ctrl+S** | Save the frame's scene and keys as your own preset |
| **R** | Rescan the frame (keeps its correction) |
| **Ctrl+C**, **Ctrl+V** | Copy a frame's correction, paste it onto another frame |
| **Ctrl+Shift+V** | Paste it onto every frame of the roll |
| **Ctrl+Z**, **Ctrl+Shift+Z** | Undo / redo, per frame |
| **Ctrl+E** | Export the frame again |
| **Ctrl+,** | Roll settings |
| **Ctrl+N**, **Ctrl+O** | New roll, open roll |
| **F1** | All keys |

Keys while cropping (after **A**):

| Key | Does |
|---|---|
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
  (Filmgetreu) is gentler and closer to the film itself.
- **Multi-exposure** (on by default): a second, longer pass for more shadow
  detail. Takes longer. Only on Reflecta/PIE scanners.
- **Exports:**
  - TIFF 16 bit in sRGB, Adobe RGB (default) or ProPhoto;
  - JPEG (sRGB);
  - raw DNG, dust-cleaned or as scanned.
- **Export folder:** by default the roll's `Export` folder.

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
- **Raw scans are large:** about 260 MB per frame at 3600 dpi, so a 36-exposure roll needs around 10 GB.

## Not done yet

Film stock profiles, using the monitor's colour profile on screen (sRGB is
assumed), dragging the crop with the mouse, and resetting a hung scanner over USB.

## For developers

- Terms used in the code and UI: [GLOSSARY.md](GLOSSARY.md).
- Design decisions: [docs/adr/](docs/adr/).
- UI mockups: [docs/design/](docs/design/) (open `Pro Scan Mockups.dc.html`).
- The patched Reflecta driver and its patches: `proscan/driver/`.
- Scanning from the command line: `python3 -m proscan neu …`, `python3 -m proscan scan …`.

Tests (they never touch the scanner):

```bash
python3 -m unittest discover tests
```
