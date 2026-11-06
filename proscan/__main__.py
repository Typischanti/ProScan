"""Start the Pro Scan window, or scan from the command line.

  python -m proscan
  python -m proscan neu "<Rollenname>" --filmtyp colour_negative
  python -m proscan scan "<Rollenname>"
  python -m proscan staub "<Rollenname>"   (Staub aller Bilder neu suchen, dann neu exportieren)
"""
import argparse
import tempfile

import cv2
import numpy as np

from . import capture, export, roll as rolls, scanner


def show_preview(preview, path):
    """Save the preview as an 8-bit PNG for a quick look (OpenCV writes BGR)."""
    image = (np.asarray(preview[..., :3], np.float32) / 257).astype(np.uint8)
    cv2.imwrite(str(path), image[..., ::-1])


def scan(roll):
    device = scanner.find_device()
    if device is None:
        raise SystemExit('Kein Filmscanner gefunden. Scanner einschalten und per USB anschließen.')
    with tempfile.TemporaryDirectory() as work:
        while True:
            number = len(roll.frames) + 1
            if input(f'Bild {number} einlegen, dann Enter (q = Ende): ').strip().lower() == 'q':
                return
            preview_png = f'{work}/vorschau.png'
            show_preview(capture.scan_preview(device, f'{work}/vorschau.pnm'), preview_png)
            if input(f'Vorschau: {preview_png}\nEnter = Rohscan, n = neu einlegen: ').strip().lower() == 'n':
                continue
            reports = []
            roll.add_frame(lambda d: reports.append(capture.scan_raw(
                device, d, infrared=roll.infrared and scanner.features(device)['infrared'],
                multi_exposure=roll.settings['multi_exposure'] and scanner.features(device)['multi_exposure'])))
            report = reports[0]
            merge, dust = report.get('merge', {}), report.get('dust', {})
            print('  Mehrfachbelichtung:', merge.get('reason') or ('Kanäle ' + ''.join(merge.get('used_channels', []))))
            print('  Staub:', dust.get('reason') or f'{dust.get("selected_pixels", 0)} Pixel markiert')
            for path in export.export_frame(roll, number):
                print('  Exportiert:', path)


def redo_dust(roll):
    """Find every frame's dust again from its saved infrared, then export the frame again."""
    for frame in roll.frames:
        n = frame['number']
        if not (roll.frame_dir(n) / 'infrarot.npy').exists():
            print(f'Bild {n}: kein Infrarot')
            continue
        dust = capture.redetect_dust(roll.frame_dir(n))
        print(f'Bild {n}:', dust.get('reason') or f'{dust.get("selected_pixels", 0)} Pixel Staub', flush=True)
        export.export_frame(roll, n)


def main():
    parser = argparse.ArgumentParser(prog='proscan')
    commands = parser.add_subparsers(dest='command')
    new = commands.add_parser('neu', help='Neue Filmrolle anlegen')
    new.add_argument('name')
    new.add_argument('--filmtyp', choices=rolls.FILM_TYPES, required=True)
    new.add_argument('--filmmaterial')
    commands.add_parser('scan', help='Bilder einer Rolle scannen').add_argument('name')
    commands.add_parser('staub', help='Staub aller Bilder einer Rolle neu suchen und neu exportieren').add_argument('name')
    args = parser.parse_args()
    if args.command is None:
        from .gui import main as gui
        raise SystemExit(gui())
    if args.command == 'neu':
        details = {'name': args.name, 'film_type': args.filmtyp}
        if args.filmmaterial:
            details['film_stock'] = args.filmmaterial
        print('Angelegt:', rolls.Roll.create(details).path)
    elif args.command == 'staub':
        redo_dust(rolls.Roll.open(rolls.ROOT / rolls.validate_name(args.name)))
    else:
        try:
            scan(rolls.Roll.open(rolls.ROOT / rolls.validate_name(args.name)))
        except KeyboardInterrupt:
            raise SystemExit('\nAbgebrochen. Fertige Bilder bleiben erhalten.')


if __name__ == '__main__':
    main()
