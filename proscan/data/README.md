# Film data

`films.json` holds, for each colour negative film stock and for Kodak Portra Endura paper, the dye and base
density spectra and the characteristic curves (paper: also its spectral sensitivity), plus the CIE 1931 2°
colour-matching functions. Resampled to 5 nm and to 0.05 log exposure steps.

- Film and paper data: spektrafilm profiles by Andrea Volpato, https://github.com/andreavolpato/agx-emulsion
  (commit 3bb2c2d, `src/spektrafilm/data/profiles`), processed from the manufacturers' data sheets.
  Licensed CC BY-SA 4.0.
- CIE 2018, CIE 1931 colour-matching functions, 2 degree observer (data table), International Commission on
  Illumination (CIE), Vienna, Austria, DOI 10.25039/CIE.DS.xvudnb9b. Licensed CC BY-SA 4.0.

This file, as an adaptation of both, is licensed CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/).
