# RhythmSlicer Pro

RhythmSlicer Pro is a minimal, cross-platform CLI MP3 player that uses VLC via
`python-vlc`.

## Quickstart

1) Install VLC (see prerequisites below).
2) Install the package:

```bash
pip install -e .
```

3) Play an MP3 (or any file VLC supports):

```bash
r-slicer play path/to/file.mp3
```

## How to run

```bash
# Play a file (waits until playback ends or Ctrl+C)
r-slicer play path/to/file.mp3

# Pause/Resume/Stop
r-slicer pause
r-slicer resume
r-slicer stop

# Set volume (0-100)
r-slicer volume 75

# Check status
r-slicer status

# Exit immediately after starting playback
r-slicer play --no-wait path/to/file.mp3

# Module invocation also works
python -m rhythm_slicer.cli play path/to/file.mp3
```

## Platform prerequisites

- VLC installed and available on your system.
- Python package `python-vlc` (installed automatically with this project).

Note: Commands act on the player instance created for the current process.

## Troubleshooting (Windows)

If you see `VLC backend is unavailable`, `python-vlc` likely cannot load
`libvlc.dll`. Ensure VLC and Python bitness match and set the VLC paths:

```powershell
$env:VLC_DIR = "C:\Program Files\VideoLAN\VLC"
$env:PATH = "$env:VLC_DIR;$env:PATH"
$env:PYTHON_VLC_MODULE_PATH = $env:VLC_DIR
$env:PYTHON_VLC_LIB_PATH = "$env:VLC_DIR\libvlc.dll"
python -c "import vlc; print(vlc.libvlc_get_version())"
```

If that prints a version (e.g., `3.0.21 Vetinari`), the backend is available.
If it fails, verify `libvlc.dll` exists at the path and that VLC is installed
as 64-bit when using 64-bit Python.
