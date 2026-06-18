package com.jarvis.glasses.audio

import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Conversión entre PCM16 mono y contenedor WAV (RIFF/WAVE).
 */
object WavUtil {

    private const val HEADER_SIZE = 44

    /**
     * Empaqueta muestras PCM16 mono en un WAV con cabecera RIFF/WAVE.
     */
    fun pcm16ToWav(pcm: ShortArray, sampleRate: Int = 16000): ByteArray {
        val channels = 1
        val bitsPerSample = 16
        val byteRate = sampleRate * channels * bitsPerSample / 8
        val blockAlign = channels * bitsPerSample / 8
        val dataSize = pcm.size * 2
        val totalSize = HEADER_SIZE + dataSize

        val buffer = ByteBuffer.allocate(totalSize).order(ByteOrder.LITTLE_ENDIAN)

        // Cabecera RIFF
        buffer.put("RIFF".toByteArray(Charsets.US_ASCII))
        buffer.putInt(totalSize - 8)              // tamaño del chunk = total - 8
        buffer.put("WAVE".toByteArray(Charsets.US_ASCII))

        // Subchunk "fmt "
        buffer.put("fmt ".toByteArray(Charsets.US_ASCII))
        buffer.putInt(16)                         // tamaño del subchunk fmt para PCM
        buffer.putShort(1)                        // formato 1 = PCM sin comprimir
        buffer.putShort(channels.toShort())
        buffer.putInt(sampleRate)
        buffer.putInt(byteRate)
        buffer.putShort(blockAlign.toShort())
        buffer.putShort(bitsPerSample.toShort())

        // Subchunk "data"
        buffer.put("data".toByteArray(Charsets.US_ASCII))
        buffer.putInt(dataSize)
        for (sample in pcm) {
            buffer.putShort(sample)
        }

        return buffer.array()
    }

    /**
     * Extrae las muestras PCM16 del bloque "data" de un WAV.
     * Busca el chunk "data" en vez de asumir cabecera fija de 44 bytes.
     */
    fun wavToPcm16(wav: ByteArray): ShortArray {
        val buffer = ByteBuffer.wrap(wav).order(ByteOrder.LITTLE_ENDIAN)

        // Localiza el offset y tamaño del chunk "data".
        var offset = 12 // tras "RIFF" + tamaño + "WAVE"
        var dataOffset = -1
        var dataSize = 0
        while (offset + 8 <= wav.size) {
            val id = String(wav, offset, 4, Charsets.US_ASCII)
            val size = buffer.getInt(offset + 4)
            if (id == "data") {
                dataOffset = offset + 8
                dataSize = size
                break
            }
            // Los chunks se alinean a tamaño par.
            offset += 8 + size + (size and 1)
        }

        if (dataOffset < 0) {
            // Sin chunk "data" reconocible: caemos a la cabecera estándar de 44 bytes.
            dataOffset = HEADER_SIZE
            dataSize = wav.size - HEADER_SIZE
        }
        // Acota a lo realmente presente en el array.
        if (dataOffset + dataSize > wav.size) {
            dataSize = wav.size - dataOffset
        }
        if (dataSize <= 0) return ShortArray(0)

        val sampleCount = dataSize / 2
        val pcm = ShortArray(sampleCount)
        val data = ByteBuffer.wrap(wav, dataOffset, dataSize).order(ByteOrder.LITTLE_ENDIAN)
        for (i in 0 until sampleCount) {
            pcm[i] = data.short
        }
        return pcm
    }
}
