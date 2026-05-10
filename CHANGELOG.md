# PCM Player v1.1

UI redesign with switchable themes, brushed-metal transport buttons, real-time speed control, and one-click Windows context-menu integration.

## What's new

- **Switchable themes** — gear icon in the header opens a picker with **Ocean** (deep blue, default), **Forest** (emerald green), **Sunset** (warm orange) and **Graphite** (black/gray)
- **Portable settings** — the chosen theme is saved to `settings.json` next to the `.exe` (no registry, no AppData; works from a USB stick)
- **Brushed-metal transport buttons** with a soft press animation (offset + blur shadow shrink in 90 ms on click) and a unified Unicode media-control glyph set (`⏹` `⏮` `▶` / `⏸` `⏭`)
- **Real-time playback speed** with stepwise `−` / `+` buttons (0.05× per click, range 0.50× – 2.50×) and a one-click reset to 1.00× — replaces the previous slider for finer, more deliberate control
- **Auto-play on launch** — opening a file via the OS file association or sending one through the right-click context menu starts playback immediately
- **In-app context-menu install** — the gear menu offers a one-click "Install in Windows right-click menu" / "Remove from Windows right-click menu" toggle (auto-detects the current state via `winreg`, no admin required, multi-select aware via `MultiSelectModel=Player`)
- **Optional `.bat` helpers** for the same registry install/uninstall, for users who prefer not to open the player first
- **Custom application icon** embedded in the `.exe`; the Windows taskbar groups under PCM Player instead of the generic Python interpreter icon (via `SetCurrentProcessExplicitAppUserModelID`)
- **Responsive layout** — transport and slider rows stay centered when the window is wide instead of spreading their controls to the edges
- **Crash log** (`pcm_player_error.log`) written next to the executable on Python or native faults; auto-purged on a clean exit

## Removed

- Format-parameter panel for raw PCM (sample rate / channels / bit depth / encoding / endian / header skip). The player now relies entirely on libsndfile auto-detection plus filename-extension defaults for raw PCM.
- On-screen ±5 s skip buttons. The arrow keys (← → for ±5 s, Shift+← → for ±30 s) are kept.

## Fixed

- `QApplication`/`QStyleFactory` initialization order that produced an `access violation` (segfault) when the packaged `--windowed` build started — Python init crashed before `sys.excepthook` could fire, so the launcher would just die silently
- `build_windows.bat` calling the broken `pyinstaller.exe` shim (path baked in at venv creation time, broke when the venv was relocated). The script now invokes PyInstaller through `python -m PyInstaller`
- Native libraries (PortAudio, libsndfile) not always being bundled. Build switched to `--collect-all sounddevice --collect-all soundfile`
- `MainWindow._update_ui_state` referencing `btn_back5` / `btn_fwd5` after those buttons were removed from the transport row

## Build options

The Windows build script now supports two env-var toggles:

| Variable     | Effect                                                              |
| ------------ | ------------------------------------------------------------------- |
| `ONEFILE=1`  | Produce a single self-extracting `dist\PCMPlayer.exe` (~60 MB)      |
| `DEBUG=1`    | Build with the console attached + bootloader logs (for diagnostics) |

By default it produces a folder bundle at `dist\PCMPlayer\` (faster startup, fewer antivirus false positives).

## Download

Grab the `PCMPlayer.exe` from the assets below — no installation required.
For the right-click "Play with PCM-Player" entry, also grab `install_context_menu.bat` and `uninstall_context_menu.bat`, or use the in-app gear menu.

## Requirements

- Windows 10/11

---

# PCM Player v1.0

First release of **PCM Player** — a lightweight player for raw PCM audio (the original use case being MSU-1 SNES rom-hack soundtracks) and any common audio format libsndfile understands.

## Features

- **Raw PCM playback** with a configurable panel for sample rate, channels, bit depth, encoding (signed / unsigned / float) and byte order, plus a header-skip offset for files that ship with a small magic block in front of the samples (e.g. MSU-1)
- **Auto-detected formats**: WAV, FLAC, OGG/Vorbis, OPUS, AIFF, AU, MP3 (via libsndfile ≥ 1.1)
- **Transport**: play / pause / stop / previous / next, plus on-screen ±5 s skip buttons
- **Click-to-seek waveform** rendered with `QPainter`, peaks computed on a worker thread so the UI never blocks
- **Drag-and-drop playlist** with auto-advance and double-click-to-jump
- **Keyboard shortcuts** for everything (Space, ← → for ±5 s, Shift+← → for ±30 s, Ctrl+← → for prev/next, Ctrl+O for open)
- **Single-file portable executable** (`dist\PCMPlayer.exe`, no install)

## Download

Grab the `PCMPlayer.exe` from the assets below — no installation required.

## Requirements

- Windows 10/11

---

*See the [README](README.md) for usage details.*
