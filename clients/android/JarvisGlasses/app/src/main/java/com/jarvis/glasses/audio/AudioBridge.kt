package com.jarvis.glasses.audio

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioAttributes
import android.media.AudioDeviceInfo
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.os.Build
import com.jarvis.glasses.audio.WavUtil
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

/**
 * Puente de audio con las gafas Bluetooth.
 *
 * - Captura: rutea la entrada al micro de las gafas (TYPE_BLE_HEADSET o
 *   TYPE_BLUETOOTH_SCO) vía AudioManager.setCommunicationDevice() en API 31+,
 *   o startBluetoothSco() como fallback en API < 31. AudioRecord en modo
 *   VOICE_COMMUNICATION 16 kHz mono PCM16, entregando frames de 1280 muestras.
 * - Reproducción: AudioTrack por la salida activa (las gafas), decodificando
 *   el WAV con WavUtil.
 */
class AudioBridge(private val ctx: Context) {

    companion object {
        const val SAMPLE_RATE = 16000
        const val FRAME_SAMPLES = 1280 // 80 ms @16kHz
    }

    private val audioManager =
        ctx.getSystemService(Context.AUDIO_SERVICE) as AudioManager

    private var record: AudioRecord? = null
    private var captureThread: Thread? = null
    private val capturing = AtomicBoolean(false)

    private var track: AudioTrack? = null

    /** true si la entrada quedó enrutada a un dispositivo Bluetooth (gafas). */
    @Volatile
    var micRoutedToGlasses: Boolean = false
        private set

    /**
     * Arranca la captura del micro de las gafas. Entrega frames de 1280
     * muestras int16 al callback desde un hilo dedicado.
     */
    @SuppressLint("MissingPermission")
    fun startMic(onFrame: (ShortArray) -> Unit) {
        if (capturing.get()) return

        // Modo de comunicación: necesario para enrutar a SCO/BLE.
        audioManager.mode = AudioManager.MODE_IN_COMMUNICATION

        micRoutedToGlasses = routeInputToGlasses()

        val minBuf = AudioRecord.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )
        // Buffer holgado: varios frames para evitar overruns.
        val bufSize = maxOf(minBuf, FRAME_SAMPLES * 2 * 8)

        val rec = AudioRecord(
            MediaRecorder.AudioSource.VOICE_COMMUNICATION,
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            bufSize
        )
        if (rec.state != AudioRecord.STATE_INITIALIZED) {
            rec.release()
            throw IllegalStateException("AudioRecord no inicializó")
        }
        record = rec
        rec.startRecording()
        capturing.set(true)

        captureThread = thread(name = "jarvis-mic", isDaemon = true) {
            val frame = ShortArray(FRAME_SAMPLES)
            while (capturing.get()) {
                var read = 0
                // Rellenar un frame completo (read puede ser parcial).
                while (read < FRAME_SAMPLES && capturing.get()) {
                    val n = rec.read(frame, read, FRAME_SAMPLES - read)
                    if (n <= 0) break
                    read += n
                }
                if (read == FRAME_SAMPLES) {
                    onFrame(frame.copyOf())
                }
            }
        }
    }

    /** Detiene la captura y libera recursos. */
    fun stopMic() {
        capturing.set(false)
        captureThread?.let {
            try {
                it.join(500)
            } catch (_: InterruptedException) {
            }
        }
        captureThread = null
        record?.apply {
            try {
                if (recordingState == AudioRecord.RECORDSTATE_RECORDING) stop()
            } catch (_: IllegalStateException) {
            }
            release()
        }
        record = null
        clearInputRoute()
    }

    /**
     * Reproduce un WAV por la salida activa (gafas). onDone se invoca al
     * terminar la reproducción.
     */
    fun play(wav: ByteArray, onDone: () -> Unit) {
        thread(name = "jarvis-play", isDaemon = true) {
            try {
                val pcm = WavUtil.wavToPcm16(wav)

                val attrs = AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
                val format = AudioFormat.Builder()
                    .setSampleRate(SAMPLE_RATE)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .build()
                val minOut = AudioTrack.getMinBufferSize(
                    SAMPLE_RATE,
                    AudioFormat.CHANNEL_OUT_MONO,
                    AudioFormat.ENCODING_PCM_16BIT
                )
                val at = AudioTrack(
                    attrs,
                    format,
                    maxOf(minOut, pcm.size * 2),
                    AudioTrack.MODE_STREAM,
                    AudioManager.AUDIO_SESSION_ID_GENERATE
                )
                track = at

                // Dirigir la salida a las gafas si están disponibles.
                routeOutputToGlasses(at)

                at.play()
                var offset = 0
                while (offset < pcm.size) {
                    val n = at.write(pcm, offset, pcm.size - offset)
                    if (n < 0) break
                    offset += n
                }
                // Vaciar el buffer antes de parar.
                at.stop()
                at.flush()
                at.release()
                track = null
            } catch (_: Exception) {
                track?.release()
                track = null
            } finally {
                onDone()
            }
        }
    }

    // --- Enrutado de entrada ---

    private fun routeInputToGlasses(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val dev = findBluetoothDevice(AudioManager.GET_DEVICES_INPUTS)
            if (dev != null) {
                audioManager.setCommunicationDevice(dev)
                true
            } else {
                false
            }
        } else {
            // Fallback API < 31: SCO clásico.
            @Suppress("DEPRECATION")
            if (audioManager.isBluetoothScoAvailableOffCall) {
                @Suppress("DEPRECATION")
                audioManager.startBluetoothSco()
                @Suppress("DEPRECATION")
                audioManager.isBluetoothScoOn = true
                true
            } else {
                false
            }
        }
    }

    private fun clearInputRoute() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            audioManager.clearCommunicationDevice()
        } else {
            @Suppress("DEPRECATION")
            audioManager.isBluetoothScoOn = false
            @Suppress("DEPRECATION")
            audioManager.stopBluetoothSco()
        }
        audioManager.mode = AudioManager.MODE_NORMAL
    }

    // --- Enrutado de salida ---

    private fun routeOutputToGlasses(at: AudioTrack) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val dev = findBluetoothDevice(AudioManager.GET_DEVICES_OUTPUTS)
            if (dev != null) {
                at.setPreferredDevice(dev)
            }
        }
    }

    /**
     * Busca un dispositivo Bluetooth (BLE primero, luego SCO) entre las
     * entradas o salidas. flags = GET_DEVICES_INPUTS | GET_DEVICES_OUTPUTS.
     */
    private fun findBluetoothDevice(flags: Int): AudioDeviceInfo? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return null
        val devices = audioManager.getDevices(flags)
        return devices.firstOrNull { it.type == AudioDeviceInfo.TYPE_BLE_HEADSET }
            ?: devices.firstOrNull { it.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO }
            ?: devices.firstOrNull()
    }
}
