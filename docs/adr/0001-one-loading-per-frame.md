# One loading per frame, develop from the raw scan

Unlike a Frontier, which prescans a whole roll and then fine-scans it, the CrystalScan 7200 takes one frame at a time and every frame is loaded by hand. Each frame is therefore loaded exactly once: a 600 dpi preview shows whether it sits correctly, the operator confirms, and a single 3600 dpi raw scan (with infrared and multi-exposure) is taken. All correction and every export are computed from that raw scan, so a roll can be corrected at any time, and re-developed years later, without the scanner.

## Considered Options

- **Frontier-style prescan/fine-scan split**: rejected, since it would mean loading every frame twice.
- **Correcting on the preview before the raw scan**: rejected, since it would tie correction to the moment the frame is in the scanner.
