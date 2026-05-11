package com.darthmotzkus.pcmplayer

import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Bit-depth + encoding combination for raw PCM input. */
data class RawFormat(
    val sampleRate: Int,
    val channels: Int,
    val bitDepth: Int,
    val encoding: Encoding,
    val endian: Endian,
) {
    enum class Encoding { SIGNED, UNSIGNED, FLOAT }
    enum class Endian { LE, BE }
}

/**
 * Decodes raw PCM byte streams into a small in-memory WAV byte array so they can
 * be fed to ExoPlayer like any other formatted file. This is the bridge between
 * MSU-1-style `.pcm` files and the rest of the playback chain.
 */
object PcmDecoder {

    /** Returns RawFormat defaults guessed from the filename extension. */
    fun guessFromExtension(name: String): RawFormat? {
        val ext = name.substringAfterLast('.', "").lowercase()
        return when (ext) {
            "pcm", "raw", "bin", "dat" ->
                RawFormat(44_100, 2, 16, RawFormat.Encoding.SIGNED, RawFormat.Endian.LE)
            "s8" ->
                RawFormat(44_100, 1, 8, RawFormat.Encoding.SIGNED, RawFormat.Endian.LE)
            "s16", "s16le" ->
                RawFormat(44_100, 2, 16, RawFormat.Encoding.SIGNED, RawFormat.Endian.LE)
            "s16be" ->
                RawFormat(44_100, 2, 16, RawFormat.Encoding.SIGNED, RawFormat.Endian.BE)
            "s24", "s24le" ->
                RawFormat(44_100, 2, 24, RawFormat.Encoding.SIGNED, RawFormat.Endian.LE)
            "s24be" ->
                RawFormat(44_100, 2, 24, RawFormat.Encoding.SIGNED, RawFormat.Endian.BE)
            "s32", "s32le" ->
                RawFormat(44_100, 2, 32, RawFormat.Encoding.SIGNED, RawFormat.Endian.LE)
            "s32be" ->
                RawFormat(44_100, 2, 32, RawFormat.Encoding.SIGNED, RawFormat.Endian.BE)
            "u8" ->
                RawFormat(44_100, 1, 8, RawFormat.Encoding.UNSIGNED, RawFormat.Endian.LE)
            "f32", "f32le" ->
                RawFormat(44_100, 2, 32, RawFormat.Encoding.FLOAT, RawFormat.Endian.LE)
            "f32be" ->
                RawFormat(44_100, 2, 32, RawFormat.Encoding.FLOAT, RawFormat.Endian.BE)
            "f64" ->
                RawFormat(44_100, 2, 64, RawFormat.Encoding.FLOAT, RawFormat.Endian.LE)
            else -> null
        }
    }

    /**
     * Decode `raw` according to `fmt` to a (frames * channels) float array
     * in interleaved order, range roughly [-1, 1]. Used both for waveform peaks
     * and (after quantization) for the WAV body.
     */
    fun decodeToFloat(raw: ByteArray, fmt: RawFormat): FloatArray {
        val order = if (fmt.endian == RawFormat.Endian.LE) ByteOrder.LITTLE_ENDIAN else ByteOrder.BIG_ENDIAN
        val buf = ByteBuffer.wrap(raw).order(order)
        return when (fmt.encoding) {
            RawFormat.Encoding.SIGNED -> when (fmt.bitDepth) {
                8 -> FloatArray(raw.size) { raw[it].toFloat() / 128f }
                16 -> {
                    val n = raw.size / 2
                    FloatArray(n) { buf.short.toFloat() / 32_768f }
                }
                24 -> decode24Signed(raw, fmt.endian)
                32 -> {
                    val n = raw.size / 4
                    FloatArray(n) { buf.int.toFloat() / 2_147_483_648f }
                }
                else -> throw IllegalArgumentException("Unsupported signed bit depth: ${fmt.bitDepth}")
            }
            RawFormat.Encoding.UNSIGNED -> when (fmt.bitDepth) {
                8 -> FloatArray(raw.size) { ((raw[it].toInt() and 0xFF) - 128).toFloat() / 128f }
                16 -> {
                    val n = raw.size / 2
                    FloatArray(n) { ((buf.short.toInt() and 0xFFFF) - 32_768).toFloat() / 32_768f }
                }
                else -> throw IllegalArgumentException("Unsupported unsigned bit depth: ${fmt.bitDepth}")
            }
            RawFormat.Encoding.FLOAT -> when (fmt.bitDepth) {
                32 -> {
                    val n = raw.size / 4
                    FloatArray(n) { buf.float }
                }
                64 -> {
                    val n = raw.size / 8
                    FloatArray(n) { buf.double.toFloat() }
                }
                else -> throw IllegalArgumentException("Unsupported float bit depth: ${fmt.bitDepth}")
            }
        }
    }

    private fun decode24Signed(raw: ByteArray, endian: RawFormat.Endian): FloatArray {
        val n = raw.size / 3
        val out = FloatArray(n)
        for (i in 0 until n) {
            val o = i * 3
            val v: Int = if (endian == RawFormat.Endian.LE) {
                (raw[o].toInt() and 0xFF) or
                    ((raw[o + 1].toInt() and 0xFF) shl 8) or
                    ((raw[o + 2].toInt()) shl 16)        // keep sign in MSB
            } else {
                (raw[o + 2].toInt() and 0xFF) or
                    ((raw[o + 1].toInt() and 0xFF) shl 8) or
                    ((raw[o].toInt()) shl 16)
            }
            out[i] = v.toFloat() / 8_388_608f
        }
        return out
    }

    /** Wrap PCM samples (Float in [-1,1]) into a minimal RIFF/WAVE (16-bit) container. */
    fun wrapAsWav(samples: FloatArray, sampleRate: Int, channels: Int): ByteArray {
        // Quantize to little-endian signed 16-bit
        val dataBytes = ByteArray(samples.size * 2)
        val bb = ByteBuffer.wrap(dataBytes).order(ByteOrder.LITTLE_ENDIAN)
        for (s in samples) {
            val v = (s.coerceIn(-1f, 1f) * 32_767f).toInt()
            bb.putShort(v.toShort())
        }
        return buildWavHeader(dataBytes.size, sampleRate, channels) + dataBytes
    }

    private fun buildWavHeader(dataSize: Int, sampleRate: Int, channels: Int): ByteArray {
        val baos = ByteArrayOutputStream(44)
        val dos = DataOutputStream(baos)
        val byteRate = sampleRate * channels * 2
        val blockAlign = channels * 2

        dos.writeBytes("RIFF")
        dos.writeIntLE(36 + dataSize)        // chunk size
        dos.writeBytes("WAVE")
        dos.writeBytes("fmt ")
        dos.writeIntLE(16)                   // subchunk1 size (PCM)
        dos.writeShortLE(1)                  // audio format = PCM
        dos.writeShortLE(channels)
        dos.writeIntLE(sampleRate)
        dos.writeIntLE(byteRate)
        dos.writeShortLE(blockAlign)
        dos.writeShortLE(16)                 // bits per sample
        dos.writeBytes("data")
        dos.writeIntLE(dataSize)
        return baos.toByteArray()
    }

    private fun DataOutputStream.writeIntLE(v: Int) {
        write(v and 0xFF); write((v ushr 8) and 0xFF)
        write((v ushr 16) and 0xFF); write((v ushr 24) and 0xFF)
    }
    private fun DataOutputStream.writeShortLE(v: Int) {
        write(v and 0xFF); write((v ushr 8) and 0xFF)
    }

    /** Down-sample peak values from a float array for the waveform display. */
    fun computePeaks(samples: FloatArray, channels: Int, buckets: Int = 480): FloatArray {
        if (samples.isEmpty() || buckets <= 0) return FloatArray(maxOf(1, buckets))
        // Quick mono mix using channel stride
        val frames = samples.size / maxOf(1, channels)
        val mono = FloatArray(frames)
        for (i in 0 until frames) {
            var acc = 0f
            for (c in 0 until channels) acc += samples[i * channels + c]
            mono[i] = acc / channels
        }
        val bucket = maxOf(1, frames / buckets)
        val out = FloatArray(buckets)
        var max = 0f
        for (b in 0 until buckets) {
            val start = b * bucket
            val end = minOf(frames, start + bucket)
            var m = 0f
            for (i in start until end) {
                val a = if (mono[i] < 0) -mono[i] else mono[i]
                if (a > m) m = a
            }
            out[b] = m
            if (m > max) max = m
        }
        if (max > 1e-9f) for (i in out.indices) out[i] = out[i] / max
        return out
    }
}
