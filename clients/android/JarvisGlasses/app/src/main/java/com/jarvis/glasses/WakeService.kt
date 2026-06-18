package com.jarvis.glasses

import com.jarvis.glasses.audio.AudioBridge
import com.jarvis.glasses.audio.WavUtil
import com.jarvis.glasses.data.Settings
import com.jarvis.glasses.net.JarvisClient
import com.jarvis.glasses.wake.VadDetector
import com.jarvis.glasses.wake.WakeWordDetector

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.io.IOException
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Foreground service que escucha "Hey Mycroft" en continuo por el micro de las gafas,
 * graba la orden, la envia al servidor Jarvis y reproduce la respuesta.
 *
 * Maquina de estados: LISTENING -> RECORDING -> THINKING -> SPEAKING -> LISTENING.
 */
class WakeService : LifecycleService() {

    companion object {
        // Estados expuestos a la UI.
        const val LISTENING = "LISTENING"
        const val RECORDING = "RECORDING"
        const val THINKING = "THINKING"
        const val SPEAKING = "SPEAKING"
        const val IDLE = "IDLE"

        /** Estado actual del bucle de voz, observable desde la UI. */
        val STATE = MutableStateFlow(IDLE)

        /** Indica si el micro entro realmente por las gafas (BLE/SCO). */
        val MIC_ROUTED = MutableStateFlow(false)

        private const val CHANNEL_ID = "jarvis"
        private const val NOTIF_ID = 1001

        // Parametros de endpointing.
        private const val SAMPLE_RATE = 16000
        private const val FRAME_SAMPLES = 1280            // 80 ms @ 16 kHz
        private const val SILENCE_TIMEOUT_MS = 800        // corte tras silencio
        private const val MAX_RECORD_MS = 10_000          // tope de grabacion
        private const val MIN_SPEECH_MS = 240             // descarta disparos vacios
    }

    private lateinit var settings: Settings
    private lateinit var audio: AudioBridge
    private lateinit var wake: WakeWordDetector
    private lateinit var vad: VadDetector

    // Buffer de la orden en curso (acceso desde el callback de audio).
    private val recording = ArrayList<Short>(SAMPLE_RATE * 10)

    // Flags de control del bucle, leidos/escritos desde el hilo de audio.
    private val isRecording = AtomicBoolean(false)
    private val muteWake = AtomicBoolean(false)           // true durante THINKING/SPEAKING
    private var silenceMs = 0
    private var recordedMs = 0
    private var speechMs = 0

    // Scope de IO para red/reproduccion sin bloquear el callback de audio.
    private val ioScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var inFlight: Job? = null

    private var serverUrl: String = ""
    private var secret: String = ""

    override fun onCreate() {
        super.onCreate()
        settings = Settings(this)
        audio = AudioBridge(this)
        wake = WakeWordDetector(this)
        vad = VadDetector(this)
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        startAsForeground()
        startLoop()
        // Watchdog: el sistema recrea el servicio si lo mata.
        return START_STICKY
    }

    private fun startLoop() {
        STATE.value = LISTENING
        // Carga la configuracion antes de abrir el micro.
        lifecycleScope.launch {
            serverUrl = settings.serverUrl.first()
            secret = settings.secret.first()
            wake.threshold = settings.threshold.first()

            audio.startMic { frame ->
                MIC_ROUTED.value = audio.micRoutedToGlasses
                onFrame(frame)
            }
        }
    }

    /** Procesa cada frame de 1280 muestras entregado por AudioBridge. */
    private fun onFrame(frame: ShortArray) {
        if (muteWake.get()) return  // no escuchar mientras pensamos/hablamos

        if (!isRecording.get()) {
            // LISTENING: buscar la wake word.
            if (wake.process(frame)) {
                beginRecording()
            }
            return
        }

        // RECORDING: acumular y aplicar endpointing por VAD.
        appendFrame(frame)
        recordedMs += frameMs()

        val speech = vad.isSpeech(frame)
        if (speech) {
            speechMs += frameMs()
            silenceMs = 0
        } else {
            silenceMs += frameMs()
        }

        val enoughSilence = silenceMs >= SILENCE_TIMEOUT_MS && speechMs >= MIN_SPEECH_MS
        val tooLong = recordedMs >= MAX_RECORD_MS
        if (enoughSilence || tooLong) {
            endRecordingAndSend()
        }
    }

    private fun beginRecording() {
        recording.clear()
        silenceMs = 0
        recordedMs = 0
        speechMs = 0
        vad.reset()
        isRecording.set(true)
        STATE.value = RECORDING
    }

    private fun appendFrame(frame: ShortArray) {
        for (s in frame) recording.add(s)
    }

    private fun endRecordingAndSend() {
        isRecording.set(false)
        // Si no hubo voz suficiente, vuelve a escuchar sin molestar al servidor.
        if (speechMs < MIN_SPEECH_MS || recording.isEmpty()) {
            wake.reset()
            STATE.value = LISTENING
            return
        }

        val pcm = recording.toShortArray()
        recording.clear()
        muteWake.set(true)   // ignora wake word durante THINKING/SPEAKING
        STATE.value = THINKING

        inFlight?.cancel()
        inFlight = ioScope.launch {
            try {
                val wav = WavUtil.pcm16ToWav(pcm, SAMPLE_RATE)
                val client = JarvisClient(serverUrl, secret)
                val responseWav = client.voice(wav)
                STATE.value = SPEAKING
                audio.play(responseWav) {
                    // Al terminar de hablar, re-arma la escucha.
                    resumeListening()
                }
            } catch (e: IOException) {
                // Error de red/servidor: vuelve a escuchar.
                resumeListening()
            } catch (e: Exception) {
                resumeListening()
            }
        }
    }

    private fun resumeListening() {
        wake.reset()
        muteWake.set(false)
        STATE.value = LISTENING
    }

    private fun frameMs(): Int = (FRAME_SAMPLES * 1000) / SAMPLE_RATE  // 80 ms

    private fun startAsForeground() {
        val notif = buildNotification(STATE.value)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIF_ID, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } else {
            startForeground(NOTIF_ID, notif)
        }
    }

    private fun buildNotification(state: String): Notification {
        val intent = Intent(this, MainActivity::class.java)
        val pi = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Jarvis escuchando")
            .setContentText("Estado: $state · di \"Hey Mycroft\"")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentIntent(pi)
            .setOngoing(true)
            .setShowWhen(false)
            .build()
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val mgr = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val ch = NotificationChannel(
                CHANNEL_ID, "Jarvis", NotificationManager.IMPORTANCE_LOW
            ).apply { description = "Servicio de escucha de voz" }
            mgr.createNotificationChannel(ch)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        inFlight?.cancel()
        ioScope.cancel()
        try { audio.stopMic() } catch (_: Exception) {}
        try { wake.close() } catch (_: Exception) {}
        try { vad.close() } catch (_: Exception) {}
        STATE.value = IDLE
        MIC_ROUTED.value = false
    }
}
