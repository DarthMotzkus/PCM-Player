# PCM Player

A fully-compatible PCM player for raw audio files — and pretty much any audio format you throw at it.

> **Looking for Android?** See [README Android.md](README%20Android.md) and the [android/](android/) folder. Starting with v2.0, every GitHub Release ships both `PCMPlayer.exe` (Windows) and `PCMPlayer-<version>.apk` (Android), built automatically by CI.

## Origin

The original idea was simple: **play PCM tracks from MSU-1 SNES rom-hacks**, so I could listen to those uncompressed soundtracks outside the emulator. MSU-1 audio comes as headerless (well, near-headerless) 16-bit signed little-endian stereo PCM at 44100 Hz, and most general-purpose players just refuse to open them, or open them at the wrong sample rate.

It quickly grew past that. What started as an MSU-1 listener turned into a full audio player with a modern GUI, broad format auto-detection, real-time speed control, a playlist, and proper transport controls. So now it does what I originally needed — and a lot more.

## Features

- Modern dark UI (PySide6 / Qt 6) with custom waveform display and **brushed-metal transport buttons**
- **Switchable themes** — gear icon in the header opens a picker with **Ocean** (deep blue, default), **Forest** (emerald green), **Sunset** (warm orange) and **Graphite** (black/gray); the selection is remembered in a portable `settings.json` next to the .exe (no registry, no AppData — fully portable)
- **In-app context-menu install** — same gear menu offers a one-click "Install in Windows right-click menu" / "Remove from Windows right-click menu" toggle (auto-detects the current state, no admin required)
- Drag-and-drop anywhere on the window — adds files to the playlist
- **Single-instance:** opening more files while the player is already running appends to the existing playlist instead of spawning a second window
- **Folder support:** right-clicking a folder (or inside a folder's empty area) and choosing *Play with PCM-Player* queues all audio files in that folder, sorted by name
- **Auto-play on launch:** opening a file via association or sending one through the right-click context menu starts playback immediately
- **Waveform timeline:** the song shape itself is the seek bar — click anywhere on it to jump, drag to scrub, all in real time. A slim progress strip below it gives a clean linear "where am I" indicator and also accepts click-to-seek.
- Full transport: **Play / Pause / Stop / Previous / Next / Repeat** (3-state: off → repeat one → repeat all)
- **Real-time playback speed**: stepwise `−` / `+` buttons (0.05× per click, range 0.50× – 2.50×) plus a one-click reset to 1.00×
- Volume slider (defaults to 100 %)
- Animated bevel-style transport buttons with press feedback
- Playlist with auto-advance, double-click to jump, add/remove/clear
- Keyboard shortcuts for everything
- Automatic format detection — no parameter dials, the player figures it out from the file
- Single-file portable executable (one `.exe`, no install)
- Custom application icon embedded in the `.exe` and shown in the Windows taskbar

## Supported formats

**Auto-detected from header (via libsndfile):**
WAV · FLAC · OGG/Vorbis · OPUS · AIFF · AU · **MP3** (libsndfile ≥ 1.1)

**Raw PCM (auto-detected from filename extension):**

| Extension(s)                    | Detected as                                |
| ------------------------------- | ------------------------------------------ |
| `.pcm` · `.raw` · `.bin` · `.dat` | Signed 16-bit, little-endian             |
| `.s8`                           | Signed 8-bit                               |
| `.s16` · `.s16le` / `.s16be`     | Signed 16-bit, little- / big-endian       |
| `.s24` · `.s24le` / `.s24be`     | Signed 24-bit, little- / big-endian       |
| `.s32` · `.s32le` / `.s32be`     | Signed 32-bit, little- / big-endian       |
| `.u8`                           | Unsigned 8-bit                             |
| `.f32` · `.f32le` / `.f32be`     | 32-bit float, little- / big-endian        |
| `.f64`                          | 64-bit float                               |

The default sample rate / channel count for raw files is 44 100 Hz stereo. If your raw file uses a different sample rate or channel count, rename the extension or the player will guess wrong — there's no manual override on the UI by design (the player is meant to be drop-and-play).

## Playing MSU-1 tracks

MSU-1 `.pcm` files use this format:

- **Sample rate:** 44 100 Hz
- **Channels:** 2 (stereo)
- **Bit depth:** 16-bit
- **Encoding:** Signed Int
- **Byte order:** Little Endian
- **Pre-data bytes:** 8 (the `"MSU1"` magic + 4-byte loop point)

Drop the `.pcm` file in and it plays — the auto-detected format already matches MSU-1. The 8 leading metadata bytes will produce a tiny click at the very start of the track since the player auto-detects parameters and doesn't expose a header-skip field. If that bothers you, strip the first 8 bytes from the file (`tail -c +9 in.pcm > out.pcm` or any hex editor).

## Right-click "Play with PCM-Player" (Windows)

You can register the player as a Windows Explorer right-click action so that selecting one or more audio files and choosing **Play with PCM-Player** sends them all as a playlist to the running player.

**Easiest way (in-app):** open the gear menu → click **"Install in Windows right-click menu"**. The same menu auto-detects the current state and toggles to **"Remove from Windows right-click menu"** if it's already installed. Per-user only (`HKCU`), no admin required.

**Alternative (.bat files):** if you'd rather not open the player, the repo also ships `install_context_menu.bat` / `uninstall_context_menu.bat`. Drop them next to `PCMPlayer.exe` and double-click — same end result.

The install registers the verb in three places:
- on **any file** (`*\shell`)
- on **folders** (`Directory\shell` — right-click a folder to queue every audio file inside it)
- on the **folder background** (`Directory\Background\shell` — right-click empty space inside an open folder, same effect)

It uses `MultiSelectModel="Player"` so Explorer invokes the player **once** with all selected items, plus a single-instance guard inside the player so any extra launches that slip through still hand their files over to the running window instead of opening duplicate copies.

If you move `PCMPlayer.exe` to a new location, re-install (gear menu or `.bat`) from there so the registered path stays correct.

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

By default the script produces a folder bundle at `dist\PCMPlayer\PCMPlayer.exe` (faster startup, fewer antivirus false positives — distribute the whole folder, zip it if you want a single file).

**Optional environment variables:**

```cmd
set ONEFILE=1   ::  produce a single self-extracting dist\PCMPlayer.exe (~60 MB)
set DEBUG=1    ::  build with the console attached + bootloader logs (diagnostics)
build_windows.bat
```

The build calls PyInstaller via `python -m PyInstaller` with `--collect-all sounddevice --collect-all soundfile` so the native PortAudio and libsndfile DLLs are bundled, plus `--icon icon.ico --add-data icon.ico;.` so both the executable file icon and the in-app window/taskbar icon use the bundled artwork.

If a packaged build crashes silently in the future, the app writes a `pcm_player_error.log` next to the executable with a full Python and C-level stack trace (via `faulthandler`).

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
  --icon icon.ico \
  --add-data icon.ico:. \
  --collect-all sounddevice \
  --collect-all soundfile \
  pcm_player.py
```

## Project layout

```
pcmplayer/
├── pcm_player.py                  # Application (single file)
├── requirements.txt               # Python dependencies
├── build_windows.bat              # Windows build script
├── install_context_menu.bat       # Adds "Play with PCM-Player" to Explorer right-click
├── uninstall_context_menu.bat     # Removes it
├── icon.ico                       # Multi-resolution Windows icon (embedded in the .exe)
├── CHANGELOG.md                   # Per-version release notes
└── README.md                      # This file
```

## Technical notes

- **Audio engine** uses `sounddevice.OutputStream` with a real-time callback running on PortAudio's thread. State mutations are serialized behind a single lock so the GUI thread can manipulate the engine safely without glitching playback.
- **Variable-speed playback** is done with a linear-interpolation resampler inside the audio callback. At 1.00× there's a fast path with no interpolation cost; at any other rate the callback synthesizes output frames at fractional positions of the source. It changes pitch (tape-style fast/slow), which is the trade-off for being lock-free, allocation-free, and zero-latency.
- **Decoding** is delegated to **libsndfile** via `soundfile`. For raw PCM, the file is read into a buffer and passed to `sf.read(format='RAW', subtype=…, endian=…)` with parameters guessed from the filename extension — the same backend Audacity and most pro tools use under the hood.
- The one combination libsndfile doesn't support natively (PCM unsigned 16-bit) is handled by a small NumPy decoder in the codebase.
- **Waveform peaks** are precomputed on a worker thread after load so the UI doesn't stall on long files. Drawing is done in `paintEvent` with `QPainter` directly — no third-party charting library.
- **Seeking** is seamless: the stream is closed, the frame cursor is repositioned, the stream is reopened. On modern hardware it's imperceptible.
- **Crash safety:** `faulthandler` and `sys.excepthook` write a log file next to the executable on either Python exceptions or native (C-extension) faults — important because the packaged build runs `--windowed` and would otherwise die silently. The log is auto-purged on a clean exit.
- **Windows taskbar identity:** `SetCurrentProcessExplicitAppUserModelID` is called early so the taskbar groups under the PCM Player icon instead of the generic Python interpreter icon.
- **Portable settings:** the chosen theme is written to `settings.json` next to the executable. No registry keys, no AppData — copy the `.exe` and its `settings.json` to a USB stick and your preference travels with it.
- **Context-menu install** uses the Python `winreg` module to write `HKCU\Software\Classes\*\shell\PlayWithPCMPlayer` with `MultiSelectModel=Player`. The gear menu's `aboutToShow` signal re-checks the registry each time it's opened so the install/uninstall label stays in sync.

## License

Use it however you want.
