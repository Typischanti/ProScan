# Pro Scan

Professional film scanning for one Reflecta CrystalScan 7200, modelled on the workflow of lab scanners such as the Fujifilm Frontier. Terms are given in English with the German UI label in parentheses.

## Film

**Roll** (Filmrolle):
One developed film, scanned and delivered as a unit; all of its frames share one film type.
_Avoid_: Order, job, batch, film

**Frame** (Bild):
One exposed image on a roll, identified by its position on that roll.
_Avoid_: Image, picture, shot, slide

**Film type** (Filmtyp):
The kind of emulsion on a roll: colour negative, black-and-white negative, or colour positive.
_Avoid_: Film mode, scan mode

**Colour negative** (Farbnegativ):
Film type whose frames are inverted and colour-masked; has an orange base.
_Avoid_: C-41 (a process, not a film type)

**Black-and-white negative** (Schwarzweißnegativ):
Film type whose frames are inverted and carry no colour information.
_Avoid_: Monochrome, B/W

**Colour positive** (Farbpositiv):
Film type whose frames are already positive images; also called slide or reversal film.
_Avoid_: Dia, slide, E-6 (a process, not a film type)

**Film base** (Filmgrund):
The colour and density of unexposed film next to a frame; the reference for inverting a negative. Each frame has its own.
_Avoid_: Orange mask, base colour, Dmin

## Scanning

**Loading** (Einlegen):
Placing one frame into the scanner by hand; every frame of a roll is loaded separately.
_Avoid_: Feeding, advancing

**Preview** (Vorschau):
A quick low-resolution scan of the loaded frame, used only to check that it is loaded correctly before its raw scan.
_Avoid_: Prescan, Vorscan, thumbnail

**Raw scan** (Rohscan):
The unprocessed, full-resolution scanner data of one frame; every correction and export is computed from it.
_Avoid_: Fine scan, main scan, Hauptscan, original

**Multi-exposure** (Mehrfachbelichtung):
Scanning the same frame at more than one exposure and merging the passes into one raw scan with more shadow detail.
_Avoid_: HDR, bracketing

**Roll details** (Rollenangaben):
What the operator records about a roll: name and film type, optionally film stock, ISO and push/pull, camera, lens, date, who developed it, and notes.
_Avoid_: Metadata, roll info, tags

## Correction

**Crop** (Ausschnitt):
The part of a raw scan that a frame's exports show, set by hand; a new frame starts with the previous frame's crop.
_Avoid_: Framing, auto crop, Rahmen

**Sharpness** (Schärfe):
A correction key in fixed steps that sets how much a frame is sharpened in its developed exports.
_Avoid_: Unsharp mask, detail

**Auto correction** (Automatik):
The density and colour balance the software chooses for a frame by itself.
_Avoid_: Auto levels, auto exposure

**Correction** (Korrektur):
The operator's adjustment of one frame, expressed in fixed key steps relative to its auto correction.
_Avoid_: Edit, adjustment, settings

**Density** (Dichte, D):
How light or dark a developed frame is as a whole; one of the correction keys.
_Avoid_: Exposure

**Brightness** (Helligkeit, H):
How light the midtones of a developed frame are, with black and white left where they are; one of the correction keys.
_Avoid_: Gamma, Density

**Colour keys** (Farbtasten C / M / Y):
Correction keys that shift a frame towards or away from cyan, magenta or yellow.
_Avoid_: Colour sliders, RGB balance, white balance

**Tone range** (Bereich: Gesamt / Lichter / Mitten / Schatten):
The part of a frame's tones the colour keys act on: the whole frame, or mainly its highlights, midtones or shadows.
_Avoid_: Zone, colour wheels, split toning

**Saturation** (Sättigung, F):
How strong a developed frame's colours are, changed as on film: more colour means more dye, so colours also get deeper and darker; greys stay. One of the correction keys.
_Avoid_: Chroma, colourfulness

**Vibrance** (Dynamik, V):
Saturation that changes muted colours most and strong ones least. One of the correction keys.
_Avoid_: Vividness, smart saturation

**Loupe** (Lupe):
The frame shown at full resolution, 1:1, while Z is held.
_Avoid_: Zoom, magnifier

**Auto lock** (Automatik übernehmen):
A frame taking another frame's automatic correction instead of its own, so a sequence prints alike.
_Avoid_: Density lock, sync

**Film data** (Filmdaten):
A look that develops colour negatives from the film maker's published curves and spectra: scan to dye, dye to the light in the camera, then a print on virtual paper.
_Avoid_: Spectral look, emulation

**Film profile** (Filmprofil):
What a film stock always does differently from other stocks, known in advance: its colour layers' contrast. Film base and cast are not part of it; they are measured on every roll.
_Avoid_: Film preset, LUT

**Scene** (Szene):
The kind of picture a frame shows (portrait, landscape, night …), which shapes its auto correction; one per frame, Standard by default.
_Avoid_: Mode, filter

**Preset** (Voreinstellung):
A named scene, set of correction key values, or both, applied to a frame in one step. Built-in or the user's own.
_Avoid_: Profile, template, style

**Gradation** (Gradation):
The contrast character of a developed frame, chosen from fixed soft-to-hard steps.
_Avoid_: Contrast curve, tone curve

**Look** (Bildstil):
The overall rendering the auto correction aims for: either the Frontier look or the faithful look.
_Avoid_: Preset, filter, style, profile

**Frontier look** (Frontier-Look):
A look that is punchy, warm and kind to skin tones, in the manner of a lab scanner.
_Avoid_: Lab look, pleasing look

**Faithful look** (Filmgetreu):
A look that renders the film as it is, correcting only the scanner's own colour cast.
_Avoid_: Real look, neutral, natural, accurate

## Export

**Export** (Export):
Writing a roll's frames to files in the formats chosen for that roll.
_Avoid_: Save, output, delivery

**Raw export** (Raw-Export):
A frame's raw scan written as a linear DNG for developing in another program.
_Avoid_: RAW, raw TIFF
