# PCM Player

A fully-compatible PCM player for raw audio files — and pretty much any audio format you throw at it.

## Origin

The original idea was simple: **play PCM tracks from MSU-1 SNES rom-hacks**, so I could listen to those uncompressed soundtracks outside the emulator. MSU-1 audio comes as headerless (well, near-headerless) 16-bit signed little-endian stereo PCM at 44100 Hz, and most general-purpose players just refuse to open them, or open them at the wrong sample rate.

It quickly grew past that. What started as an MSU-1 listener turned into a full audio player with a modern GUI, a configurable raw-PCM decoder for *any* PCM variant, automatic detection of the usual formats, a playlist, and proper transport controls. So now it does what I originally needed — and a lot more.

## Features

- Modern dark UI (PySide6 / Qt 6)
- Drag-and-drop anywhere on the window — adds files to the playlist
- Click-to-seek waveform display
- Full transport: **Play / Pause / Stop / Previous / Next** + 5-second skip buttons
- Volume control with slider
- Playlist with auto-advance, double-click to jump, add/remove/clear
- Keyboard shortcuts for everything
- Format-parameter panel for raw PCM (live-reload on change)
- Single-file portable executable (one `.exe`, no install)

## Supported formats

**Auto-detected from header:**
WAV · FLAC · OGG/Vorbis · OPUS · AIFF · AU · **MP3** (via libsndfile ≥ 1.1)

**Raw PCM (parameters configurable in the UI):**

| Parameter      | Options                                                              |
| -------------- | -------------------------------------------------------------------- |
| Sample rate    | 8000 · 11025 · 16000 · 22050 · 32000 · 44100 · 48000 · 88200 · 96000 · 192000 Hz |
| Channels       | 1 (mono) to 8                                                        |
| Bit depth      | 8 · 16 · 24 · 32 · 64                                                |
| Encoding       | Signed Int · Unsigned Int · Float                                    |
| Byte order     | Little Endian · Big Endian                                           |
| Header skip    | Any byte offset (skip headers, sync bytes, etc.)                     |

Recognized raw PCM extensions with sensible defaults: `.pcm`, `.raw`, `.bin`, `.dat`, `.s8`, `.s16/le/be`, `.s24/le/be`, `.s32/le/be`, `.u8`, `.f32/le/be`, `.f64`.

## Playing MSU-1 tracks

MSU-1 `.pcm` files use this format:

- **Sample rate:** 44100 Hz
- **Channels:** 2 (stereo)
- **Bit depth:** 16-bit
- **Encoding:** Signed Int
- **Byte order:** Little Endian
- **Header skip:** **8 bytes** (the `"MSU1"` magic + 4-byte loop point)

Drop your `.pcm` file into the player and set the **Header Skip** field to `8` — that's it. The player decodes and plays the audio cleanly without the leading metadata bytes producing a click at the start. Defaults for sample rate / channels / bit depth already match MSU-1, so usually only the header offset needs tweaking.

## Keyboard shortcuts

| Key                    | Action                       |
| ---------------------- | ---------------------------- |
| **Space**              | Play / Pause                 |
| **Esc**                | Stop                         |
| **← →**                | Seek ±5 s                    |
| **Shift + ← →**        | Seek ±30 s                   |
| **Ctrl + ← →**         | Previous / next track        |
| **↑ ↓**                | Volume ±5 %                  |
| **Ctrl + O**           | Open file                    |

## Build the portable Windows `.exe`

**Requirements:** Python 3.10+ on `PATH`. Internet access for the first `pip install` only.

```cmd
cd <project-folder>
build_windows.bat
```

The script creates a local venv, installs `PySide6`, `numpy`, `sounddevice`, `soundfile`, and `pyinstaller`, then builds with `--onefile --windowed --collect-binaries sounddevice --collect-binaries soundfile` so the native PortAudio and libsndfile DLLs are bundled.

**Output:** `dist\PCMPlayer.exe` — a single portable file (~80 MB). Drop it on a USB stick, copy it to any Windows 10/11 machine, run it. No Python required, no installer.

## Run from source (any platform)

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python pcm_player.py
```

You can also pass files on the command line:

```bash
python pcm_player.py track1.pcm track2.wav
```

For Linux / macOS executables, the same PyInstaller line works:

```bash
pyinstaller --noconfirm --clean --onefile --windowed \
  --name PCMPlayer \
  --collect-binaries sounddevice \
  --collect-binaries soundfile \
  --collect-data soundfile \
  pcm_player.py
```

## Project layout

```
pcmplayer/
├── pcm_player.py        # Application (single file)
├── requirements.txt     # Python dependencies
├── build_windows.bat    # Windows build script
└── README.md            # This file
```

## Technical notes

- **Audio engine** uses `sounddevice.OutputStream` with a real-time callback running on PortAudio's thread. State mutations are serialized behind a single lock so the GUI thread can manipulate the engine safely without glitching playback.
- **Decoding** is delegated to **libsndfile** via `soundfile`. For raw PCM, the file is read into a buffer and passed to `sf.read(format='RAW', subtype=…, endian=…)` with parameters from the UI — the same backend Audacity and most pro tools use under the hood.
- The one combination libsndfile doesn't support natively (PCM unsigned 16-bit) is handled by a small NumPy decoder in the codebase.
- **Waveform peaks** are precomputed on a worker thread after load so the UI doesn't stall on long files. Drawing is done in `paintEvent` with `QPainter` directly — no third-party charting library.
- **Seeking** is seamless: the stream is closed, the frame cursor is repositioned, the stream is reopened. On modern hardware it's imperceptible.

## License

Use it however you want.
