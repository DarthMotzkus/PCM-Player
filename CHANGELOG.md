# PCM Player v2.0

Major release: native **Android port** ships alongside the Windows desktop build, with a fully automated CI pipeline that builds both binaries and publishes them to a single GitHub Release per tag.

## What's new

- **Android port** (`android/`) — native app written in Kotlin + AndroidX Media3 (ExoPlayer) + Material 3:
  - Same audio formats as desktop: WAV · FLAC · OGG/Vorbis · OPUS · AIFF · AU · MP3, plus raw PCM (`.pcm`, `.raw`, `.s8`, `.s16/le/be`, `.s24/le/be`, `.s32/le/be`, `.u8`, `.f32/le/be`, `.f64`)
  - Raw PCM auto-detected from extension (44 100 Hz · stereo · 16-bit signed LE for `.pcm`, matching MSU-1)
  - Four switchable themes — **Ocean** (default), **Forest**, **Sunset**, **Graphite** — same palette as desktop, persisted via `SharedPreferences`
  - Transport: play / pause / stop / previous / next + 3-state repeat (off → one → all)
  - Click-to-seek waveform with precomputed peaks for raw PCM
  - Variable playback speed 0.50× – 2.50× (0.05 step), tap the readout to reset to 1.00×
  - Playlist with auto-advance and tap-to-jump
  - Opens audio via **Open with…**, **share/send** intents, and a built-in file picker
- **CI/Release pipeline** (`.github/workflows/`):
  - `build-android.yml` and `build-windows.yml` build APK + EXE on every push to `main`, uploading as artifacts
  - `release.yml` triggers on numeric tag pushes (`2.0`, `2.1`, …) — runs both builds fresh, extracts the matching CHANGELOG section, and publishes a GitHub Release with `PCMPlayer.exe` + `PCMPlayer-<tag>.apk` attached
  - Tag pattern is bare numeric to match the existing repo convention (no `v` prefix)

## Notes

- The Windows context-menu installer is desktop-only and not ported — Android uses the system **Open with…** picker instead, which the app already accepts via intent.
- The APK is built as **debug** (debuggable, signed with the default Android debug key). Install via "Install from unknown sources" on your device. A signed release variant is a future step once a keystore is in place.

## Download

Grab `PCMPlayer.exe` (Windows) and `PCMPlayer-2.0.apk` (Android) from the assets below. The desktop binary is portable (no install). For Android, transfer the APK and enable "Install from unknown sources" if prompted.

## Requirements

- Windows 10/11 (desktop)
- Android 7.0 / API 24+ (mobile)

---

# PCM Player v1.2

Right-click integration overhaul, repeat modes, waveform-as-timeline with click + drag seeking, a slim progress strip below the waveform, a centered cluster of volume + speed controls, and a long list of fixes around the file-handoff path.

## What's new

- **Single-instance** — only one PCMPlayer window can be open at a time. Any extra launches (e.g. when Explorer falls back to one-process-per-file for multi-select) hand their argv to the existing window over a `QLocalServer` socket and exit immediately. The running window appends the incoming files to its playlist and brings itself to the front.
- **Folder context menu** — the install now registers the verb in three places:
  - any **file** (`*\shell`)
  - any **folder** (`Directory\shell`) — right-click a folder to queue every audio file inside it
  - the **folder background** (`Directory\Background\shell`) — right-click empty space inside an open folder, same effect
  - In all cases the player scans the folder non-recursively, filters by known audio extensions, sorts case-insensitively, and queues the result.
- **Repeat button** with a 3-state cycle: **off → repeat one track → repeat playlist → off**. The button is highlighted with the accent color when active and shows a small `¹` superscript in repeat-one mode.
- **Waveform is the timeline** — click anywhere on the song shape to jump, drag to scrub. Drag is throttled to ~12 Hz so the audio stream doesn't churn. Played portion is rendered in the theme accent, unplayed portion in a dimmed accent so the song shape stays readable from position 0.
- **Slim progress strip** sits directly below the waveform — a 4 px tall accent-gradient bar that fills as the song plays and supports click-to-seek (custom `ClickableSlider`, no draggable knob, just a visual indicator).
- **Speed controls demoted and centered** — no more big "SPEED" label. The `1.00x` value plus tiny `−` / `+` / `⟲` steppers sit right next to the volume slider in a single centered cluster. Double-click the value to reset to 1.00×.

## Fixed

- **Peaks computation never reached the GUI** — `compute_peaks` ran successfully in the worker thread but the `QTimer.singleShot` we used to hop back to the main thread silently failed to marshal, leaving the waveform stuck on its empty/loading state. Replaced with a proper `Signal` + queued connection, which Qt routes cross-thread automatically.
- Selecting many files in Explorer and choosing *Play with PCM-Player* would open one player per file instead of one playlist. Even with `MultiSelectModel="Player"` set, Windows can still split the invocation in some scenarios (e.g. mixed selections, slow shell handlers); the new single-instance guard makes the result a single window with the full list every time.
- *Previous* / *Next* transport buttons stayed disabled when files were added to the playlist mid-playback. They now wake up the moment the playlist reaches more than one item, regardless of how the items got there.
- The right-click verb wasn't visible on folders at all — only on individual files.
- `MainWindow._update_ui_state` referenced `btn_back5` / `btn_fwd5` after those buttons were removed in v1.1, crashing the app on startup of any packaged build that hit `_update_ui_state`.

## Download

Grab the `PCMPlayer.exe` from the assets below — no installation required. The right-click integration is one click away in the gear menu.

## Requirements

- Windows 10/11

---

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
