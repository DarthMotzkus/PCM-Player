# PCM Player — Android

Native Android port of [PCM-Player](https://github.com/DarthMotzkus/PCM-Player), a fully-compatible audio player with first-class support for raw PCM files (originally built to play MSU-1 SNES rom-hack soundtracks).

## Features

- **Modern Material 3 UI** with switchable themes — Ocean (default), Forest, Sunset, Graphite
- Plays the same formats as the desktop version: WAV · FLAC · OGG/Vorbis · OPUS · AIFF · AU · MP3, plus raw PCM (`.pcm`, `.raw`, `.s8`, `.s16/le/be`, `.s24/le/be`, `.s32/le/be`, `.u8`, `.f32/le/be`, `.f64`)
- Raw PCM auto-detected from filename extension (sensible defaults: 44 100 Hz · stereo · 16-bit signed LE for `.pcm`)
- **Transport:** play / pause / stop / previous / next, plus 3-state repeat (off → one → all)
- **Click-to-seek waveform** display; precomputed peaks for raw PCM, decorative placeholder for compressed formats
- **Variable playback speed** 0.50× – 2.50× (0.05 step), tap the speed readout to reset to 1.00×
- Playlist with auto-advance and tap-to-jump
- Opens audio files passed via "Open with…", share / send intents, and a built-in file picker
- Persistent theme preference

The only desktop feature that doesn't carry over is the Windows right-click context-menu installer — irrelevant on Android, which uses the system "Open with…" picker instead.

## Getting the APK

You have **two ways** to build the APK. Pick whichever fits your setup.

### Option 1 — GitHub Actions (no local tooling needed)

1. Push this project to a GitHub repository.
2. GitHub Actions runs the `.github/workflows/build.yml` workflow on every push.
3. Open the latest run under the **Actions** tab → download the `PCMPlayer-debug-apk` artifact (.zip with the APK inside).
4. Transfer the APK to your phone and install (enable "Install from unknown sources" if prompted).

No Android Studio, no Gradle setup on your machine. The build runs on GitHub's infrastructure with full access to the Android SDK / Maven dependencies that aren't reachable from sandboxed environments.

### Option 2 — Build locally

Requirements: **Android Studio Hedgehog** (or newer) **or** JDK 17 + Android SDK + Gradle 8.7+.

```bash
# From the project root
./gradlew assembleDebug
# or, if there's no gradle wrapper yet:
gradle wrapper --gradle-version 8.7
./gradlew assembleDebug
```

The APK lands in `app/build/outputs/apk/debug/app-debug.apk`. First build pulls ~100 MB of dependencies from Google Maven and Maven Central; subsequent builds are cached.

To open in Android Studio: **File → Open → select the project folder**, wait for Gradle sync, hit **Run** (▶).

## MSU-1 quick guide

Drop any MSU-1 `.pcm` file into the playlist. The defaults already match (44 100 Hz, stereo, 16-bit signed LE). The 8 leading metadata bytes (`MSU1` magic + 4-byte loop point) play through as a very short click at the start of the track — to remove it, strip those 8 bytes with any hex editor or `tail -c +9 in.pcm > out.pcm`.

## Project layout

```
PCMPlayerAndroid/
├── .github/workflows/build.yml      # CI: builds the APK on push
├── app/
│   ├── build.gradle.kts             # App-level build config
│   ├── proguard-rules.pro
│   └── src/main/
│       ├── AndroidManifest.xml
│       ├── java/com/darthmotzkus/pcmplayer/
│       │   ├── MainActivity.kt
│       │   ├── AudioEngine.kt       # ExoPlayer wrapper, supports raw PCM via in-memory WAV
│       │   ├── PcmDecoder.kt        # Raw PCM → float → WAV header conversion
│       │   ├── WaveformView.kt      # Custom view, click-to-seek
│       │   ├── PlaylistAdapter.kt   # RecyclerView adapter
│       │   ├── ThemeManager.kt      # Theme switching + persistence
│       │   ├── Track.kt
│       │   └── PcmPlayerApp.kt
│       └── res/                     # layouts, icons, themes, strings
├── build.gradle.kts
├── settings.gradle.kts
├── gradle.properties
├── gradle/wrapper/gradle-wrapper.properties
└── README.md
```

## Technical notes

- **Playback engine:** AndroidX Media3 (ExoPlayer). It handles WAV/FLAC/OGG/MP3/AIFF/etc. natively, plus seeking and `PlaybackParameters`-based variable speed.
- **Raw PCM bridge:** when the file is `.pcm` or any other raw PCM extension, the bytes are decoded with `PcmDecoder.decodeToFloat()`, requantized to 16-bit and wrapped in a 44-byte RIFF/WAVE header in memory. ExoPlayer plays it through `ByteArrayDataSource` like any other progressive media. Same code path, same seek/speed/loop behavior for every format.
- **24-bit and float PCM:** decoded sample-by-sample with sign-extension for signed 24-bit, byte-swap for big-endian.
- **Waveform:** for raw PCM, peaks come from the same float array used to build the WAV body — costs one extra pass over the samples, done off the main thread. For compressed formats, a synthetic sine-envelope shows a decorative bar that still works as a click-to-seek surface.
- **Theme system:** four `AppTheme` enums hold accent + surface + border colors; on selection, all card backgrounds and button tints are re-tinted programmatically. The choice is persisted via `SharedPreferences`.
- **Intent handling:** the launcher activity is `singleTask`. Sharing audio from other apps (`Intent.ACTION_SEND` / `SEND_MULTIPLE`) or "Open with…" (`ACTION_VIEW`) routes through `onNewIntent`, appends to the playlist, and starts playback.

## License

GPL-2.0, matching the desktop project.
