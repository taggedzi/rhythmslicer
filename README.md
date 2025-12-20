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
# Play a file
r-slicer play path/to/file.mp3

# Pause/Resume/Stop
r-slicer pause
r-slicer resume
r-slicer stop

# Set volume (0-100)
r-slicer volume 75

# Check status
r-slicer status

# Module invocation also works
python -m rhythm_slicer.cli play path/to/file.mp3
```

## Platform prerequisites

- VLC installed and available on your system.
- Python package `python-vlc` (installed automatically with this project).

Note: Commands act on the player instance created for the current process.
