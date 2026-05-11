package com.darthmotzkus.pcmplayer

import android.content.ContentResolver
import android.content.Intent
import android.graphics.Color
import android.graphics.PorterDuff
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.OpenableColumns
import android.view.Gravity
import android.view.View
import android.widget.PopupMenu
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.Player
import androidx.recyclerview.widget.LinearLayoutManager
import com.darthmotzkus.pcmplayer.databinding.ActivityMainBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var engine: AudioEngine

    private val playlist = mutableListOf<Track>()
    private var currentIndex = -1
    private lateinit var adapter: PlaylistAdapter

    private val handler = Handler(Looper.getMainLooper())
    private val tickRunnable = object : Runnable {
        override fun run() {
            refreshPosition()
            handler.postDelayed(this, 33)
        }
    }

    private val pickFiles = registerForActivityResult(
        ActivityResultContracts.OpenMultipleDocuments()
    ) { uris ->
        if (uris.isNotEmpty()) {
            uris.forEach { uri ->
                try { contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION) } catch (_: Exception) {}
            }
            addUris(uris, autoPlay = currentIndex < 0)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        engine = AudioEngine(this)
        engine.listener = object : AudioEngine.Listener {
            override fun onIsPlayingChanged(isPlaying: Boolean) {
                binding.btnPlay.setImageResource(
                    if (isPlaying) R.drawable.ic_pause else R.drawable.ic_play
                )
            }
            override fun onStateChanged(state: Int) {
                if (state == Player.STATE_ENDED) {
                    when (engine.repeatMode) {
                        AudioEngine.RepeatMode.ONE -> { engine.seekTo(0); engine.play() }
                        AudioEngine.RepeatMode.ALL -> nextTrack()
                        AudioEngine.RepeatMode.OFF -> if (currentIndex < playlist.lastIndex) nextTrack()
                    }
                }
            }
            override fun onError(message: String) { showStatus("Error: $message") }
            override fun onSpeedChanged(speed: Float) {
                binding.tvSpeed.text = "%.2fx".format(speed)
            }
            override fun onRepeatModeChanged(mode: AudioEngine.RepeatMode) {
                binding.btnRepeat.setImageResource(when (mode) {
                    AudioEngine.RepeatMode.OFF -> R.drawable.ic_repeat_off
                    AudioEngine.RepeatMode.ONE -> R.drawable.ic_repeat_one
                    AudioEngine.RepeatMode.ALL -> R.drawable.ic_repeat_all
                })
            }
        }

        setupUi()
        applyTheme(ThemeManager.current(this), redrawWaveColors = true)
        handlePotentialIncomingIntent(intent)
        handler.post(tickRunnable)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handlePotentialIncomingIntent(intent)
    }

    override fun onDestroy() {
        handler.removeCallbacks(tickRunnable)
        engine.release()
        super.onDestroy()
    }

    // ----------------------------------------------------- UI wiring

    private fun setupUi() {
        adapter = PlaylistAdapter(
            playlist,
            onPlay = { idx -> loadIndex(idx, autoPlay = true) },
            onRemove = { idx -> removeTrack(idx) },
        )
        binding.rvPlaylist.layoutManager = LinearLayoutManager(this)
        binding.rvPlaylist.adapter = adapter

        binding.btnPlay.setOnClickListener { engine.togglePlay() }
        binding.btnStop.setOnClickListener { engine.stop() }
        binding.btnPrev.setOnClickListener { previousTrack() }
        binding.btnNext.setOnClickListener { nextTrack() }
        binding.btnRepeat.setOnClickListener {
            engine.repeatMode = when (engine.repeatMode) {
                AudioEngine.RepeatMode.OFF -> AudioEngine.RepeatMode.ONE
                AudioEngine.RepeatMode.ONE -> AudioEngine.RepeatMode.ALL
                AudioEngine.RepeatMode.ALL -> AudioEngine.RepeatMode.OFF
            }
        }

        binding.btnSpeedDown.setOnClickListener { engine.playbackSpeed = engine.playbackSpeed - 0.05f }
        binding.btnSpeedUp.setOnClickListener   { engine.playbackSpeed = engine.playbackSpeed + 0.05f }
        binding.tvSpeed.setOnClickListener      { engine.playbackSpeed = 1.0f }

        binding.btnOpen.setOnClickListener {
            pickFiles.launch(arrayOf(
                "audio/*", "application/octet-stream",
                "*/*" // fallback so users can pick .pcm files which some pickers tag as unknown
            ))
        }

        binding.btnClearPlaylist.setOnClickListener { clearPlaylist() }
        binding.btnTheme.setOnClickListener(::showThemeMenu)

        binding.waveform.onSeek = { f -> engine.seekFraction(f) }
    }

    private fun showThemeMenu(anchor: View) {
        val menu = PopupMenu(this, anchor, Gravity.END)
        AppTheme.entries.forEach { t ->
            menu.menu.add(0, t.ordinal, t.ordinal, "${if (ThemeManager.current(this) == t) "✓ " else "   "}${t.displayName}")
        }
        menu.setOnMenuItemClickListener { item ->
            val theme = AppTheme.entries[item.itemId]
            ThemeManager.set(this, theme)
            applyTheme(theme, redrawWaveColors = true)
            true
        }
        menu.show()
    }

    private fun applyTheme(theme: AppTheme, redrawWaveColors: Boolean) {
        // Background tint
        binding.root.setBackgroundColor(theme.background)
        binding.cardCurrent.background = roundedBg(theme.surface, theme.border)
        binding.cardControls.background = roundedBg(theme.surface, theme.border)
        binding.cardWaveform.background = roundedBg(theme.surface, theme.border)
        binding.cardPlaylist.background = roundedBg(theme.surface, theme.border)

        binding.tvTitle.setTextColor(theme.primary)
        binding.btnTheme.setColorFilter(theme.primary, PorterDuff.Mode.SRC_IN)

        // Tint transport buttons
        intArrayOf(
            R.id.btn_prev, R.id.btn_stop, R.id.btn_next, R.id.btn_repeat,
            R.id.btn_speed_down, R.id.btn_speed_up, R.id.btn_open, R.id.btn_clear_playlist
        ).forEach {
            findViewById<View>(it)?.let { v ->
                if (v is android.widget.ImageButton) {
                    v.setColorFilter(theme.primaryLight, PorterDuff.Mode.SRC_IN)
                }
            }
        }
        binding.btnPlay.setColorFilter(theme.primary, PorterDuff.Mode.SRC_IN)
        binding.tvSpeed.setTextColor(theme.primaryLight)
        binding.tvTime.setTextColor(theme.primaryLight)

        if (redrawWaveColors) {
            binding.waveform.setAccentColors(theme.primary, theme.primaryLight)
        }
        adapter.setAccent(theme.primary)
    }

    private fun roundedBg(fill: Int, stroke: Int): GradientDrawable =
        GradientDrawable().apply {
            cornerRadius = 18f
            setColor(fill)
            setStroke(1, stroke)
        }

    // ----------------------------------------------------- Playlist ops

    private fun handlePotentialIncomingIntent(intent: Intent?) {
        intent ?: return
        val uris = mutableListOf<Uri>()
        when (intent.action) {
            Intent.ACTION_VIEW -> intent.data?.let { uris.add(it) }
            Intent.ACTION_SEND -> {
                @Suppress("DEPRECATION")
                intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM)?.let { uris.add(it) }
            }
            Intent.ACTION_SEND_MULTIPLE -> {
                @Suppress("DEPRECATION")
                intent.getParcelableArrayListExtra<Uri>(Intent.EXTRA_STREAM)?.let { uris.addAll(it) }
            }
        }
        if (uris.isNotEmpty()) addUris(uris, autoPlay = true)
    }

    private fun addUris(uris: List<Uri>, autoPlay: Boolean) {
        val firstNew = playlist.size
        for (u in uris) {
            val track = describeUri(u) ?: continue
            playlist.add(track)
            adapter.notifyItemInserted(playlist.size - 1)
        }
        if (playlist.isNotEmpty() && currentIndex < 0) {
            loadIndex(firstNew.coerceAtMost(playlist.lastIndex), autoPlay)
        }
        binding.tvHint.visibility = if (playlist.isEmpty()) View.VISIBLE else View.GONE
    }

    private fun describeUri(uri: Uri): Track? {
        var displayName = uri.lastPathSegment ?: "unknown"
        var size = 0L
        try {
            contentResolver.query(uri, null, null, null, null)?.use { c ->
                if (c.moveToFirst()) {
                    val ni = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    val si = c.getColumnIndex(OpenableColumns.SIZE)
                    if (ni >= 0) displayName = c.getString(ni) ?: displayName
                    if (si >= 0) size = c.getLong(si)
                }
            }
        } catch (_: Exception) { /* ignore */ }

        val ext = displayName.substringAfterLast('.', "").lowercase()
        val raw = PcmDecoder.guessFromExtension(displayName)
        val detected = when {
            raw != null -> "PCM"
            ext.isNotEmpty() -> ext
            else -> "audio"
        }
        return Track(uri, displayName, size, detected, raw)
    }

    private fun loadIndex(idx: Int, autoPlay: Boolean) {
        if (idx !in playlist.indices) return
        currentIndex = idx
        adapter.setActiveIndex(idx)
        val t = playlist[idx]
        binding.tvCurrentName.text = t.displayName
        binding.tvCurrentMeta.text = "${t.detectedType.uppercase()}"

        if (t.rawFormat != null) {
            // Raw PCM: read bytes, decode, re-wrap as WAV in memory, hand to ExoPlayer
            binding.waveform.clear()
            lifecycleScope.launch {
                try {
                    val (wav, peaks) = withContext(Dispatchers.IO) {
                        val bytes = readAllBytes(contentResolver, t.uri)
                        val floats = PcmDecoder.decodeToFloat(bytes, t.rawFormat)
                        val wav = PcmDecoder.wrapAsWav(floats, t.rawFormat.sampleRate, t.rawFormat.channels)
                        val peaks = PcmDecoder.computePeaks(floats, t.rawFormat.channels)
                        wav to peaks
                    }
                    engine.loadInMemoryWav(wav, t.uri, autoPlay)
                    binding.waveform.showPeaks(peaks)
                    binding.tvCurrentMeta.text =
                        "PCM  ·  ${t.rawFormat.sampleRate} Hz  ·  ${t.rawFormat.channels}ch  ·  ${t.rawFormat.bitDepth}-bit"
                } catch (e: Exception) {
                    showStatus("Failed to decode PCM: ${e.message}")
                }
            }
        } else {
            // Formatted: let ExoPlayer handle it. Waveform shows a placeholder.
            engine.loadFormatted(t.uri, autoPlay)
            binding.waveform.showPlaceholder()
        }
    }

    private fun removeTrack(idx: Int) {
        if (idx !in playlist.indices) return
        playlist.removeAt(idx)
        adapter.notifyItemRemoved(idx)
        if (idx == currentIndex) {
            engine.stop()
            currentIndex = -1
            binding.tvCurrentName.text = "—"
            binding.tvCurrentMeta.text = ""
            binding.waveform.clear()
        } else if (idx < currentIndex) {
            currentIndex--
            adapter.setActiveIndex(currentIndex)
        }
        binding.tvHint.visibility = if (playlist.isEmpty()) View.VISIBLE else View.GONE
    }

    private fun clearPlaylist() {
        engine.stop()
        val n = playlist.size
        playlist.clear()
        adapter.notifyItemRangeRemoved(0, n)
        currentIndex = -1
        binding.tvCurrentName.text = "—"
        binding.tvCurrentMeta.text = ""
        binding.waveform.clear()
        binding.tvHint.visibility = View.VISIBLE
    }

    private fun previousTrack() {
        if (playlist.isEmpty()) return
        val next = if (currentIndex > 0) currentIndex - 1 else playlist.lastIndex
        loadIndex(next, autoPlay = true)
    }

    private fun nextTrack() {
        if (playlist.isEmpty()) return
        val next = if (currentIndex < playlist.lastIndex) currentIndex + 1 else 0
        loadIndex(next, autoPlay = true)
    }

    // ----------------------------------------------------- Helpers

    private fun refreshPosition() {
        val pos = engine.position()
        val dur = engine.duration()
        binding.tvTime.text = "${fmtTime(pos)} / ${fmtTime(dur)}"
        if (dur > 0) binding.waveform.setProgressFraction(pos.toFloat() / dur.toFloat())
    }

    private fun fmtTime(ms: Long): String {
        if (ms < 0) return "0:00"
        val s = ms / 1000
        return "%d:%02d".format(s / 60, s % 60)
    }

    private fun showStatus(msg: String) {
        binding.tvCurrentMeta.text = msg
    }

    private fun readAllBytes(cr: ContentResolver, uri: Uri): ByteArray {
        cr.openInputStream(uri).use { input ->
            requireNotNull(input) { "Cannot open $uri" }
            return input.readBytes()
        }
    }
}
