#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PCM Raw Audio Player
====================
Modern portable audio player with raw PCM support and broad format detection.

Supports out of the box:
  - WAV, FLAC, OGG/Vorbis, AIFF, AU (via libsndfile)
  - MP3 (via libsndfile >= 1.1)
  - Raw PCM in any common variant: S8/U8, S16/U16, S24, S32, F32, F64,
    little/big endian, mono/stereo/multichannel, with optional header skip.

Controls: Play / Pause / Stop / Previous / Next / Seek / Volume
Playlist: Drag-and-drop multiple files, double-click to jump, auto-advance
Shortcuts: Space (play/pause), Left/Right (seek 5s), Shift+Left/Right (jump),
           Ctrl+Left/Right (prev/next), Ctrl+O (open), Esc (stop)
"""

from __future__ import annotations

import io
import json
import os
import sys
import atexit
import threading
import traceback
import faulthandler
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


def _crash_log_path() -> str:
    base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "pcm_player_error.log")


# faulthandler catches native crashes (segfault / access violation from C extensions)
# that sys.excepthook cannot see, and writes a C-level stack trace.
try:
    _CRASH_LOG_PATH = _crash_log_path()
    _CRASH_LOG = open(_CRASH_LOG_PATH, "a", encoding="utf-8", buffering=1)
    faulthandler.enable(file=_CRASH_LOG, all_threads=True)

    def _purge_empty_log() -> None:
        try:
            _CRASH_LOG.close()
            if os.path.getsize(_CRASH_LOG_PATH) == 0:
                os.remove(_CRASH_LOG_PATH)
        except Exception:
            pass

    atexit.register(_purge_empty_log)
except Exception:
    _CRASH_LOG = None


def _log_fatal(prefix: str, exc: BaseException) -> None:
    try:
        with open(_crash_log_path(), "a", encoding="utf-8") as f:
            f.write(f"=== {prefix} ===\n")
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
            f.write("\n")
    except Exception:
        pass


def _excepthook(exctype, value, tb):
    try:
        with open(_crash_log_path(), "a", encoding="utf-8") as f:
            f.write("=== Uncaught exception ===\n")
            f.write("".join(traceback.format_exception(exctype, value, tb)))
            f.write("\n")
    except Exception:
        pass


sys.excepthook = _excepthook


def _resource_path(name: str) -> str:
    """Locate bundled resources both in dev mode and inside a PyInstaller bundle."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def _settings_path() -> str:
    """Path to the portable settings.json — always next to the .exe (frozen)
    or next to the script (dev)."""
    base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "settings.json")


def _load_settings() -> dict:
    try:
        with open(_settings_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_settings(data: dict) -> None:
    try:
        with open(_settings_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Windows right-click "Play with PCM-Player" — install/uninstall via winreg.
# Per-user (HKCU), no admin required. Multi-select aware via MultiSelectModel.
# -----------------------------------------------------------------------------

# Three registry locations: files (any extension), folders (right-click on a
# folder), and the folder background (right-click inside an open folder).
_CTXMENU_KEY_FILE   = r"Software\Classes\*\shell\PlayWithPCMPlayer"
_CTXMENU_KEY_DIR    = r"Software\Classes\Directory\shell\PlayWithPCMPlayer"
_CTXMENU_KEY_DIR_BG = r"Software\Classes\Directory\Background\shell\PlayWithPCMPlayer"


def _ctxmenu_supported() -> bool:
    """Only available on Windows when the player is running as a packaged .exe."""
    return sys.platform == "win32" and getattr(sys, "frozen", False)


def _ctxmenu_is_installed() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CTXMENU_KEY_FILE):
            return True
    except (OSError, FileNotFoundError):
        return False


def _ctxmenu_install() -> bool:
    if not _ctxmenu_supported():
        return False
    try:
        import winreg
        exe = sys.executable

        def _write_verb(key_path: str, command_value: str):
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as k:
                winreg.SetValue(k, "", winreg.REG_SZ, "Play with PCM-Player")
                winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, f'"{exe}",0')
                winreg.SetValueEx(k, "MultiSelectModel", 0, winreg.REG_SZ, "Player")
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path + r"\command") as k:
                winreg.SetValue(k, "", winreg.REG_SZ, command_value)

        # Files: %1 receives the (possibly multi-select) list of file paths.
        _write_verb(_CTXMENU_KEY_FILE, f'"{exe}" %1')
        # Folders (right-click on a folder): %1 is the folder path.
        _write_verb(_CTXMENU_KEY_DIR,  f'"{exe}" %1')
        # Folder background (right-click inside an open folder): %V is the cwd.
        _write_verb(_CTXMENU_KEY_DIR_BG, f'"{exe}" "%V"')
        return True
    except Exception:
        return False


def _ctxmenu_uninstall() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
    except Exception:
        return False
    removed_any = False
    for parent in (_CTXMENU_KEY_FILE, _CTXMENU_KEY_DIR, _CTXMENU_KEY_DIR_BG):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, parent + r"\command")
        except FileNotFoundError:
            pass
        except Exception:
            pass
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, parent)
            removed_any = True
        except FileNotFoundError:
            pass
        except Exception:
            pass
    return removed_any


import numpy as np
import sounddevice as sd
import soundfile as sf

from string import Template

from PySide6.QtCore import (
    QPoint, QPointF, QPropertyAnimation, QRect, QSize, Qt,
    QTimer, QUrl, Signal, QObject, QEvent, QEasingCurve,
)
from PySide6.QtGui import (
    QAction, QBrush, QColor, QDragEnterEvent, QDropEvent, QFont,
    QFontDatabase, QIcon, QKeySequence, QPainter, QPainterPath, QPen,
    QPixmap, QShortcut,
)
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGraphicsDropShadowEffect,
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QMenu, QMessageBox, QPushButton, QSizePolicy, QSlider,
    QStyleFactory, QToolButton, QVBoxLayout, QWidget,
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket

# ============================================================================
# Audio data model and decoding
# ============================================================================

# Map (encoding, bit_depth) -> libsndfile RAW subtype string.
# libsndfile is the workhorse here — it does the heavy lifting.
SUBTYPE_MAP = {
    ("signed",   8): "PCM_S8",
    ("signed",  16): "PCM_16",
    ("signed",  24): "PCM_24",
    ("signed",  32): "PCM_32",
    ("unsigned", 8): "PCM_U8",
    ("float",   32): "FLOAT",
    ("float",   64): "DOUBLE",
}

# Default raw PCM parameters guessed from filename extension.
RAW_EXT_DEFAULTS = {
    "pcm":   ("signed", 16, "le"),
    "raw":   ("signed", 16, "le"),
    "bin":   ("signed", 16, "le"),
    "dat":   ("signed", 16, "le"),
    "s8":    ("signed",  8, "le"),
    "s16":   ("signed", 16, "le"),
    "s16le": ("signed", 16, "le"),
    "s16be": ("signed", 16, "be"),
    "s24":   ("signed", 24, "le"),
    "s24le": ("signed", 24, "le"),
    "s24be": ("signed", 24, "be"),
    "s32":   ("signed", 32, "le"),
    "s32le": ("signed", 32, "le"),
    "s32be": ("signed", 32, "be"),
    "u8":    ("unsigned", 8, "le"),
    "f32":   ("float",  32, "le"),
    "f32le": ("float",  32, "le"),
    "f32be": ("float",  32, "be"),
    "f64":   ("float",  64, "le"),
}

SUPPORTED_EXTENSIONS = (
    "*.wav *.flac *.ogg *.oga *.opus *.aif *.aiff *.au *.snd "
    "*.mp3 *.m4a "
    "*.pcm *.raw *.bin *.dat *.s8 *.s16 *.s24 *.s32 *.u8 *.f32 *.f64 "
    "*.s16le *.s16be *.s24le *.s24be *.s32le *.s32be *.f32le *.f32be"
)

_AUDIO_EXTS = frozenset(
    s.lstrip("*.").lower()
    for s in SUPPORTED_EXTENSIONS.split() if s.startswith("*.")
)


def _is_audio_file(path: str) -> bool:
    return os.path.splitext(path)[1].lstrip(".").lower() in _AUDIO_EXTS


def _expand_args_to_files(args) -> List[str]:
    """Resolve a list of CLI arguments into a flat list of audio files. Folders
    are scanned (non-recursively, sorted case-insensitively) for files whose
    extension matches a known audio format. Used so the right-click menu can
    target a folder and the player automatically queues its audio contents."""
    out: List[str] = []
    for a in args:
        if not a:
            continue
        if os.path.isfile(a):
            out.append(a)
        elif os.path.isdir(a):
            try:
                for f in sorted(os.listdir(a), key=str.lower):
                    full = os.path.join(a, f)
                    if os.path.isfile(full) and _is_audio_file(full):
                        out.append(full)
            except Exception:
                pass
    return out


@dataclass
class TrackInfo:
    """Everything we need to know about a track to load and play it."""
    path: str
    name: str
    size: int
    sample_rate: int = 44100
    channels: int = 2
    bit_depth: int = 16
    encoding: str = "signed"   # 'signed' | 'unsigned' | 'float'
    endian: str = "le"         # 'le' | 'be'
    data_offset: int = 0
    duration: float = 0.0
    detected_type: str = "pcm"  # 'wav', 'flac', 'mp3', 'ogg', 'pcm', etc.


def detect_format(path: str) -> TrackInfo:
    """Inspect a file and return a populated TrackInfo.

    Strategy:
      1. Ask libsndfile if it can recognise the header (covers WAV/FLAC/OGG/MP3/AIFF/AU).
      2. Otherwise fall back to raw PCM with extension-based defaults.
    """
    p = str(path)
    name = os.path.basename(p)
    size = os.path.getsize(p)
    ext = os.path.splitext(name)[1].lstrip(".").lower()

    info = TrackInfo(path=p, name=name, size=size)

    try:
        sfi = sf.info(p)
    except Exception:
        sfi = None

    if sfi is not None:
        info.detected_type = (sfi.format or "").lower()
        info.sample_rate = sfi.samplerate
        info.channels = sfi.channels
        info.duration = float(sfi.duration)
        sub = (sfi.subtype or "").upper()
        if sub.startswith("PCM_"):
            d = sub[4:]
            if d == "S8":
                info.encoding, info.bit_depth = "signed", 8
            elif d == "U8":
                info.encoding, info.bit_depth = "unsigned", 8
            else:
                try:
                    info.encoding, info.bit_depth = "signed", int(d)
                except ValueError:
                    info.encoding, info.bit_depth = "signed", 16
        elif sub == "FLOAT":
            info.encoding, info.bit_depth = "float", 32
        elif sub == "DOUBLE":
            info.encoding, info.bit_depth = "float", 64
        return info

    # Raw PCM fallback
    info.detected_type = "pcm"
    if ext in RAW_EXT_DEFAULTS:
        enc, bd, en = RAW_EXT_DEFAULTS[ext]
        info.encoding, info.bit_depth, info.endian = enc, bd, en
    bps = max(1, info.bit_depth // 8)
    if info.channels > 0 and info.sample_rate > 0:
        info.duration = max(0.0, (size - info.data_offset) / (bps * info.channels * info.sample_rate))
    return info


def load_audio(track: TrackInfo) -> Tuple[np.ndarray, int]:
    """Decode track to a (frames, channels) float32 numpy array. Returns (data, sample_rate)."""
    # Formatted (header-bearing) files: libsndfile handles them directly.
    formatted_types = {"wav", "wave", "flac", "ogg", "oga", "vorbis",
                       "opus", "aiff", "aifc", "au", "snd", "mpeg", "mp3", "mpeg layer iii"}
    if any(t in track.detected_type for t in formatted_types):
        data, sr = sf.read(track.path, dtype="float32", always_2d=True)
        return np.ascontiguousarray(data), int(sr)

    # Raw PCM: ask libsndfile to decode with the user-specified parameters.
    subtype = SUBTYPE_MAP.get((track.encoding, track.bit_depth))
    if subtype is None:
        # Unsigned 16-bit isn't a libsndfile subtype; decode manually.
        if track.encoding == "unsigned" and track.bit_depth == 16:
            return _decode_u16(track), track.sample_rate
        raise ValueError(
            f"Unsupported raw PCM combination: {track.encoding} {track.bit_depth}-bit"
        )

    endian = "LITTLE" if track.endian == "le" else "BIG"
    with open(track.path, "rb") as f:
        if track.data_offset:
            f.seek(track.data_offset)
        raw = f.read()

    data, sr = sf.read(
        io.BytesIO(raw),
        samplerate=track.sample_rate,
        channels=track.channels,
        format="RAW",
        subtype=subtype,
        endian=endian,
        dtype="float32",
        always_2d=True,
    )
    return np.ascontiguousarray(data), int(sr)


def _decode_u16(track: TrackInfo) -> np.ndarray:
    """Manual unsigned-16 decoder (libsndfile lacks PCM_U16)."""
    with open(track.path, "rb") as f:
        if track.data_offset:
            f.seek(track.data_offset)
        raw = f.read()
    dt = np.dtype("<u2") if track.endian == "le" else np.dtype(">u2")
    arr = np.frombuffer(raw, dtype=dt).astype(np.float32)
    arr = (arr - 32768.0) / 32768.0
    n = (arr.size // track.channels) * track.channels
    arr = arr[:n].reshape(-1, track.channels)
    return np.ascontiguousarray(arr)


def compute_peaks(samples: np.ndarray, n_buckets: int = 480) -> np.ndarray:
    """Compress audio to N peak values for waveform drawing. Mono mix of channels."""
    if samples.size == 0 or n_buckets <= 0:
        return np.zeros(max(1, n_buckets), dtype=np.float32)
    mono = samples.mean(axis=1) if samples.ndim == 2 else samples
    # Pad and reshape to (n_buckets, bucket_size) then take per-bucket max abs.
    bucket = max(1, mono.size // n_buckets)
    usable = bucket * n_buckets
    if usable <= 0:
        return np.zeros(n_buckets, dtype=np.float32)
    trimmed = np.abs(mono[:usable]).reshape(n_buckets, bucket)
    peaks = trimmed.max(axis=1).astype(np.float32)
    m = float(peaks.max()) if peaks.size else 1.0
    if m > 1e-9:
        peaks = peaks / m
    return peaks


# ============================================================================
# Audio engine
# ============================================================================

class AudioEngine(QObject):
    """Threaded playback using sounddevice's callback API.

    The audio callback runs on PortAudio's thread; we serialize state
    mutations behind a single lock so the GUI can poke the engine safely.
    """
    position_changed = Signal(float)   # current position in seconds
    duration_changed = Signal(float)
    state_changed = Signal(str)        # 'idle' | 'playing' | 'paused'
    track_loaded = Signal(object)      # TrackInfo
    track_finished = Signal()
    error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._stream: Optional[sd.OutputStream] = None
        self._samples: Optional[np.ndarray] = None
        self._sample_rate: int = 44100
        self._channels: int = 2
        self._fpos: float = 0.0       # fractional frame position (supports variable speed)
        self._volume: float = 1.0
        self._speed: float = 1.0      # 1.0 = real time; <1 slower, >1 faster (changes pitch)
        self._state: str = "idle"
        self._track: Optional[TrackInfo] = None

        self._poll = QTimer(self)
        self._poll.setInterval(33)   # ~30 fps UI refresh
        self._poll.timeout.connect(self._emit_position)

    # -- public properties --------------------------------------------------
    @property
    def state(self) -> str: return self._state
    @property
    def track(self) -> Optional[TrackInfo]: return self._track
    @property
    def samples(self) -> Optional[np.ndarray]: return self._samples
    @property
    def duration(self) -> float:
        return (len(self._samples) / float(self._sample_rate)) if self._samples is not None else 0.0
    @property
    def position(self) -> float:
        return (self._fpos / float(self._sample_rate)) if self._samples is not None else 0.0
    @property
    def volume(self) -> float: return self._volume
    @property
    def speed(self) -> float: return self._speed

    def set_volume(self, v: float) -> None:
        self._volume = max(0.0, min(1.0, float(v)))

    def set_speed(self, v: float) -> None:
        with self._lock:
            self._speed = max(0.25, min(3.0, float(v)))

    # -- internal -----------------------------------------------------------
    def _emit_position(self) -> None:
        self.position_changed.emit(self.position)
        if (self._samples is not None
                and self._fpos >= len(self._samples)
                and self._state == "playing"):
            self._set_state("idle")
            self._poll.stop()
            self.track_finished.emit()

    def _set_state(self, s: str) -> None:
        if s != self._state:
            self._state = s
            self.state_changed.emit(s)

    def _close_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _callback(self, outdata, frames, time_info, status) -> None:
        # Real-time audio thread. Keep this short and lock-light.
        with self._lock:
            if self._samples is None:
                outdata.fill(0)
                return
            n_in = len(self._samples)
            speed = self._speed
            # Fast path at 1x: integer-indexed copy, no interp cost.
            if speed == 1.0:
                start = int(self._fpos)
                end = start + frames
                if end >= n_in:
                    remaining = max(0, n_in - start)
                    if remaining > 0:
                        outdata[:remaining] = self._samples[start:start + remaining] * self._volume
                    if remaining < frames:
                        outdata[remaining:].fill(0)
                    self._fpos = float(n_in)
                    raise sd.CallbackStop
                outdata[:] = self._samples[start:end] * self._volume
                self._fpos = float(end)
                return

            # Variable speed: linear interpolation between adjacent input frames.
            idx = self._fpos + np.arange(frames, dtype=np.float64) * speed
            end_fpos = self._fpos + frames * speed
            if end_fpos >= n_in - 1:
                valid = int(np.searchsorted(idx, n_in - 1, side="left"))
                if valid > 0:
                    iv = idx[:valid]
                    i0 = iv.astype(np.int64)
                    frac = (iv - i0).reshape(-1, 1).astype(np.float32)
                    outdata[:valid] = (self._samples[i0] * (1.0 - frac)
                                       + self._samples[i0 + 1] * frac) * self._volume
                outdata[valid:].fill(0)
                self._fpos = float(n_in)
                raise sd.CallbackStop
            i0 = idx.astype(np.int64)
            frac = (idx - i0).reshape(-1, 1).astype(np.float32)
            outdata[:] = (self._samples[i0] * (1.0 - frac)
                          + self._samples[i0 + 1] * frac) * self._volume
            self._fpos = end_fpos

    # -- public commands ----------------------------------------------------
    def load(self, track: TrackInfo) -> None:
        self.stop()
        try:
            data, sr = load_audio(track)
            with self._lock:
                self._samples = data
                self._sample_rate = sr
                self._channels = data.shape[1]
                self._fpos = 0.0
                self._track = track
                track.duration = len(data) / float(sr)
            self.track_loaded.emit(track)
            self.duration_changed.emit(self.duration)
            self.position_changed.emit(0.0)
            self._set_state("idle")
        except Exception as e:
            self.error.emit(f"Failed to load {os.path.basename(track.path)}: {e}")

    def reload_with(self, track: TrackInfo) -> None:
        """Reload current file with new format parameters (raw PCM tweaks)."""
        was_playing = self._state == "playing"
        self.load(track)
        if was_playing:
            self.play()

    def play(self) -> None:
        if self._samples is None:
            return
        if self._state == "playing":
            return
        with self._lock:
            if self._fpos >= len(self._samples):
                self._fpos = 0.0
        try:
            self._close_stream()
            self._stream = sd.OutputStream(
                samplerate=self._sample_rate,
                channels=self._channels,
                callback=self._callback,
                dtype="float32",
            )
            self._stream.start()
            self._set_state("playing")
            self._poll.start()
        except Exception as e:
            self.error.emit(f"Playback error: {e}")

    def pause(self) -> None:
        if self._state != "playing":
            return
        self._close_stream()
        self._set_state("paused")
        self._poll.stop()

    def stop(self) -> None:
        self._close_stream()
        with self._lock:
            self._fpos = 0.0
        self._set_state("idle")
        self._poll.stop()
        self.position_changed.emit(0.0)

    def toggle_play(self) -> None:
        if self._state == "playing":
            self.pause()
        else:
            self.play()

    def seek(self, seconds: float) -> None:
        if self._samples is None:
            return
        was_playing = self._state == "playing"
        # Seamless seek: stop the stream, jump the cursor, restart if needed.
        self._close_stream()
        with self._lock:
            target = max(0.0, min(seconds, self.duration)) * self._sample_rate
            self._fpos = min(target, float(len(self._samples)))
        if was_playing:
            try:
                self._stream = sd.OutputStream(
                    samplerate=self._sample_rate,
                    channels=self._channels,
                    callback=self._callback,
                    dtype="float32",
                )
                self._stream.start()
                # _poll is already running
            except Exception as e:
                self._set_state("paused")
                self._poll.stop()
                self.error.emit(f"Seek error: {e}")
                self.position_changed.emit(self.position)
                return
        self.position_changed.emit(self.position)


# ============================================================================
# Custom widgets
# ============================================================================

class WaveformWidget(QWidget):
    """Click-to-seek waveform display, drawn from precomputed peaks."""
    seek_requested = Signal(float)   # seconds

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(110)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.PointingHandCursor)
        self._peaks: Optional[np.ndarray] = None
        self._duration: float = 0.0
        self._position: float = 0.0
        self._loading = False
        self._empty_text = "NO FILE LOADED"
        self._dragging = False
        self._last_seek_pos = -1.0
        self.apply_theme(THEMES[DEFAULT_THEME])

    def apply_theme(self, t: dict):
        self._wf_bg_top = QColor(t["drop_bg_top"])
        self._wf_bg_bot = QColor(t["drop_bg_bot"])
        self._wf_border = QColor(t["border"])
        # Played: bright accent. Unplayed: same accent dimmed but still
        # clearly visible — at position 0 every bar is "unplayed", so this
        # alpha decides whether the song shape is readable at all.
        self._wf_played = QColor(t["accent"])
        self._wf_unplayed = QColor(t["accent"])
        self._wf_unplayed.setAlpha(95)
        self._wf_playhead = QColor(t["accent_glow"])
        self._wf_text = QColor(t["text_label"])
        self._wf_centerline = QColor(t["text_mute"])
        self._wf_centerline.setAlpha(35)
        self.update()

    def set_loading(self, loading: bool):
        self._loading = loading
        self.update()

    def set_peaks(self, peaks: Optional[np.ndarray], duration: float):
        self._peaks = peaks
        self._duration = float(duration)
        self.update()

    def set_position(self, seconds: float):
        self._position = float(seconds)
        self.update()

    def _seek_from_x(self, x: float, throttle: bool = False) -> None:
        if self._duration <= 0 or self._peaks is None:
            return
        ratio = max(0.0, min(1.0, x / max(1, self.width())))
        target = ratio * self._duration
        if throttle and abs(target - self._last_seek_pos) < 0.08:
            return
        self._last_seek_pos = target
        self._position = target  # paint immediately for responsiveness
        self.update()
        self.seek_requested.emit(target)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._seek_from_x(event.position().x())

    def mouseMoveEvent(self, event):
        if self._dragging and (event.buttons() & Qt.LeftButton):
            # Throttle to ~12 Hz so the audio engine isn't churning the stream
            # 60 times per second while the user drags across the waveform.
            self._seek_from_x(event.position().x(), throttle=True)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self._seek_from_x(event.position().x())

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        w, h = self.width(), self.height()

        # Background card with subtle vertical gradient
        from PySide6.QtGui import QLinearGradient
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, self._wf_bg_top)
        bg.setColorAt(1.0, self._wf_bg_bot)
        p.fillRect(self.rect(), bg)
        p.setPen(QPen(self._wf_border, 1))
        p.drawRect(0, 0, w - 1, h - 1)

        # Centerline
        p.setPen(QPen(self._wf_centerline, 1))
        p.drawLine(0, h // 2, w, h // 2)

        if self._peaks is None or self._peaks.size == 0:
            # While peaks are being computed (short window for typical files),
            # leave the area empty — just the gradient + centerline. The real
            # song waveform replaces this as soon as compute_peaks returns.
            # Only show the placeholder text when no file is loaded at all.
            if not self._loading:
                p.setPen(self._wf_text)
                font = p.font()
                font.setPointSize(9)
                font.setLetterSpacing(QFont.PercentageSpacing, 120)
                p.setFont(font)
                p.drawText(self.rect(), Qt.AlignCenter, self._empty_text)
            return

        n = self._peaks.size
        bw = max(1.0, w / n)
        progress = (self._position / self._duration) if self._duration > 0 else 0.0
        progress = max(0.0, min(1.0, progress))
        px = int(progress * w)

        for i in range(n):
            x = int(i * bw)
            bar_h = max(1, int(self._peaks[i] * h * 0.88))
            color = self._wf_played if x < px else self._wf_unplayed
            p.fillRect(x, (h - bar_h) // 2, max(1, int(bw - 0.5) or 1), bar_h, color)

        # Playhead
        if self._duration > 0:
            p.setPen(QPen(self._wf_playhead, 2))
            p.drawLine(px, 2, px, h - 2)



class AnimatedButton(QToolButton):
    """Tool button with a soft drop shadow that retracts on press, giving the
    impression that the button physically depresses into the panel."""

    def __init__(self, parent=None, *,
                 shadow_color: QColor = QColor(0, 0, 0, 160),
                 shadow_blur: int = 14,
                 shadow_offset: int = 3,
                 glow: bool = False):
        super().__init__(parent)
        self._rest_offset = shadow_offset
        self._rest_blur = shadow_blur
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(shadow_blur)
        self._shadow.setColor(shadow_color)
        self._shadow.setOffset(0, shadow_offset)
        self.setGraphicsEffect(self._shadow)

        # Animate offset and blur together so the press feels physical: the
        # shadow shrinks toward the button as it travels down. OutQuad is
        # snappier than OutCubic and matches typical UI press feedback.
        self._anim_off = QPropertyAnimation(self._shadow, b"offset", self)
        self._anim_blur = QPropertyAnimation(self._shadow, b"blurRadius", self)
        for anim in (self._anim_off, self._anim_blur):
            anim.setDuration(90)
            anim.setEasingCurve(QEasingCurve.OutQuad)

        if glow:
            self._shadow.setColor(QColor(41, 182, 246, 180))

    def set_shadow_color(self, color: QColor) -> None:
        self._shadow.setColor(color)

    def _animate(self, off_y: float, blur: float) -> None:
        self._anim_off.stop()
        self._anim_off.setStartValue(self._shadow.offset())
        self._anim_off.setEndValue(QPointF(0, off_y))
        self._anim_off.start()
        self._anim_blur.stop()
        self._anim_blur.setStartValue(self._shadow.blurRadius())
        self._anim_blur.setEndValue(blur)
        self._anim_blur.start()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.isEnabled():
            self._animate(0, max(3.0, self._rest_blur * 0.4))
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._animate(self._rest_offset, self._rest_blur)
        super().mouseReleaseEvent(e)


class DropZone(QFrame):
    """Dashed drop area used when no track is loaded."""
    files_dropped = Signal(list)   # list[str]
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(120)
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        icon = QLabel("⬆")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size:24px;color:#777;")
        title = QLabel("DROP AUDIO FILES HERE")
        title.setAlignment(Qt.AlignCenter)
        title.setObjectName("DropTitle")
        hint = QLabel("PCM · RAW · WAV · FLAC · OGG · MP3 · AIFF · F32 · S16 · S24 · S32")
        hint.setAlignment(Qt.AlignCenter)
        hint.setObjectName("DropHint")
        hint.setWordWrap(True)
        lay.addWidget(icon)
        lay.addWidget(title)
        lay.addWidget(hint)

    def mousePressEvent(self, _e):
        self.clicked.emit()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.setProperty("dragOver", True)
            self.style().unpolish(self); self.style().polish(self)

    def dragLeaveEvent(self, _e):
        self.setProperty("dragOver", False)
        self.style().unpolish(self); self.style().polish(self)

    def dropEvent(self, e: QDropEvent):
        self.setProperty("dragOver", False)
        self.style().unpolish(self); self.style().polish(self)
        urls = e.mimeData().urls()
        files = [u.toLocalFile() for u in urls if u.isLocalFile()]
        if files:
            self.files_dropped.emit(files)


# ============================================================================
# Main window
# ============================================================================

# ============================================================================
# Themes — palettes for the deep-blue Ocean (default), green Forest, orange
# Sunset, and grayscale Graphite. Each theme defines the page background, card
# tones, accent (used by the play button, sliders, badges, and waveform),
# and a 5-stop "metal" gradient used to give all transport buttons a brushed
# metal feel: a bright top edge, a highlight band near the top, a flat mid
# face, and a sharp shadow at the bottom.
# ============================================================================

THEMES = {
    "ocean": {
        "name": "Ocean",
        "bg":          "#0A1929",
        "card_top":    "#15324F",
        "card_bot":    "#10263F",
        "card_hover":  "#1A4670",
        "border":      "#1E3A5F",
        "drop_bg_top": "#102542",
        "drop_bg_bot": "#0B1C30",
        "drop_border": "#1E4870",
        "drop_glow":   "rgba(41, 182, 246, 30)",
        "accent":      "#29B6F6",
        "accent_hi":   "#4FC3F7",
        "accent_glow": "#80DEEA",
        "accent_dark": "#015D85",
        "accent_text": "#042032",
        "text":        "#E3F2FD",
        "text_dim":    "#B0D4F1",
        "text_mute":   "#7AAACF",
        "text_label":  "#5C8AAB",
        "list_bg":     "#0E2238",
        "list_hover":  "#15324F",
        "list_sel_a":  "#1A4D7A",
        "list_sel_b":  "#2C5A8F",
        "metal_edge":   "#5C8AB5",
        "metal_high":   "#3F6A92",
        "metal_mid":    "#1F3F62",
        "metal_low":    "#122846",
        "metal_shadow": "#061122",
        "metal_text":   "#DDEEFB",
        "metal_text_hi":"#FFFFFF",
        "shadow_glow":  "rgba(41, 182, 246, 180)",
    },
    "forest": {
        "name": "Forest",
        "bg":          "#0A1F18",
        "card_top":    "#15402E",
        "card_bot":    "#0F2E20",
        "card_hover":  "#1B5238",
        "border":      "#1E4530",
        "drop_bg_top": "#10301F",
        "drop_bg_bot": "#0B2418",
        "drop_border": "#1E5538",
        "drop_glow":   "rgba(34, 197, 94, 30)",
        "accent":      "#22C55E",
        "accent_hi":   "#4ADE80",
        "accent_glow": "#86EFAC",
        "accent_dark": "#14532D",
        "accent_text": "#062012",
        "text":        "#DCFCE7",
        "text_dim":    "#A7E0BC",
        "text_mute":   "#73B891",
        "text_label":  "#5A8C70",
        "list_bg":     "#0F2A1D",
        "list_hover":  "#15402E",
        "list_sel_a":  "#1B5238",
        "list_sel_b":  "#2C7A4D",
        "metal_edge":   "#5CB58A",
        "metal_high":   "#3F926A",
        "metal_mid":    "#1F623F",
        "metal_low":    "#124628",
        "metal_shadow": "#06220F",
        "metal_text":   "#DDF5E5",
        "metal_text_hi":"#FFFFFF",
        "shadow_glow":  "rgba(34, 197, 94, 180)",
    },
    "sunset": {
        "name": "Sunset",
        "bg":          "#1A0F08",
        "card_top":    "#3E1F0E",
        "card_bot":    "#2A1408",
        "card_hover":  "#5A2D14",
        "border":      "#4A2510",
        "drop_bg_top": "#3A1B0C",
        "drop_bg_bot": "#1F0F06",
        "drop_border": "#5A2D14",
        "drop_glow":   "rgba(249, 115, 22, 30)",
        "accent":      "#F97316",
        "accent_hi":   "#FB923C",
        "accent_glow": "#FED7AA",
        "accent_dark": "#9A3412",
        "accent_text": "#26110A",
        "text":        "#FFEDD5",
        "text_dim":    "#FBC58A",
        "text_mute":   "#C88E5C",
        "text_label":  "#946540",
        "list_bg":     "#2A1408",
        "list_hover":  "#3E1F0E",
        "list_sel_a":  "#5A2D14",
        "list_sel_b":  "#7A3F1B",
        "metal_edge":   "#C58B4D",
        "metal_high":   "#A66931",
        "metal_mid":    "#6B3F18",
        "metal_low":    "#46280C",
        "metal_shadow": "#221404",
        "metal_text":   "#FFE0BC",
        "metal_text_hi":"#FFFFFF",
        "shadow_glow":  "rgba(249, 115, 22, 180)",
    },
    "graphite": {
        "name": "Graphite",
        "bg":          "#0F0F0F",
        "card_top":    "#252528",
        "card_bot":    "#1A1A1C",
        "card_hover":  "#36363A",
        "border":      "#2E2E32",
        "drop_bg_top": "#1F1F22",
        "drop_bg_bot": "#141416",
        "drop_border": "#3A3A3E",
        "drop_glow":   "rgba(212, 212, 216, 28)",
        "accent":      "#D4D4D8",
        "accent_hi":   "#FAFAFA",
        "accent_glow": "#F4F4F5",
        "accent_dark": "#71717A",
        "accent_text": "#0A0A0A",
        "text":        "#FAFAFA",
        "text_dim":    "#D4D4D8",
        "text_mute":   "#A1A1AA",
        "text_label":  "#71717A",
        "list_bg":     "#161618",
        "list_hover":  "#252528",
        "list_sel_a":  "#3F3F46",
        "list_sel_b":  "#52525B",
        "metal_edge":   "#C0C5CC",
        "metal_high":   "#909598",
        "metal_mid":    "#5A5F65",
        "metal_low":    "#34373C",
        "metal_shadow": "#0D0E10",
        "metal_text":   "#F4F4F5",
        "metal_text_hi":"#FFFFFF",
        "shadow_glow":  "rgba(212, 212, 216, 140)",
    },
}

DEFAULT_THEME = "ocean"


_QSS_TEMPLATE = Template("""
QMainWindow, QWidget#Central { background: $bg; color: $text; }
QLabel { color: $text_dim; }

QLabel#Title { color: $accent_hi; font-weight: 700; font-size: 16px; letter-spacing: 6px; }
QLabel#Subtitle { color: $text_label; font-size: 9px; letter-spacing: 4px; }
QLabel#SectionLabel { color: $text_label; font-size: 9px; letter-spacing: 5px; }
QLabel#Badge {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 $accent_hi, stop:1 $accent);
    color: $accent_text; font-weight: 700;
    padding: 3px 10px; border-radius: 6px; font-size: 9px; letter-spacing: 1px;
}
QLabel#FileName { color: $text; font-size: 13px; }
QLabel#FileMeta { color: $text_mute; font-size: 10px; }
QLabel#Time {
    color: $accent_hi; font-family: 'Consolas', 'Courier New', monospace;
    font-size: 14px; min-width: 160px; padding-left: 12px;
}
QLabel#StatusLabel { color: $text_mute; font-size: 10px; }
QLabel#StatusKey { color: $text_label; font-size: 9px; letter-spacing: 2px; }

QFrame#Card, QFrame#FileCard {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 $card_top, stop:1 $card_bot);
    border: 1px solid $border;
    border-radius: 10px;
}
QFrame#FileCard:hover { border-color: $accent; }
QFrame#DropZone {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 $drop_bg_top, stop:1 $drop_bg_bot);
    border: 2px dashed $drop_border;
    border-radius: 12px;
}
QFrame#DropZone[dragOver="true"] {
    border: 2px dashed $accent_hi;
    background: $drop_glow;
}
QLabel#DropTitle { color: $text_dim; font-size: 12px; letter-spacing: 4px; font-weight: 700; }
QLabel#DropHint { color: $text_label; font-size: 9px; letter-spacing: 2px; }

QFrame#ErrorBox {
    background: #3E1B1F; border: 1px solid #6E2C30;
    border-radius: 8px; padding: 6px 10px;
}
QLabel#ErrorText { color: #FFB4B8; font-size: 11px; }

/* === Soft brushed-metal transport buttons ===
 * Three-stop vertical gradient with a uniform single-color border (no
 * bevel highlight strips, no harsh shadow band at the bottom). The
 * pressed state simply inverts the gradient and tints the border with
 * the accent — the depth feeling comes from the AnimatedButton's drop
 * shadow shrinking on press. */
QToolButton#Ctrl {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0   $metal_high,
        stop:0.5 $metal_mid,
        stop:1   $metal_low);
    border: 1px solid $metal_high;
    color: $metal_text;
    min-width: 44px; min-height: 44px;
    border-radius: 16px;
    font-size: 17px;
    padding: 0px;
    font-family: 'Segoe UI Symbol', 'Segoe UI', sans-serif;
}
QToolButton#Ctrl:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0   $metal_edge,
        stop:0.5 $metal_high,
        stop:1   $metal_mid);
    border-color: $accent;
    color: $metal_text_hi;
}
QToolButton#Ctrl:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0   $metal_low,
        stop:0.5 $metal_mid,
        stop:1   $metal_high);
    border-color: $accent_dark;
}
QToolButton#Ctrl:disabled {
    background: $list_bg;
    border: 1px solid $border;
    color: $text_label;
}
QToolButton#Ctrl::menu-indicator { width: 0; height: 0; image: none; }

QToolButton#CtrlSmall {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0   $metal_high,
        stop:0.5 $metal_mid,
        stop:1   $metal_low);
    border: 1px solid $metal_high;
    color: $metal_text;
    min-width: 30px; max-width: 32px;
    min-height: 30px; max-height: 32px;
    border-radius: 10px;
    font-size: 13px; font-weight: 700;
    padding: 0px;
    font-family: 'Segoe UI Symbol', 'Segoe UI', sans-serif;
}
QToolButton#CtrlSmall:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0   $metal_edge,
        stop:0.5 $metal_high,
        stop:1   $metal_mid);
    border-color: $accent;
    color: $metal_text_hi;
}
QToolButton#CtrlSmall:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0   $metal_low,
        stop:0.5 $metal_mid,
        stop:1   $metal_high);
    border-color: $accent_dark;
}
QToolButton#CtrlSmall:disabled {
    background: $list_bg;
    border: 1px solid $border;
    color: $text_label;
}

/* === Primary action: soft pill play button using the accent ramp.
 * padding-left nudges the asymmetric ▶ glyph so it looks centered. */
QToolButton#PlayBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0   $accent_hi,
        stop:0.5 $accent,
        stop:1   $accent_dark);
    border: 1px solid $accent_hi;
    color: $accent_text;
    min-width: 60px; min-height: 60px;
    border-radius: 22px;
    font-size: 24px; font-weight: 700;
    font-family: 'Segoe UI Symbol', 'Segoe UI', sans-serif;
    padding-left: 4px;
}
QToolButton#PlayBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0   $accent_glow,
        stop:0.5 $accent_hi,
        stop:1   $accent);
    border-color: $accent_glow;
}
QToolButton#PlayBtn:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0   $accent_dark,
        stop:0.5 $accent,
        stop:1   $accent_hi);
    border-color: $accent;
}

QSlider::groove:horizontal {
    background: $card_top; height: 6px; border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent, stop:1 $accent_hi);
    height: 6px; border-radius: 3px;
}
QSlider::handle:horizontal {
    background: $metal_text_hi; width: 14px; height: 14px;
    margin: -5px 0; border-radius: 8px;
    border: 2px solid $accent;
}
QSlider::handle:horizontal:hover { background: $accent_glow; border-color: $accent_hi; }

/* Slim progress bar that sits right below the waveform — no draggable knob,
 * just a thin filled track that acts as the song's progress indicator. */
QSlider#Progress::groove:horizontal {
    background: $card_bot;
    height: 4px;
    border-radius: 2px;
}
QSlider#Progress::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent, stop:1 $accent_glow);
    height: 4px;
    border-radius: 2px;
}
QSlider#Progress::handle:horizontal {
    background: transparent;
    border: none;
    width: 0;
    margin: 0;
}

QListWidget {
    background: $list_bg; border: 1px solid $border; border-radius: 10px;
    color: $text_dim; font-size: 11px; outline: 0;
    padding: 4px;
}
QListWidget::item { padding: 8px 12px; border-radius: 6px; margin: 1px; }
QListWidget::item:hover { background: $list_hover; }
QListWidget::item:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $list_sel_a, stop:1 $list_sel_b);
    color: $metal_text_hi;
}

QMenu {
    background: $card_top;
    border: 1px solid $border;
    color: $text;
    padding: 5px;
    border-radius: 8px;
}
QMenu::item {
    padding: 7px 28px 7px 14px;
    border-radius: 6px;
}
QMenu::item:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $list_sel_a, stop:1 $list_sel_b);
    color: $metal_text_hi;
}
QMenu::item:checked { color: $accent_hi; }

QFrame#Divider {
    background: $border;
    border: none;
    min-height: 1px;
    max-height: 1px;
}

/* Repeat button: a property selector lights it up when in mode 1 (one) or 2 (all). */
QToolButton#Ctrl[repeatActive="true"] {
    color: $accent_hi;
    border-color: $accent;
}

QLabel#SpeedValue {
    color: $text_dim;
    font-family: 'Consolas','Courier New',monospace;
    font-size: 11px;
}
QLabel#SpeedValue:hover { color: $accent_hi; }

""")


def build_qss(theme_key: str) -> str:
    palette = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
    return _QSS_TEMPLATE.safe_substitute(palette)


def _parse_rgba(s: str) -> QColor:
    """Parse a 'rgba(r, g, b, a)' CSS-style string into a QColor."""
    inner = s[s.index("(") + 1: s.index(")")]
    parts = [int(p.strip()) for p in inner.split(",")]
    while len(parts) < 4:
        parts.append(255)
    return QColor(*parts)


class ClickableSlider(QSlider):
    """A QSlider that jumps to the click position on press (default Qt
    behavior is to step by a page; we want click-to-seek)."""
    seek_ratio = Signal(float)   # 0.0..1.0 of the slider range

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.maximum() > self.minimum():
            ratio = max(0.0, min(1.0, event.position().x() / max(1, self.width())))
            self.setValue(int(self.minimum() + ratio * (self.maximum() - self.minimum())))
            self.seek_ratio.emit(ratio)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.maximum() > self.minimum():
            ratio = max(0.0, min(1.0, event.position().x() / max(1, self.width())))
            self.setValue(int(self.minimum() + ratio * (self.maximum() - self.minimum())))
            self.seek_ratio.emit(ratio)
            event.accept()
            return
        super().mouseMoveEvent(event)


class MainWindow(QMainWindow):
    # Cross-thread delivery: the worker thread emits this when peaks finish,
    # Qt routes the call back to the GUI thread automatically.
    _peaks_ready = Signal(object, float)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PCM Player")
        self.resize(820, 760)
        self.setAcceptDrops(True)

        self.engine = AudioEngine()
        self.playlist: List[TrackInfo] = []
        self.current_index: int = -1

        self._theme_key: str = DEFAULT_THEME
        self._build_ui()
        self._connect_engine()
        self._install_shortcuts()
        self._update_ui_state()
        # Sync engine to default UI values (100% volume, 1.00x speed)
        self.engine.set_volume(self.vol_slider.value() / 100.0)
        self._speed_set(1.0)
        # Apply persisted theme (or default) from settings.json next to the .exe
        saved = _load_settings().get("theme", DEFAULT_THEME)
        self._apply_theme(saved if saved in THEMES else DEFAULT_THEME)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QWidget(); central.setObjectName("Central")
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title_box = QVBoxLayout(); title_box.setSpacing(2)
        title = QLabel("PCM PLAYER"); title.setObjectName("Title")
        sub = QLabel("RAW AUDIO DECODER"); sub.setObjectName("Subtitle")
        title_box.addWidget(title); title_box.addWidget(sub)
        header.addLayout(title_box); header.addStretch()
        self.header_badge = QLabel(""); self.header_badge.setObjectName("Badge"); self.header_badge.hide()
        self.header_size = QLabel(""); self.header_size.setObjectName("StatusLabel")
        header.addWidget(self.header_badge); header.addSpacing(8); header.addWidget(self.header_size)

        # Settings (theme picker) — gear button on the far right.
        header.addSpacing(10)
        self.btn_settings = AnimatedButton()
        self.btn_settings.setText("⚙")
        self.btn_settings.setObjectName("Ctrl")
        self.btn_settings.setToolTip("Theme")
        self.btn_settings.setPopupMode(QToolButton.InstantPopup)
        self._theme_menu = QMenu(self.btn_settings)
        self._theme_actions = {}
        theme_header = self._theme_menu.addAction("THEME")
        theme_header.setEnabled(False)
        for key, theme in THEMES.items():
            act = self._theme_menu.addAction(theme["name"])
            act.setCheckable(True)
            act.setData(key)
            act.triggered.connect(lambda checked=False, k=key: self._apply_theme(k))
            self._theme_actions[key] = act
        self._theme_menu.addSeparator()
        self._ctxmenu_action = self._theme_menu.addAction("Install in Windows right-click menu")
        self._ctxmenu_action.triggered.connect(self._toggle_context_menu)
        self._theme_menu.aboutToShow.connect(self._refresh_ctxmenu_action)
        self.btn_settings.setMenu(self._theme_menu)
        header.addWidget(self.btn_settings)
        outer.addLayout(header)

        # Drop zone (no file loaded)
        self.drop_zone = DropZone()
        self.drop_zone.files_dropped.connect(self._add_files)
        self.drop_zone.clicked.connect(self._open_files_dialog)
        outer.addWidget(self.drop_zone)

        # File card (file loaded)
        self.file_card = QFrame(); self.file_card.setObjectName("FileCard")
        fc_lay = QHBoxLayout(self.file_card); fc_lay.setContentsMargins(12, 10, 12, 10); fc_lay.setSpacing(12)
        icon = QLabel("♪"); icon.setStyleSheet("font-size:18px;color:#888;")
        text_box = QVBoxLayout(); text_box.setSpacing(2)
        self.file_name_lbl = QLabel("—"); self.file_name_lbl.setObjectName("FileName")
        self.file_meta_lbl = QLabel(""); self.file_meta_lbl.setObjectName("FileMeta")
        text_box.addWidget(self.file_name_lbl); text_box.addWidget(self.file_meta_lbl)
        change_btn = QToolButton(); change_btn.setText("⟳"); change_btn.setObjectName("Ctrl")
        change_btn.setToolTip("Open another file"); change_btn.clicked.connect(self._open_files_dialog)
        fc_lay.addWidget(icon); fc_lay.addLayout(text_box, 1); fc_lay.addWidget(change_btn)
        outer.addWidget(self.file_card)
        self.file_card.hide()

        # Error box
        self.error_box = QFrame(); self.error_box.setObjectName("ErrorBox")
        eb = QHBoxLayout(self.error_box); eb.setContentsMargins(10, 6, 10, 6)
        self.error_lbl = QLabel(""); self.error_lbl.setObjectName("ErrorText"); self.error_lbl.setWordWrap(True)
        eb.addWidget(self.error_lbl, 1)
        outer.addWidget(self.error_box); self.error_box.hide()

        # Waveform — also serves as the song-shape seek bar (click + drag).
        self.waveform = WaveformWidget()
        self.waveform.seek_requested.connect(self.engine.seek)
        outer.addWidget(self.waveform)

        # Slim progress bar directly below the waveform. Even when peaks
        # haven't been computed (or fail), this gives an unambiguous
        # "where am I in the song" indicator and supports click-to-seek
        # natively (we override mousePress to jump on click, not just drag).
        self.progress = ClickableSlider(Qt.Horizontal)
        self.progress.setObjectName("Progress")
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setFixedHeight(14)
        self.progress.seek_ratio.connect(self._on_progress_seek)
        outer.addWidget(self.progress)

        # Transport row — centered with stretches on both sides.
        controls = QHBoxLayout(); controls.setSpacing(10)

        def ctrl(text: str, tip: str) -> AnimatedButton:
            b = AnimatedButton()
            b.setText(text); b.setObjectName("Ctrl"); b.setToolTip(tip)
            return b

        def ctrl_small(text: str, tip: str) -> AnimatedButton:
            b = AnimatedButton(shadow_blur=8, shadow_offset=2)
            b.setText(text); b.setObjectName("CtrlSmall"); b.setToolTip(tip)
            return b

        self.btn_stop   = ctrl("⏹", "Stop  (Esc)")
        self.btn_prev   = ctrl("⏮", "Previous  (Ctrl+←)")
        self.btn_play   = AnimatedButton(glow=True, shadow_blur=24, shadow_offset=5)
        self.btn_play.setText("▶")
        self.btn_play.setObjectName("PlayBtn")
        self.btn_play.setToolTip("Play / Pause  (Space)")
        self.btn_next   = ctrl("⏭", "Next  (Ctrl+→)")
        self.btn_repeat = ctrl("↻", "Repeat: off")
        self._repeat_mode = 0  # 0=off, 1=one, 2=all
        self.btn_repeat.clicked.connect(self._cycle_repeat)

        self.btn_stop.clicked.connect(self.engine.stop)
        self.btn_play.clicked.connect(self.engine.toggle_play)
        self.btn_prev.clicked.connect(self.previous_track)
        self.btn_next.clicked.connect(self.next_track)

        controls.addStretch(1)
        for w in (self.btn_stop, self.btn_prev, self.btn_play, self.btn_next, self.btn_repeat):
            controls.addWidget(w)
        self.time_lbl = QLabel("0:00.00 / 0:00.00"); self.time_lbl.setObjectName("Time")
        controls.addWidget(self.time_lbl)
        controls.addStretch(1)

        outer.addLayout(controls)

        # Volume in the middle, speed compact in the far-right corner.
        sliders = QHBoxLayout(); sliders.setSpacing(6)

        self._speed: float = 1.0
        vol_lbl = QLabel("VOL"); vol_lbl.setObjectName("StatusKey")
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100); self.vol_slider.setValue(100)
        self.vol_slider.setFixedWidth(160)
        self.vol_slider.valueChanged.connect(self._on_volume)
        self.vol_pct = QLabel("100%"); self.vol_pct.setObjectName("StatusLabel"); self.vol_pct.setMinimumWidth(36)

        # Compact speed corner — small text + tiny stepper buttons, no big SPEED label.
        self.spd_pct = QLabel("1.00x"); self.spd_pct.setObjectName("SpeedValue")
        self.spd_pct.setMinimumWidth(40); self.spd_pct.setAlignment(Qt.AlignCenter)
        self.spd_pct.setToolTip("Playback speed — double-click to reset")
        self.btn_spd_minus = ctrl_small("−", "Slower (-0.05x)")
        self.btn_spd_minus.clicked.connect(lambda: self._speed_step(-0.05))
        self.btn_spd_plus  = ctrl_small("+", "Faster (+0.05x)")
        self.btn_spd_plus.clicked.connect(lambda: self._speed_step(0.05))
        self.btn_spd_reset = ctrl_small("⟲", "Reset to 1.00x")
        self.btn_spd_reset.clicked.connect(lambda: self._speed_set(1.0))
        # Allow double-clicking the value label to reset speed
        self.spd_pct.mouseDoubleClickEvent = lambda _e: self._speed_set(1.0)

        # One single, centered group: VOL slider + speed stepper sit side by
        # side with a slim divider between them. Stretches on both ends keep
        # the cluster centered when the window is wide.
        sliders.addStretch(1)
        sliders.addWidget(vol_lbl)
        sliders.addSpacing(6)
        sliders.addWidget(self.vol_slider)
        sliders.addWidget(self.vol_pct)
        sliders.addSpacing(20)
        sliders.addWidget(self.spd_pct)
        sliders.addSpacing(4)
        sliders.addWidget(self.btn_spd_minus)
        sliders.addWidget(self.btn_spd_plus)
        sliders.addSpacing(4)
        sliders.addWidget(self.btn_spd_reset)
        sliders.addStretch(1)

        outer.addLayout(sliders)

        # Status bar
        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("StatusLabel")
        self.status_lbl.setStyleSheet("padding-top:4px;")
        outer.addWidget(self.status_lbl)

        # Playlist section
        pl_label = QLabel("PLAYLIST  ·  drag files anywhere on the window  ·  double-click to play")
        pl_label.setObjectName("SectionLabel")
        pl_label.setStyleSheet("padding-top:6px;")
        outer.addWidget(pl_label)

        pl_row = QHBoxLayout()
        self.playlist_widget = QListWidget()
        self.playlist_widget.setMinimumHeight(120)
        self.playlist_widget.itemDoubleClicked.connect(self._on_playlist_dblclick)
        pl_row.addWidget(self.playlist_widget, 1)

        pl_btns = QVBoxLayout(); pl_btns.setSpacing(6)
        b_add = QToolButton(); b_add.setText("+"); b_add.setObjectName("Ctrl"); b_add.setToolTip("Add files (Ctrl+O)")
        b_rm  = QToolButton(); b_rm.setText("−");  b_rm.setObjectName("Ctrl");  b_rm.setToolTip("Remove selected")
        b_clr = QToolButton(); b_clr.setText("⌫"); b_clr.setObjectName("Ctrl"); b_clr.setToolTip("Clear playlist")
        b_add.clicked.connect(self._open_files_dialog)
        b_rm.clicked.connect(self._remove_selected)
        b_clr.clicked.connect(self._clear_playlist)
        for b in (b_add, b_rm, b_clr): pl_btns.addWidget(b)
        pl_btns.addStretch()
        pl_row.addLayout(pl_btns)

        outer.addLayout(pl_row, 1)

    # -------------------------------------------------------------- engine
    def _connect_engine(self):
        self.engine.position_changed.connect(self._on_position)
        self.engine.duration_changed.connect(self._on_duration)
        self.engine.state_changed.connect(self._on_state)
        self.engine.track_loaded.connect(self._on_track_loaded)
        self.engine.track_finished.connect(self._on_track_finished)
        self.engine.error.connect(self._on_error)
        # Worker thread → GUI thread for peaks
        self._peaks_ready.connect(self._on_peaks_ready)

    # ---------------------------------------------------------- shortcuts
    def _install_shortcuts(self):
        def sc(seq, fn):
            s = QShortcut(QKeySequence(seq), self)
            s.activated.connect(fn)
            return s
        sc("Space",        self.engine.toggle_play)
        sc("Esc",          self.engine.stop)
        sc("Right",        lambda: self.engine.seek(self.engine.position + 5))
        sc("Left",         lambda: self.engine.seek(self.engine.position - 5))
        sc("Shift+Right",  lambda: self.engine.seek(self.engine.position + 30))
        sc("Shift+Left",   lambda: self.engine.seek(self.engine.position - 30))
        sc("Ctrl+Right",   self.next_track)
        sc("Ctrl+Left",    self.previous_track)
        sc("Ctrl+O",       self._open_files_dialog)
        sc("Up",           lambda: self.vol_slider.setValue(self.vol_slider.value() + 5))
        sc("Down",         lambda: self.vol_slider.setValue(self.vol_slider.value() - 5))

    # ------------------------------------------------- drag & drop on window
    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        urls = e.mimeData().urls()
        files = [u.toLocalFile() for u in urls if u.isLocalFile()]
        if files:
            self._add_files(files)

    # -------------------------------------------------------------- actions
    def _open_files_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Open audio files",
            "",
            f"Audio files ({SUPPORTED_EXTENSIONS});;All files (*.*)"
        )
        if files:
            self._add_files(files)

    def _add_files(self, paths: List[str]):
        first_added = -1
        for p in paths:
            if not os.path.isfile(p):
                continue
            try:
                track = detect_format(p)
            except Exception as e:
                self._on_error(f"Cannot read {os.path.basename(p)}: {e}")
                continue
            self.playlist.append(track)
            item = QListWidgetItem(self._playlist_label(track))
            item.setToolTip(track.path)
            self.playlist_widget.addItem(item)
            if first_added < 0:
                first_added = len(self.playlist) - 1
        if first_added >= 0 and self.current_index < 0:
            self._load_index(first_added)
        # Refresh prev/next enable state so they wake up as soon as the playlist
        # reaches >1 item, even when files are added mid-playback.
        self._update_ui_state()

    @staticmethod
    def _playlist_label(t: TrackInfo) -> str:
        return f"{t.name}    [{t.detected_type.upper()}  {t.sample_rate}Hz  {t.channels}ch  {t.bit_depth}bit]"

    def _refresh_playlist_label(self, idx: int):
        if 0 <= idx < self.playlist_widget.count():
            self.playlist_widget.item(idx).setText(self._playlist_label(self.playlist[idx]))

    def _remove_selected(self):
        for it in self.playlist_widget.selectedItems():
            row = self.playlist_widget.row(it)
            self.playlist_widget.takeItem(row)
            del self.playlist[row]
            if row == self.current_index:
                self.engine.stop()
                self.current_index = -1
                self._update_ui_state()
            elif row < self.current_index:
                self.current_index -= 1

    def _clear_playlist(self):
        self.engine.stop()
        self.playlist.clear()
        self.playlist_widget.clear()
        self.current_index = -1
        self._update_ui_state()

    def _load_index(self, i: int):
        if not (0 <= i < len(self.playlist)):
            return
        self.current_index = i
        self.playlist_widget.setCurrentRow(i)
        self.engine.load(self.playlist[i])

    def _on_playlist_dblclick(self, item: QListWidgetItem):
        i = self.playlist_widget.row(item)
        self._load_index(i)
        self.engine.play()

    def previous_track(self):
        if not self.playlist:
            return
        i = (self.current_index - 1) if self.current_index > 0 else len(self.playlist) - 1
        was_playing = self.engine.state == "playing"
        self._load_index(i)
        if was_playing:
            self.engine.play()

    def next_track(self):
        if not self.playlist:
            return
        i = (self.current_index + 1) % len(self.playlist)
        was_playing = self.engine.state == "playing"
        self._load_index(i)
        if was_playing:
            self.engine.play()

    def _on_track_finished(self):
        # Repeat-one: replay the same track immediately.
        if self._repeat_mode == 1 and self.current_index >= 0:
            self._load_index(self.current_index)
            self.engine.play()
            return
        # Otherwise advance to the next track if there is one...
        if len(self.playlist) > 0 and self.current_index < len(self.playlist) - 1:
            self.next_track()
            self.engine.play()
            return
        # ...or, in repeat-all mode at the end of the list, jump back to track 0.
        if self._repeat_mode == 2 and self.playlist:
            self._load_index(0)
            self.engine.play()

    # ------------------------------------------------------- engine signals
    def _on_position(self, sec: float):
        self.waveform.set_position(sec)
        self.time_lbl.setText(f"{_fmt_time(sec)} / {_fmt_time(self.engine.duration)}")
        # Sync the slim progress bar (block its valueChanged path; we don't
        # need a feedback loop — it's just a passive indicator here)
        if self.engine.duration > 0:
            ratio = sec / self.engine.duration
            self.progress.blockSignals(True)
            self.progress.setValue(int(ratio * 1000))
            self.progress.blockSignals(False)

    def _on_progress_seek(self, ratio: float):
        if self.engine.duration > 0:
            self.engine.seek(ratio * self.engine.duration)

    def _on_duration(self, dur: float):
        self.time_lbl.setText(f"{_fmt_time(self.engine.position)} / {_fmt_time(dur)}")

    def _on_state(self, s: str):
        self.btn_play.setText("⏸" if s == "playing" else "▶")

    def _on_track_loaded(self, track: TrackInfo):
        self.error_box.hide()
        self.drop_zone.hide()
        self.file_card.show()
        ext = (os.path.splitext(track.name)[1].lstrip(".") or track.detected_type).upper()
        self.header_badge.setText(ext); self.header_badge.show()
        self.header_size.setText(_fmt_bytes(track.size))
        self.file_name_lbl.setText(track.name)
        self.file_meta_lbl.setText(
            f"{track.detected_type.upper()}  ·  {track.sample_rate} Hz  ·  "
            f"{track.channels} ch  ·  {track.bit_depth}-bit  ·  "
            f"{track.encoding.upper()}  ·  {track.endian.upper()}"
        )

        # Compute waveform peaks on a worker thread so the UI stays responsive.
        self.waveform.set_loading(True)
        self.waveform.set_peaks(None, 0)
        threading.Thread(target=self._compute_peaks_async, args=(self.engine.samples, track.duration), daemon=True).start()

        # Refresh playlist label and status
        self._refresh_playlist_label(self.current_index)
        self.status_lbl.setText(
            f"FILE {track.name}    SIZE {_fmt_bytes(track.size)}    "
            f"DUR {_fmt_time(track.duration)}    TYPE {track.detected_type.upper()}"
        )
        self._update_ui_state()

    def _compute_peaks_async(self, samples, duration):
        peaks = None
        try:
            if samples is not None:
                w = self.waveform.width()
                n = max(160, min(900, (w // 2) if w else 480))
                peaks = compute_peaks(samples, n)
        except Exception as e:
            _log_fatal("compute_peaks failed", e)
        # Hop back to the GUI thread via Qt's signal/slot mechanism, which
        # routes a queued call to the main thread automatically. (Earlier
        # we used QTimer.singleShot from the worker thread, but that could
        # silently fail to marshal — peaks were computed but never applied.)
        self._peaks_ready.emit(peaks, duration)

    def _on_peaks_ready(self, peaks, duration: float) -> None:
        self.waveform.set_loading(False)
        if peaks is not None:
            self.waveform.set_peaks(peaks, duration)

    def _on_error(self, msg: str):
        self.error_lbl.setText(msg)
        self.error_box.show()

    # ----------------------------------------------------------- ui helpers
    def _update_ui_state(self):
        has_track = self.engine.track is not None
        for b in (self.btn_play, self.btn_stop):
            b.setEnabled(has_track)
        for b in (self.btn_prev, self.btn_next):
            b.setEnabled(len(self.playlist) > 1)

    def _on_volume(self, v: int):
        self.engine.set_volume(v / 100.0)
        self.vol_pct.setText(f"{v}%")

    def _refresh_ctxmenu_action(self) -> None:
        """Sync the gear-menu install/uninstall label with the actual registry state."""
        if not _ctxmenu_supported():
            self._ctxmenu_action.setText("Install in Windows right-click menu")
            self._ctxmenu_action.setEnabled(False)
            self._ctxmenu_action.setToolTip("Available only in the packaged .exe build")
            return
        self._ctxmenu_action.setEnabled(True)
        self._ctxmenu_action.setToolTip("")
        if _ctxmenu_is_installed():
            self._ctxmenu_action.setText("Remove from Windows right-click menu")
        else:
            self._ctxmenu_action.setText("Install in Windows right-click menu")

    def _toggle_context_menu(self) -> None:
        if _ctxmenu_is_installed():
            ok = _ctxmenu_uninstall()
            if ok:
                QMessageBox.information(
                    self, "Right-click menu",
                    "Removed. The 'Play with PCM-Player' entry is no longer in the right-click menu."
                )
            else:
                QMessageBox.warning(self, "Right-click menu", "Could not remove the entry.")
        else:
            ok = _ctxmenu_install()
            if ok:
                QMessageBox.information(
                    self, "Right-click menu",
                    "Installed. Right-click any audio file in Explorer and choose "
                    "'Play with PCM-Player'. Selecting multiple files sends them all "
                    "as a playlist.\n\nIf you move PCMPlayer.exe to another folder, "
                    "open this dialog again to re-install with the new path."
                )
            else:
                QMessageBox.warning(
                    self, "Right-click menu",
                    "Could not write to the registry. Check that the .exe path is "
                    "writable and try again."
                )

    def _apply_theme(self, theme_key: str) -> None:
        if theme_key not in THEMES:
            theme_key = DEFAULT_THEME
        theme = THEMES[theme_key]
        self._theme_key = theme_key

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_qss(theme_key))

        # Re-skin theme-aware widgets that don't get all colors via QSS
        self.waveform.apply_theme(theme)
        self.btn_play.set_shadow_color(_parse_rgba(theme["shadow_glow"]))

        # Update menu checkmarks
        for k, act in self._theme_actions.items():
            act.setChecked(k == theme_key)

        # Persist into settings.json (portable, no registry)
        data = _load_settings()
        data["theme"] = theme_key
        _save_settings(data)

    def _speed_step(self, delta: float):
        self._speed_set(self._speed + delta)

    def _speed_set(self, v: float):
        v = max(0.50, min(2.50, round(v, 2)))
        self._speed = v
        self.engine.set_speed(v)
        self.spd_pct.setText(f"{v:.2f}x")
        self.btn_spd_minus.setEnabled(v > 0.50)
        self.btn_spd_plus.setEnabled(v < 2.50)
        self.btn_spd_reset.setEnabled(v != 1.0)

    def _cycle_repeat(self):
        self._repeat_mode = (self._repeat_mode + 1) % 3
        # Update icon, tooltip, and active visual state
        if self._repeat_mode == 0:
            self.btn_repeat.setText("↻")
            self.btn_repeat.setToolTip("Repeat: off (click for repeat one)")
            self.btn_repeat.setProperty("repeatActive", False)
        elif self._repeat_mode == 1:
            self.btn_repeat.setText("↻¹")
            self.btn_repeat.setToolTip("Repeat: one track (click for repeat all)")
            self.btn_repeat.setProperty("repeatActive", True)
        else:
            self.btn_repeat.setText("↻")
            self.btn_repeat.setToolTip("Repeat: whole playlist (click to turn off)")
            self.btn_repeat.setProperty("repeatActive", True)
        # Force QSS re-evaluation of the property selector
        self.btn_repeat.style().unpolish(self.btn_repeat)
        self.btn_repeat.style().polish(self.btn_repeat)


# ============================================================================
# Helpers
# ============================================================================

def _fmt_time(t: float) -> str:
    if t is None or t < 0 or t != t:  # NaN guard
        t = 0
    m = int(t // 60); s = int(t % 60); cs = int((t - int(t)) * 100)
    return f"{m}:{s:02d}.{cs:02d}"

def _fmt_bytes(n: int) -> str:
    if n >= 1_000_000: return f"{n/1_000_000:.2f} MB"
    if n >= 1024:      return f"{n/1024:.1f} KB"
    return f"{n} B"

# ============================================================================
# Entry point
# ============================================================================

# Single-instance plumbing: the first launch becomes the server; later launches
# (e.g. multiple Explorer right-click invocations against the same .exe) try to
# connect, hand over their argv, and exit. The receiver appends to the playlist
# and brings the existing window to front.
_SINGLE_INSTANCE_KEY = "PCMPlayer-SingleInstance-v1"


def _try_forward_argv_to_running(args) -> bool:
    """Return True if a running instance accepted the args and we should exit."""
    sock = QLocalSocket()
    sock.connectToServer(_SINGLE_INSTANCE_KEY)
    if not sock.waitForConnected(400):
        return False
    try:
        payload = json.dumps(list(args)).encode("utf-8")
        sock.write(payload)
        sock.flush()
        sock.waitForBytesWritten(800)
    finally:
        sock.disconnectFromServer()
    return True


def main():
    # Make Windows show our icon in the taskbar (otherwise it groups under python.exe).
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("br.com.tributodevido.pcmplayer")
        except Exception:
            pass

    # If another instance is already running, hand over our argv and exit.
    # This is what makes multi-select context-menu invocations land in a single
    # playlist instead of spawning many windows.
    if _try_forward_argv_to_running(sys.argv[1:]):
        return

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("PCM Player")
    app.setOrganizationName("Tributo Devido")
    # Theme stylesheet is applied by MainWindow.__init__ once it has loaded
    # the persisted theme from settings.json (portable, next to the .exe).

    icon_path = _resource_path("icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    win = MainWindow()
    win.show()

    # Start the local server that accepts argv hand-offs from later launches.
    server = QLocalServer()
    QLocalServer.removeServer(_SINGLE_INSTANCE_KEY)  # clean up any stale socket
    server.listen(_SINGLE_INSTANCE_KEY)

    def _on_new_connection():
        s = server.nextPendingConnection()
        if s is None:
            return
        if not s.waitForReadyRead(1000):
            s.disconnectFromServer()
            return
        data = bytes(s.readAll()).decode("utf-8", errors="ignore")
        s.disconnectFromServer()
        try:
            new_args = json.loads(data) if data else []
        except Exception:
            new_args = []
        win.show()
        win.raise_()
        win.activateWindow()
        new_files = _expand_args_to_files(new_args)
        if new_files:
            was_idle = win.engine.state != "playing"
            win._add_files(new_files)
            if was_idle:
                win.engine.play()

    server.newConnection.connect(_on_new_connection)

    # Accept files (and folders) passed on the command line — file-association
    # double-click, context-menu "Play with PCM-Player", drag-onto-shortcut.
    initial_files = _expand_args_to_files(sys.argv[1:])
    if initial_files:
        win._add_files(initial_files)
        win.engine.play()

    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception as _e:
        _log_fatal("main() crashed", _e)
        raise
