package com.darthmotzkus.pcmplayer

import android.content.Context
import android.net.Uri
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackParameters
import androidx.media3.common.Player
import androidx.media3.datasource.ByteArrayDataSource
import androidx.media3.datasource.DataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.ProgressiveMediaSource

/**
 * Wraps ExoPlayer (AndroidX Media3). Two playback paths:
 *
 *  1) **Formatted files** (WAV/FLAC/MP3/OGG/etc.) → fed directly by Uri.
 *  2) **Raw PCM files** (.pcm/.raw/.s16/…) → bytes are read off the ContentResolver,
 *     decoded with [PcmDecoder], wrapped in a tiny WAV header in memory, and replayed
 *     through ExoPlayer via [ByteArrayDataSource]. Same engine, same seeking/speed
 *     primitives — the WAV wrapper is just a portable carrier.
 */
class AudioEngine(private val context: Context) {

    val player: ExoPlayer = ExoPlayer.Builder(context).build()

    enum class RepeatMode { OFF, ONE, ALL }

    var listener: Listener? = null

    var repeatMode: RepeatMode = RepeatMode.OFF
        set(v) {
            field = v
            player.repeatMode = when (v) {
                RepeatMode.OFF -> Player.REPEAT_MODE_OFF
                RepeatMode.ONE -> Player.REPEAT_MODE_ONE
                RepeatMode.ALL -> Player.REPEAT_MODE_OFF // playlist auto-advance handles "all"
            }
            listener?.onRepeatModeChanged(v)
        }

    var playbackSpeed: Float = 1.0f
        set(v) {
            val clamped = v.coerceIn(0.5f, 2.5f)
            field = clamped
            player.playbackParameters = PlaybackParameters(clamped)
            listener?.onSpeedChanged(clamped)
        }

    init {
        player.addListener(object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) {
                listener?.onStateChanged(state)
            }
            override fun onIsPlayingChanged(isPlaying: Boolean) {
                listener?.onIsPlayingChanged(isPlaying)
            }
            override fun onPlayerError(error: androidx.media3.common.PlaybackException) {
                listener?.onError(error.message ?: error.localizedMessage ?: "Playback error")
            }
        })
    }

    /** Load a formatted file (lets ExoPlayer choose its extractor based on the Uri). */
    fun loadFormatted(uri: Uri, autoPlay: Boolean) {
        player.setMediaItem(MediaItem.fromUri(uri))
        player.prepare()
        player.playWhenReady = autoPlay
    }

    /** Load raw PCM bytes that were already decoded and wrapped into a WAV byte array. */
    fun loadInMemoryWav(wavBytes: ByteArray, displayUri: Uri, autoPlay: Boolean) {
        val dataSourceFactory = DataSource.Factory { ByteArrayDataSource(wavBytes) }
        val source = ProgressiveMediaSource.Factory(dataSourceFactory)
            .createMediaSource(MediaItem.fromUri(displayUri))
        player.setMediaSource(source)
        player.prepare()
        player.playWhenReady = autoPlay
    }

    fun play() { if (player.playbackState == Player.STATE_ENDED) player.seekTo(0); player.play() }
    fun pause() = player.pause()
    fun stop() { player.pause(); player.seekTo(0) }
    fun togglePlay() { if (player.isPlaying) player.pause() else play() }
    fun seekTo(positionMs: Long) = player.seekTo(positionMs)
    fun seekFraction(f: Float) {
        val dur = player.duration
        if (dur > 0 && dur != C.TIME_UNSET) {
            player.seekTo((dur * f.coerceIn(0f, 1f)).toLong())
        }
    }

    fun position(): Long = player.currentPosition.coerceAtLeast(0)
    fun duration(): Long = player.duration.let { if (it == C.TIME_UNSET) 0 else it }
    fun isPlaying(): Boolean = player.isPlaying

    fun release() = player.release()

    interface Listener {
        fun onStateChanged(state: Int) {}
        fun onIsPlayingChanged(isPlaying: Boolean) {}
        fun onError(message: String) {}
        fun onSpeedChanged(speed: Float) {}
        fun onRepeatModeChanged(mode: RepeatMode) {}
    }
}
