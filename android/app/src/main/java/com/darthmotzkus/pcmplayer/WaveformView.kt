package com.darthmotzkus.pcmplayer

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * Lightweight waveform display.
 * - Renders precomputed peaks (one float per "bucket") as paired top/bottom bars.
 * - Click or drag to seek; emits a fractional position [0..1] via [onSeek].
 */
class WaveformView @JvmOverloads constructor(
    context: Context, attrs: AttributeSet? = null, defStyle: Int = 0
) : View(context, attrs, defStyle) {

    private val playedPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#EF9F27") }
    private val unplayedPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#5A5A5A") }
    private val centerLinePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#22FFFFFF"); strokeWidth = 1f
    }
    private val playheadPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#FAC775"); strokeWidth = 4f
    }
    private val placeholderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#666666"); textSize = 28f; textAlign = Paint.Align.CENTER
    }

    private var peaks: FloatArray? = null
    /** Synthetic peaks shown for formatted files where we don't decode samples. */
    private var placeholderMode = false
    private var progressFraction: Float = 0f
    var onSeek: ((Float) -> Unit)? = null

    fun setAccentColors(played: Int, playhead: Int) {
        playedPaint.color = played
        playheadPaint.color = playhead
        invalidate()
    }

    fun showPeaks(p: FloatArray) {
        peaks = p
        placeholderMode = false
        invalidate()
    }

    fun showPlaceholder(buckets: Int = 320) {
        // Sine-shaped envelope so the bar still looks like a waveform; cosmetic only.
        val fake = FloatArray(buckets) { i ->
            val t = i.toFloat() / buckets
            val env = 0.25f + 0.6f * kotlin.math.sin(t * Math.PI.toFloat() * 6f).let { if (it < 0) -it else it }
            env.coerceIn(0.08f, 0.95f)
        }
        peaks = fake
        placeholderMode = true
        invalidate()
    }

    fun clear() {
        peaks = null
        placeholderMode = false
        progressFraction = 0f
        invalidate()
    }

    fun setProgressFraction(f: Float) {
        progressFraction = f.coerceIn(0f, 1f)
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        val w = width
        val h = height
        canvas.drawColor(Color.parseColor("#11000000"))
        canvas.drawLine(0f, h / 2f, w.toFloat(), h / 2f, centerLinePaint)

        val p = peaks
        if (p == null || p.isEmpty()) {
            canvas.drawText("NO TRACK LOADED", w / 2f, h / 2f + 10f, placeholderPaint)
            return
        }

        val n = p.size
        val barW = max(1f, w.toFloat() / n)
        val playX = (progressFraction * w).roundToInt()
        val mid = h / 2f
        val maxAmp = h * 0.42f

        for (i in 0 until n) {
            val x = i * barW
            val amp = p[i] * maxAmp
            val paint = if (x < playX) playedPaint else unplayedPaint
            val rect = RectF(x, mid - amp, x + barW * 0.85f, mid + amp)
            canvas.drawRoundRect(rect, 1.5f, 1.5f, paint)
        }

        // Playhead
        canvas.drawLine(playX.toFloat(), 6f, playX.toFloat(), (h - 6).toFloat(), playheadPaint)
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (peaks == null) return false
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN,
            MotionEvent.ACTION_MOVE,
            MotionEvent.ACTION_UP -> {
                val f = (event.x / max(1, width)).coerceIn(0f, 1f)
                progressFraction = f
                invalidate()
                onSeek?.invoke(f)
                return true
            }
        }
        return super.onTouchEvent(event)
    }
}
