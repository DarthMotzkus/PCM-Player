package com.darthmotzkus.pcmplayer

import android.net.Uri

/** Lightweight description of a track in the playlist. */
data class Track(
    val uri: Uri,
    val displayName: String,
    val size: Long,
    /** Detected format ("WAV", "FLAC", "MP3", "PCM", …) shown in the UI. */
    val detectedType: String,
    /** If this is a raw PCM file, the decoder parameters guessed from the extension. */
    val rawFormat: RawFormat? = null,
)
