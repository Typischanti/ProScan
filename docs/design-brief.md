# Design brief: Pro Scan

## What it is

Pro Scan is a desktop app for scanning 35 mm film on a **Reflecta CrystalScan 7200**, a film scanner that takes one frame at a time. It should feel like the operator software of a professional lab scanner (Fujifilm Frontier): fast, keyboard-driven and calm, with the image at the centre of everything. It replaces an older home-made app whose UI grew too many controls.

- **One user**: the owner, scanning their own rolls at home, often 36 frames in a sitting.
- **Platform**: Arch Linux, KDE Plasma on Wayland, one desktop monitor. It will be built with **Qt 6 (PySide6) widgets**, so design for what Qt widgets can render: no web-only effects.
- **Language**: the UI can be switched between **German (default)** and **English**. German labels are longer, so leave room.

The exact terms are in [GLOSSARY.md](../GLOSSARY.md). Use them in the UI as written there (German label / English label).

## What the user does

1. **Start a roll** (Filmrolle): enter the roll details (Rollenangaben).
   - Required: name, film type (Farbnegativ / Schwarzweißnegativ / Farbpositiv).
   - Optional: film stock, ISO with push/pull, camera, lens, date, who developed it, notes.
   - Also set per roll: the look (Frontier-Look by default, or Filmgetreu), multi-exposure (on by default), and the export settings.
   - Export settings: any mix of TIFF 16-bit (sRGB / Adobe RGB / ProPhoto), JPEG (sRGB) and DNG raw. Dust-cleaned DNG is on by default, with an "untouched" option. The export folder defaults to `<roll>/Export/`.
   - These settings default to the previous roll's.
2. **For every frame, repeat:**
   1. Load the frame by hand (Einlegen).
   2. A low-resolution **preview** (Vorschau) appears. Its only purpose is to check the film sits correctly.
   3. **Enter** starts the raw scan. **Esc** means reload or skip.
   4. The **raw scan** (Rohscan) takes a while, with multi-exposure and infrared. The user waits for it, then loads the next frame.
   5. The frame appears in the roll strip, already auto-corrected.
3. **Correct** (Korrektur): possible at any time, during scanning or after the last frame.
   - Per frame: Density (D), colour keys C / M / Y, Gradation (soft ↔ hard), Sharpness, all in **fixed key steps** shown as signed numbers (e.g. `D +2  C −1  M 0  Y +1`), Frontier-style.
   - Crop (Ausschnitt) and straightening by hand. 3:2 is locked by default, free crop is optional. A new frame starts with the previous frame's crop.
   - Black-and-white negatives have no colour keys: show them disabled, not hidden.
4. **Export** happens automatically, about 2 s after the user stops adjusting a frame or moves on. There is no save or export button in the normal flow.

Everything saves itself immediately. Undo/redo works per frame (Ctrl+Z / Ctrl+Shift+Z).

## Screens and states to design

1. **Roll start**: roll details form plus the per-roll settings above. Also the entry point for reopening an existing roll.
2. **Main screen** (the most important one):
   - **Top**: scanner status and the current step ("Bild einlegen", "Vorschau läuft", "Enter = Scannen, Esc = neu einlegen", "Rohscan 2/2 … 64 %").
   - **Centre**: the current frame, large.
   - **Right**: the correction panel with D, C/M/Y, gradation and sharpness in key steps, plus crop/straighten.
   - **Bottom**: the roll strip of all frames, numbered 1, 2, 3 in scanning order.
3. **Preview check**: the main screen while a preview waits for Enter/Esc. It must be impossible to mistake for a finished frame.
4. **12-up grid**: toggled by a key, to compare frames side by side. Correcting in the grid is a nice-to-have.
5. **Crop/straighten mode** on the current frame.
6. **Roll settings**: the same settings as roll start, editable later.
7. **Scanner failure**: a hung scan shows "reset and rescan this frame". It must make clear that no other frame is affected.
8. **Rescanning a frame later**: e.g. frame 17 has a hair. The frame's correction and crop are kept, and the old raw scan moves to `Ersetzt/`.
9. **First run / empty state**: no roll open, scanner connected or not.

Frame states the roll strip and grid need to show:
- empty slot / preview waiting / scanning (with progress) / scanned and auto-corrected
- corrected by the operator (shows that it differs from the auto correction)
- **film base borrowed**: no clear film was visible, so the film base comes from another frame; needs a small badge
- export pending / exported / export failed
- scan failed

## Keyboard

The operator should be able to do a whole roll without the mouse:
- **Arrow keys** move between frames.
- **Number pad** keys correct the current frame.
- **Enter/Esc** confirm or reject the preview.
- A key toggles the 12-up grid.

Please propose a number-pad mapping for D, C/M/Y, gradation and sharpness, plus "reset frame to auto", in the spirit of a Frontier keyboard. Show the mapping somewhere discoverable, e.g. a key legend.

## Visual direction

- **Neutral grey UI around the image.** The user judges colour by eye, so nothing coloured or saturated may sit next to the image. A dark neutral grey works well. Accent colour only for status and warnings, and kept small.
- The image view is colour-managed with the monitor profile, so the chrome should not compete with it.
- Calm and dense like professional tools, not a consumer photo app. Big readable key values, small chrome.
- Numbers in the correction panel should be easy to read at a glance from a step back.

## Not in this version

Don't design these: grain reduction, film stock profiles, contact sheets, printing, toning, dust-cleaning strength, a photo library or catalogue, metadata per frame.

## Open for the designer

- The number-pad mapping.
- How many steps each key has and how steps are shown (the number is decided, the visual form isn't).
- Where crop/straighten lives: a mode on the main screen, or the right panel.

## What to deliver

Mockups of screens 1–9 in one consistent style: light chrome is not required, dark is preferred. Show at least one German and one English version of the main screen. Include the key legend and all frame states in the roll strip.
