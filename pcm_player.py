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


import numpy as np
import sounddevice as sd
import soundfile as sf

from PySide6.QtCore import (
    QPoint, QPointF, QPropertyAnimation, QRect, QSize, Qt, QTimer, QUrl,
    Signal, QObject, QEvent, QEasingCurve,
)
from PySide6.QtGui import (
    QAction, QBrush, QColor, QDragEnterEvent, QDropEvent, QFont,
    QFontDatabase, QIcon, QKeySequence, QPainter, QPainterPath, QPen,
    QPixmap, QShortcut,
)
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGraphicsDropShadowEffect,
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPushButton, QSizePolicy, QSlider,
    QStyleFactory, QToolButton, QVBoxLayout, QWidget,
)

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
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self._peaks: Optional[np.ndarray] = None
        self._duration: float = 0.0
        self._position: float = 0.0
        self._loading = False
        self._empty_text = "NO FILE LOADED"

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

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._duration > 0 and self._peaks is not None:
            ratio = max(0.0, min(1.0, event.position().x() / max(1, self.width())))
            self.seek_requested.emit(ratio * self._duration)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        w, h = self.width(), self.height()

        # Background card with subtle vertical gradient
        from PySide6.QtGui import QLinearGradient
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor("#102542"))
        bg.setColorAt(1.0, QColor("#0B1C30"))
        p.fillRect(self.rect(), bg)
        p.setPen(QPen(QColor("#1E3A5F"), 1))
        p.drawRect(0, 0, w - 1, h - 1)

        # Centerline
        p.setPen(QPen(QColor(80, 150, 200, 40), 1))
        p.drawLine(0, h // 2, w, h // 2)

        if self._peaks is None or self._peaks.size == 0:
            p.setPen(QColor("#5C8AAB"))
            font = p.font()
            font.setPointSize(9)
            font.setLetterSpacing(QFont.PercentageSpacing, 120)
            p.setFont(font)
            text = "DECODING…" if self._loading else self._empty_text
            p.drawText(self.rect(), Qt.AlignCenter, text)
            return

        n = self._peaks.size
        bw = max(1.0, w / n)
        progress = (self._position / self._duration) if self._duration > 0 else 0.0
        progress = max(0.0, min(1.0, progress))
        px = int(progress * w)

        played_color = QColor("#29B6F6")
        unplayed_color = QColor(120, 170, 210, 60)

        for i in range(n):
            x = int(i * bw)
            bar_h = max(1, int(self._peaks[i] * h * 0.88))
            color = played_color if x < px else unplayed_color
            p.fillRect(x, (h - bar_h) // 2, max(1, int(bw - 0.5) or 1), bar_h, color)

        # Playhead
        if self._duration > 0:
            p.setPen(QPen(QColor("#80DEEA"), 2))
            p.drawLine(px, 2, px, h - 2)


class AnimatedButton(QToolButton):
    """Tool button with a soft drop shadow that retracts on press, giving the
    impression that the button physically depresses into the panel."""

    def __init__(self, parent=None, *,
                 shadow_color: QColor = QColor(0, 0, 0, 170),
                 shadow_blur: int = 18,
                 shadow_offset: int = 4,
                 glow: bool = False):
        super().__init__(parent)
        self._rest_offset = shadow_offset
        self._rest_blur = shadow_blur
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(shadow_blur)
        self._shadow.setColor(shadow_color)
        self._shadow.setOffset(0, shadow_offset)
        self.setGraphicsEffect(self._shadow)

        self._anim = QPropertyAnimation(self._shadow, b"offset", self)
        self._anim.setDuration(110)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        if glow:
            # Subtle cyan glow for the primary action button.
            self._shadow.setColor(QColor(41, 182, 246, 180))

    def _animate_to(self, target_y: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._shadow.offset())
        self._anim.setEndValue(QPointF(0, target_y))
        self._anim.start()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.isEnabled():
            self._animate_to(0)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._animate_to(self._rest_offset)
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

APP_QSS = """
QMainWindow, QWidget#Central { background: #0A1929; color: #E3F2FD; }
QLabel { color: #B0D4F1; }

QLabel#Title { color: #4FC3F7; font-weight: 700; font-size: 16px; letter-spacing: 6px; }
QLabel#Subtitle { color: #5C8AAB; font-size: 9px; letter-spacing: 4px; }
QLabel#SectionLabel { color: #5C8AAB; font-size: 9px; letter-spacing: 5px; }
QLabel#Badge {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4FC3F7, stop:1 #29B6F6);
    color: #062338; font-weight: 700;
    padding: 3px 10px; border-radius: 6px; font-size: 9px; letter-spacing: 1px;
}
QLabel#FileName { color: #ECF6FE; font-size: 13px; }
QLabel#FileMeta { color: #7AAACF; font-size: 10px; }
QLabel#Time {
    color: #4FC3F7; font-family: 'Consolas', 'Courier New', monospace;
    font-size: 14px; min-width: 160px; padding-left: 12px;
}
QLabel#StatusLabel { color: #7AAACF; font-size: 10px; }
QLabel#StatusKey { color: #5C8AAB; font-size: 9px; letter-spacing: 2px; }

QFrame#Card, QFrame#FileCard {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #15324F, stop:1 #10263F);
    border: 1px solid #1E3A5F;
    border-radius: 10px;
}
QFrame#FileCard:hover { border-color: #29B6F6; }
QFrame#DropZone {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #102542, stop:1 #0B1C30);
    border: 2px dashed #1E4870;
    border-radius: 12px;
}
QFrame#DropZone[dragOver="true"] {
    border: 2px dashed #4FC3F7;
    background: rgba(41, 182, 246, 30);
}
QLabel#DropTitle { color: #90CAF9; font-size: 12px; letter-spacing: 4px; font-weight: 700; }
QLabel#DropHint { color: #5C8AAB; font-size: 9px; letter-spacing: 2px; }

QFrame#ErrorBox {
    background: #3E1B1F; border: 1px solid #6E2C30;
    border-radius: 8px; padding: 6px 10px;
}
QLabel#ErrorText { color: #FFB4B8; font-size: 11px; }

QToolButton#Ctrl {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #2C5680, stop:0.5 #1B3D62, stop:1 #122E4D);
    border-top: 1px solid #4D7DAE;
    border-left: 1px solid #2C5680;
    border-right: 1px solid #2C5680;
    border-bottom: 1px solid #0A1A2D;
    color: #DDEEFB;
    min-width: 42px; min-height: 42px;
    border-radius: 11px;
    font-size: 17px;
    padding: 0px;
    font-family: 'Segoe UI Symbol', 'Segoe UI', sans-serif;
}
QToolButton#Ctrl:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #3B6EA6, stop:0.5 #275387, stop:1 #1A3D62);
    border-top-color: #6FA0D0;
    border-left-color: #3B6EA6;
    border-right-color: #3B6EA6;
    color: #FFFFFF;
}
QToolButton#Ctrl:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #122E4D, stop:0.5 #1B3D62, stop:1 #2C5680);
    border-top: 1px solid #0A1A2D;
    border-bottom: 1px solid #4D7DAE;
    padding-top: 1px;
}
QToolButton#Ctrl:disabled {
    background: #0F2238;
    border-top: 1px solid #1E3A5F;
    border-left: 1px solid #15314F;
    border-right: 1px solid #15314F;
    border-bottom: 1px solid #0A1A2D;
    color: #2D4A6B;
}

QToolButton#PlayBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #80DEEA, stop:0.5 #4FC3F7, stop:1 #1A8FCB);
    border-top: 1px solid #B8EFFB;
    border-left: 1px solid #4FC3F7;
    border-right: 1px solid #4FC3F7;
    border-bottom: 1px solid #015D85;
    color: #042032;
    min-width: 56px; min-height: 56px;
    border-radius: 14px;
    font-size: 22px; font-weight: 700;
    font-family: 'Segoe UI Symbol', 'Segoe UI', sans-serif;
    padding: 0px;
}
QToolButton#PlayBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #C5F2FB, stop:0.5 #80DEEA, stop:1 #29B6F6);
    border-top-color: #E1FAFF;
}
QToolButton#PlayBtn:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #1A8FCB, stop:0.5 #4FC3F7, stop:1 #80DEEA);
    border-top: 1px solid #015D85;
    border-bottom: 1px solid #B8EFFB;
    padding-top: 1px;
}

QSlider::groove:horizontal {
    background: #15324F; height: 6px; border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #29B6F6, stop:1 #4FC3F7);
    height: 6px; border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #FFFFFF; width: 14px; height: 14px;
    margin: -5px 0; border-radius: 8px;
    border: 2px solid #29B6F6;
}
QSlider::handle:horizontal:hover { background: #80DEEA; border-color: #4FC3F7; }

QListWidget {
    background: #0E2238; border: 1px solid #1E3A5F; border-radius: 10px;
    color: #B0D4F1; font-size: 11px; outline: 0;
    padding: 4px;
}
QListWidget::item { padding: 8px 12px; border-radius: 6px; margin: 1px; }
QListWidget::item:hover { background: #15324F; }
QListWidget::item:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1A4D7A, stop:1 #2C5A8F);
    color: #FFFFFF;
}

QFrame#Divider { background: #1E3A5F; max-height: 1px; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PCM Player")
        self.resize(820, 760)
        self.setAcceptDrops(True)

        self.engine = AudioEngine()
        self.playlist: List[TrackInfo] = []
        self.current_index: int = -1
        self._user_seeking = False

        self._build_ui()
        self._connect_engine()
        self._install_shortcuts()
        self._update_ui_state()
        # Sync engine to default UI values (100% volume, 1.0x speed)
        self.engine.set_volume(self.vol_slider.value() / 100.0)
        self.engine.set_speed(self.spd_slider.value() / 100.0)

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

        # Waveform
        self.waveform = WaveformWidget()
        self.waveform.seek_requested.connect(self.engine.seek)
        outer.addWidget(self.waveform)

        # Seek slider
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.setValue(0)
        self.seek_slider.sliderPressed.connect(lambda: setattr(self, "_user_seeking", True))
        self.seek_slider.sliderReleased.connect(self._on_seek_release)
        outer.addWidget(self.seek_slider)

        # Transport controls — all unicode media-control glyphs from the same family
        # for visual consistency. AnimatedButton gives them depth + press animation.
        controls = QHBoxLayout(); controls.setSpacing(10)

        def ctrl(text: str, tip: str) -> AnimatedButton:
            b = AnimatedButton()
            b.setText(text); b.setObjectName("Ctrl"); b.setToolTip(tip)
            return b

        self.btn_stop  = ctrl("⏹", "Stop  (Esc)")              # ⏹
        self.btn_back5 = ctrl("⏪", "Back 5s  (←)")        # ⏪
        self.btn_prev  = ctrl("⏮", "Previous  (Ctrl+←)")  # ⏮
        self.btn_play  = AnimatedButton(glow=True, shadow_blur=28, shadow_offset=5)
        self.btn_play.setText("▶")                              # ▶
        self.btn_play.setObjectName("PlayBtn")
        self.btn_play.setToolTip("Play / Pause  (Space)")
        self.btn_next  = ctrl("⏭", "Next  (Ctrl+→)")      # ⏭
        self.btn_fwd5  = ctrl("⏩", "Forward 5s  (→)")     # ⏩

        self.btn_stop.clicked.connect(self.engine.stop)
        self.btn_play.clicked.connect(self.engine.toggle_play)
        self.btn_prev.clicked.connect(self.previous_track)
        self.btn_next.clicked.connect(self.next_track)
        self.btn_back5.clicked.connect(lambda: self.engine.seek(self.engine.position - 5))
        self.btn_fwd5.clicked.connect(lambda: self.engine.seek(self.engine.position + 5))

        for w in (self.btn_stop, self.btn_back5, self.btn_prev, self.btn_play,
                  self.btn_next, self.btn_fwd5):
            controls.addWidget(w)

        self.time_lbl = QLabel("0:00.00 / 0:00.00"); self.time_lbl.setObjectName("Time")
        controls.addWidget(self.time_lbl)
        controls.addStretch()

        outer.addLayout(controls)

        # Speed + Volume row (sliders for fine control)
        sliders = QHBoxLayout(); sliders.setSpacing(10)
        spd_lbl = QLabel("SPEED"); spd_lbl.setObjectName("StatusKey")
        self.spd_slider = QSlider(Qt.Horizontal)
        self.spd_slider.setRange(50, 250)   # 0.50x .. 2.50x
        self.spd_slider.setValue(100)
        self.spd_slider.setFixedWidth(140)
        self.spd_slider.valueChanged.connect(self._on_speed)
        self.spd_pct = QLabel("1.00x"); self.spd_pct.setObjectName("StatusLabel"); self.spd_pct.setMinimumWidth(40)
        # Double-click on the speed slider resets to 1.0x
        self.spd_slider.mouseDoubleClickEvent = lambda _e: self.spd_slider.setValue(100)

        sliders.addWidget(spd_lbl); sliders.addWidget(self.spd_slider); sliders.addWidget(self.spd_pct)
        sliders.addStretch()

        vol_lbl = QLabel("VOL"); vol_lbl.setObjectName("StatusKey")
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100); self.vol_slider.setValue(100)
        self.vol_slider.setFixedWidth(140)
        self.vol_slider.valueChanged.connect(self._on_volume)
        self.vol_pct = QLabel("100%"); self.vol_pct.setObjectName("StatusLabel"); self.vol_pct.setMinimumWidth(40)
        sliders.addWidget(vol_lbl); sliders.addWidget(self.vol_slider); sliders.addWidget(self.vol_pct)

        outer.addLayout(sliders)

        # Divider
        d1 = QFrame(); d1.setObjectName("Divider"); d1.setFrameShape(QFrame.HLine); d1.setFixedHeight(1)
        outer.addWidget(d1)

        # Status bar
        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("StatusLabel")
        self.status_lbl.setStyleSheet("padding-top:4px;")
        outer.addWidget(self.status_lbl)

        # Playlist
        pl_label = QLabel("PLAYLIST  ·  drag files anywhere on the window  ·  double-click to play")
        pl_label.setObjectName("SectionLabel")
        outer.addWidget(pl_label)

        pl_row = QHBoxLayout()
        self.playlist_widget = QListWidget()
        self.playlist_widget.setMinimumHeight(140)
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

        outer.addStretch()

    # -------------------------------------------------------------- engine
    def _connect_engine(self):
        self.engine.position_changed.connect(self._on_position)
        self.engine.duration_changed.connect(self._on_duration)
        self.engine.state_changed.connect(self._on_state)
        self.engine.track_loaded.connect(self._on_track_loaded)
        self.engine.track_finished.connect(self._on_track_finished)
        self.engine.error.connect(self._on_error)

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
        # Auto-advance if there's a next track; otherwise stay idle.
        if len(self.playlist) > 1 and self.current_index < len(self.playlist) - 1:
            self.next_track()
            self.engine.play()

    # ------------------------------------------------------- engine signals
    def _on_position(self, sec: float):
        if self._user_seeking:
            return
        self.waveform.set_position(sec)
        self.time_lbl.setText(f"{_fmt_time(sec)} / {_fmt_time(self.engine.duration)}")
        if self.engine.duration > 0:
            ratio = sec / self.engine.duration
            self.seek_slider.blockSignals(True)
            self.seek_slider.setValue(int(ratio * 1000))
            self.seek_slider.blockSignals(False)

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
        if samples is None:
            return
        # Bigger windows = more bars; cap so we don't redraw a million bars.
        n = max(120, min(800, self.waveform.width() // 2 if self.waveform.width() else 480))
        peaks = compute_peaks(samples, n)
        # Hop back to GUI thread via signal-equivalent: QTimer.singleShot
        QTimer.singleShot(0, lambda: (self.waveform.set_loading(False),
                                      self.waveform.set_peaks(peaks, duration)))

    def _on_error(self, msg: str):
        self.error_lbl.setText(msg)
        self.error_box.show()

    # ----------------------------------------------------------- ui helpers
    def _update_ui_state(self):
        has_track = self.engine.track is not None
        for b in (self.btn_play, self.btn_stop, self.btn_back5, self.btn_fwd5):
            b.setEnabled(has_track)
        for b in (self.btn_prev, self.btn_next):
            b.setEnabled(len(self.playlist) > 1)

    def _on_volume(self, v: int):
        self.engine.set_volume(v / 100.0)
        self.vol_pct.setText(f"{v}%")

    def _on_speed(self, v: int):
        speed = v / 100.0
        self.engine.set_speed(speed)
        self.spd_pct.setText(f"{speed:.2f}x")

    def _on_seek_release(self):
        self._user_seeking = False
        if self.engine.duration <= 0:
            return
        ratio = self.seek_slider.value() / 1000.0
        self.engine.seek(ratio * self.engine.duration)


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

def main():
    # Make Windows show our icon in the taskbar (otherwise it groups under python.exe).
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("br.com.tributodevido.pcmplayer")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("PCM Player")
    app.setOrganizationName("Tributo Devido")
    app.setStyleSheet(APP_QSS)

    icon_path = _resource_path("icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    win = MainWindow()
    win.show()

    # Accept files passed on the command line
    args = sys.argv[1:]
    files = [a for a in args if os.path.isfile(a)]
    if files:
        win._add_files(files)

    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception as _e:
        _log_fatal("main() crashed", _e)
        raise
