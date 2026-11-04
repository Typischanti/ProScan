# Installing Pro Scan

Pro Scan talks to the scanner through SANE (`scanimage`), so it runs where SANE
runs: **Linux** fully, **macOS** partly, **Windows** only through WSL 2.

| | Linux (x86-64) | Linux (ARM) | macOS | Windows |
|---|---|---|---|---|
| Reflecta/PIE with infrared + multi-exposure | yes | after building the driver | after building the driver | through WSL 2 |
| Nikon Coolscan, Plustek OpticFilm, Epson Perfection | yes | yes | yes | through WSL 2 |
| Tested | Arch Linux | no | no | no |

Pro Scan needs **Python 3.12 or newer**.

The repository is private, so get it with the GitHub CLI (`gh auth login` once)
or with `git clone https://github.com/Typischanti/ProScan.git` and your GitHub
credentials.

## Linux

### 1. Install SANE and Python

Arch Linux (everything from the distribution):

```bash
sudo pacman -S sane python python-numpy python-opencv python-tifffile pyside6
```

Debian and Ubuntu:

```bash
sudo apt install sane-utils python3 python3-venv git
```

Fedora:

```bash
sudo dnf install sane-backends python3 git
```

### 2. Get Pro Scan

```bash
git clone https://github.com/Typischanti/ProScan.git ~/ProScan
```

On Arch you're done with the packages. On other distributions, install the
Python packages in a virtual environment inside the project:

```bash
cd ~/ProScan && python3 -m venv .venv && .venv/bin/pip install numpy opencv-python-headless tifffile PySide6
```

### 3. Allow access to the scanner

Arch, Debian, Ubuntu and Fedora give the logged-in user access to known
scanners. Check that SANE sees yours (switch the scanner on first):

```bash
scanimage -L
```

If it's not listed but `lsusb` shows it, add a udev rule for it. Replace the
IDs with the two hex numbers `lsusb` prints for the scanner (`05e3:0145` is the
CrystalScan 7200):

```bash
echo 'ATTRS{idVendor}=="05e3", ATTRS{idProduct}=="0145", ENV{libsane_matched}="yes", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/65-proscan.rules
```

```bash
sudo udevadm control --reload && sudo udevadm trigger
```

Then unplug the scanner and plug it in again.

A Reflecta/PIE scanner doesn't need to show up in `scanimage -L`: Pro Scan
brings its own driver for it (`proscan/driver/`, built for x86-64 against
sane-backends 1.4.0). It only needs the USB access above.

### 4. Start it

From the project folder (with `.venv/bin/python` in place of `python3` if you
made a virtual environment):

```bash
python3 -m proscan
```

To get **Pro Scan** in the app menu, create a launcher and a menu entry. Change
the path if the project is not in `~/ProScan`, and use `.venv/bin/python` if you
made a virtual environment:

```bash
mkdir -p ~/.local/bin && printf '#!/bin/sh\ncd "$HOME/ProScan" && exec python3 -m proscan "$@"\n' > ~/.local/bin/proscan && chmod +x ~/.local/bin/proscan
```

```bash
printf '[Desktop Entry]\nType=Application\nName=Pro Scan\nComment=Scan and develop film\nExec=%s/.local/bin/proscan\nIcon=scanner\nTerminal=false\nCategories=Graphics;Photography;Scanning;\nStartupWMClass=proscan\n' "$HOME" > ~/.local/share/applications/proscan.desktop
```

### Linux on ARM (Raspberry Pi and similar)

The bundled driver is an x86-64 file. Coolscan, OpticFilm and Epson scanners
work through the system's SANE as they are. For a Reflecta/PIE scanner, build
the driver yourself: get the sane-backends 1.4.0 source, apply the two patches
in `proscan/driver/` (`patch -p1 < …`), build it, and copy
`backend/.libs/libsane-pieusb.so.1` over the one in `proscan/driver/`.

## macOS

Untested. With [Homebrew](https://brew.sh):

```bash
brew install sane-backends python git
```

```bash
git clone https://github.com/Typischanti/ProScan.git ~/ProScan
```

```bash
cd ~/ProScan && python3 -m venv .venv && .venv/bin/pip install numpy opencv-python-headless tifffile PySide6
```

```bash
cd ~/ProScan && .venv/bin/python -m proscan
```

Coolscan, OpticFilm and Epson scanners work through Homebrew's SANE. The
bundled Reflecta/PIE driver is a Linux file and doesn't load on macOS.
Homebrew's own pieusb driver may still find the scanner, but without Pro Scan's
patches: no capture progress, and multi-exposure may fall back to a single
pass. Loading a self-built patched driver on macOS is not set up yet.

## Windows

There is no SANE for Windows, so Pro Scan can't talk to the scanner directly.
It can run inside **WSL 2** (Windows 11, untested):

1. Install WSL with Ubuntu: `wsl --install -d Ubuntu` in PowerShell, then restart.
2. Install [usbipd-win](https://github.com/dorssel/usbipd-win) to pass the
   scanner's USB connection into WSL. In PowerShell as administrator,
   `usbipd list` shows the scanner's bus ID. Then run `usbipd bind --busid <id>`
   once, and `usbipd attach --wsl --busid <id>` each time the scanner is plugged in.
3. In the Ubuntu window, follow the Linux steps for Debian and Ubuntu.
   Windows 11 shows Linux windows directly, so `python3 -m proscan` opens
   the normal Pro Scan window.

Rolls are saved in the Linux home folder (`~/Bilder/Pro Scan/`). From Windows,
open it in Explorer under `\\wsl$\Ubuntu\home\<name>\Bilder\Pro Scan`.

## Checking the installation

The tests never touch the scanner:

```bash
python3 -m unittest discover tests
```
