# Design brief: Pro Scan contact sheet

## What it is

Pro Scan can now save a **contact sheet** (Kontaktbogen) of a roll: one JPEG with every frame of the roll, for an overview, for choosing which frames to print, and for sharing. The user presses **Ctrl+K**, and Pro Scan writes `<roll name>_Kontaktbogen.jpg` into the roll's export folder.

The attached `kontaktbogen-heute.jpg` is today's version, made from a real roll (Kodak Gold 200, 35 frames). It works, but it is a plain grid. Please design what it should look like.

The roll's 35 frames are attached as `01.jpg` … `35.jpg` (900 px on the long side, already developed, cropped and turned as in the app). Use them in the boards.

The app's own design (dark, calm, Frontier-style) is in the earlier mockups; terms are in [GLOSSARY.md](../GLOSSARY.md).

## What the sheet must show

- **Every frame of the roll**, as developed in Pro Scan: corrections, crop and quarter turns applied. Frames are 3:2, mostly **upright (portrait)**, some **lying (landscape)**. Their orientation is mixed within a roll.
- **The frame number** of each frame (1, 2, 3 …), the same numbers the app uses.
- **The roll details** (Rollenangaben). Only the name is always there; everything else is optional and often empty:
  - name (e.g. "Gold 200")
  - film type: Farbnegativ, Schwarzweißnegativ or Farbpositiv
  - film stock (free text, e.g. "Kodak Gold 200"), ISO and push/pull (e.g. "ISO 400 · +1")
  - camera, lens
  - date (free text, e.g. "Oktober 2025"), developed by
- **Any number of frames:** a roll can have 12, 24, 36, 37 or any other count. Design for 36 and show how 37 and 12 look.

Do not put the notes field on the sheet; it is private.

## How it will be built

The sheet is drawn by the app, not in a browser, so keep it to what a simple renderer can draw:

- images placed in rectangles, filled rectangles and lines, and text;
- no shadows, blur, gradients or transparency effects;
- fonts: **Noto Sans** and **Noto Sans Mono** (installed on the system), in any weight;
- output: one sRGB JPEG. Today it is about 2700 px wide; choose the size, but each frame should stay at least about 400 px on its long side so the sheet can be zoomed into.

## Open for the designer

- **Paper or dark:** a classic darkroom contact sheet (frames on black film, with the film edge, sprocket holes and edge numbering), a light print on white paper, or the app's dark look.
- **Strip or grid:** six frames per row like a cut 35 mm strip, or a free grid. Upright frames could stand upright, or lie on their side as on the film.
- Where the roll details go, and how they look when only the name is filled in.
- How frame numbers are shown: under the frame, or on the film edge as on real film.
- Anything else that makes the sheet nicer to look at and easier to choose from.

## Not in this version

Don't design these: marks for chosen frames (stars, colours, crop marks drawn on the sheet), several pages, printing to a printer, a picture on the cover.

## What to deliver

- One board per variant you propose (at most three), each at the real pixel size, filled with the attached frames and the details of the Gold 200 roll: name "Gold 200", film stock "Kodak Gold 200", ISO 200, camera "Fujica ST701", date "Oktober 2025".
- The same design with only the roll name filled in, and with 12 and with 37 frames.
- Measurements for the chosen variant: page size, margins, frame size and gaps, every text with font, weight, size and colour, and all colours as hex, so it can be rebuilt exactly.
