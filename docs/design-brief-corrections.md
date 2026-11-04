# Design corrections: Pro Scan mockups, round 2

Thank you, the mockups are close. Keep the style, the layout and everything not listed here. Please change the points below and send all boards again. [GLOSSARY.md](../GLOSSARY.md) is attached again; it decides every label.

## Accepted as designed

- The number-pad layout: C/M/Y + on 7/8/9 and − on 4/5/6, D on + / −, gradation on 1 / 3, sharpness on ÷ / ×, 0 resets the frame to auto, Enter scans, comma toggles the grid.
- D, C, M and Y in steps from −12 to +12, gradation from −3 to +3, shown relative to auto.
- Crop and straighten as a mode on the main screen (key A).
- The amber dashed border on the preview (it is only a position check).

## Must change

1. **Resolution.** The raw scan is always **3600 dpi**, never 7200. A full 35 mm frame at 3600 dpi is about 5100 × 3400 px. Fix the image info line on every board (it currently says "7200 dpi · 5184 × 3456").
2. **Roll folder.** Rolls live in `~/Bilder/Pro Scan/<roll name>/`, and exports go to `~/Bilder/Pro Scan/<roll name>/Export/` by default. Fix the export folder field and any other path shown.
3. **Sharpness** is not relative to auto. It runs from **0 to 5**, with **2 as the default** for every new frame. Show it as an absolute value (`S 2`), not a signed one. Update the correction panel, the grid tiles, the rescan card and the legend sheet.
4. **Film stock** is a **free text field**, not a dropdown. Remove the ▼.
5. **The number of frames is not fixed.** A roll has as many frames as were scanned: 24, 36, 37 or any other number. The strip ends at the last scanned frame, with one empty slot for the next frame to load. Show "14 frames" instead of "14 / 36", and drop any "of 36".

## Missing

6. **Choosing which frame's film base to use.** When a frame shows **FB** (film base borrowed), the user can pick which frame's film base it uses instead. Add this to the correction panel for a frame with FB:
   - which frame it currently borrows from ("Filmgrund von Bild 8")
   - a way to choose another frame, by keyboard and by mouse
   - a way to go back to the automatic choice

   It is rare, so keep it small.
7. **Black-and-white rolls have no infrared cleaning.** When the film type is Schwarzweißnegativ, the DNG option "staubbereinigt" is disabled and set to "unberührt", with a short note explaining why (silver film blocks infrared). Show this on the roll start form, or as a small extra board.
8. **Changing the film type after frames are scanned.** In roll settings, changing the film type re-develops every frame. Show a confirmation that says so and how many frames are affected. Corrections are kept.

## Labels (use the glossary terms)

| Replace | With (DE) | With (EN) |
|---|---|---|
| Look | Bildstil | Look |
| Filmbasis geliehen | Filmgrund geliehen | Film base borrowed |
| Film-faithful | Filmgetreu | Faithful look |
| DNG-Rohdaten / DNG raw | Raw-Export (DNG) | Raw export (DNG) |

The two looks stay **Frontier-Look** and **Filmgetreu** (EN: Frontier look, Faithful look).

## Unchanged reminders

- Fonts: keep IBM Plex Sans / Mono. They will ship with the app, so no other font changes.
- The internal raw scan is not a DNG. In the rescan card, write the replaced raw scan as `Ersetzt/Bild 17 (03.11.2026)` instead of `017_roh_2026-11-03.dng`.
