package com.jarvis.glasses.wake

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.content.Context
import java.io.Closeable
import java.nio.FloatBuffer

/**
 * Detector de wake word "Hey Mycroft" fiel al pipeline de openWakeWord
 * (github.com/dscripka/openWakeWord) usando ONNX Runtime Android.
 *
 * Cadena de modelos:
 *   1) melspectrogram.onnx : entrada audio PCM float [1, N] -> salida [1,1,T,32]
 *      (32 bins mel; ~97 frames/s). Se aplica el escalado de openWakeWord: x/10 + 2.
 *   2) embedding_model.onnx : entrada ventana mel [1, 76, 32, 1] -> embedding [1,1,1,96]
 *      (96 dims). Ventana de 76 frames mel, paso de 8 frames.
 *   3) hey_mycroft_v0.1.onnx : entrada [1, 16, 96] (16 embeddings) -> score [1,1].
 *
 * Se mantienen dos buffers deslizantes:
 *   - melBuffer    : frames mel [32] acumulados; al haber >=76 se generan embeddings
 *                    avanzando de 8 en 8 frames.
 *   - embedBuffer  : embeddings [96]; los ultimos 16 forman la entrada de la wakeword.
 *
 * Cada llamada a process() consume un frame de 1280 muestras int16 @16kHz (80 ms).
 */
class WakeWordDetector(
    private val ctx: Context,
    var threshold: Float = 0.5f
) : Closeable {

    private companion object {
        const val MEL_BINS = 32          // bins mel por frame
        const val EMB_WINDOW = 76        // frames mel por ventana de embedding
        const val EMB_STEP = 8           // paso (frames mel) entre embeddings
        const val EMB_DIM = 96           // dimension del embedding
        const val WW_WINDOW = 16         // embeddings que consume la wakeword
        const val FRAME_SAMPLES = 1280   // muestras por frame (80 ms)

        // Limites de los buffers (~10 s, como en openWakeWord) para no crecer sin fin.
        const val MEL_MAX_FRAMES = 10 * 97
        const val EMB_MAX = 120
    }

    private val env: OrtEnvironment = OrtEnvironment.getEnvironment()

    private val melSession: OrtSession = createSession("melspectrogram.onnx")
    private val embSession: OrtSession = createSession("embedding_model.onnx")
    private val wwSession: OrtSession = createSession("hey_mycroft_v0.1.onnx")

    private val melInputName: String = melSession.inputNames.iterator().next()
    private val embInputName: String = embSession.inputNames.iterator().next()
    private val wwInputName: String = wwSession.inputNames.iterator().next()

    // Buffer deslizante de frames mel: cada elemento es un frame de 32 floats.
    private val melBuffer = ArrayDeque<FloatArray>()
    // Indice del primer frame mel aun no consumido por una ventana de embedding.
    private var melConsumed = 0

    // Buffer deslizante de embeddings: cada elemento es un vector de 96 floats.
    private val embedBuffer = ArrayDeque<FloatArray>()

    private fun createSession(asset: String): OrtSession {
        val bytes = ctx.assets.open(asset).use { it.readBytes() }
        return env.createSession(bytes, OrtSession.SessionOptions())
    }

    /**
     * Procesa un frame de 1280 muestras int16 @16kHz.
     * Devuelve true cuando el score de "Hey Mycroft" supera [threshold].
     */
    fun process(frame16k: ShortArray): Boolean {
        require(frame16k.size == FRAME_SAMPLES) {
            "Se esperan $FRAME_SAMPLES muestras por frame, recibidas ${frame16k.size}"
        }

        // 1) Audio int16 -> float (openWakeWord alimenta el PCM tal cual, sin normalizar).
        val audio = FloatArray(FRAME_SAMPLES) { frame16k[it].toFloat() }

        // 2) melspectrogram: [1, 1280] -> [1,1,T,32], aplicar escalado y acumular.
        val melFrames = computeMel(audio)
        for (f in melFrames) melBuffer.addLast(f)
        trimMel()

        // 3) Generar todos los embeddings posibles con ventana 76 / paso 8.
        produceEmbeddings()

        // 4) Si hay >=16 embeddings, evaluar la wakeword con los ultimos 16.
        if (embedBuffer.size < WW_WINDOW) return false
        val score = runWakeword()
        return score >= threshold
    }

    /** melspectrogram.onnx: entrada [1, N] float -> salida [1,1,T,32]; escalado x/10+2. */
    private fun computeMel(audio: FloatArray): List<FloatArray> {
        val input = OnnxTensor.createTensor(
            env,
            FloatBuffer.wrap(audio),
            longArrayOf(1, audio.size.toLong())
        )
        input.use {
            melSession.run(mapOf(melInputName to it)).use { result ->
                // Salida tipica [1,1,T,32]; se aplana dinamicamente.
                @Suppress("UNCHECKED_CAST")
                val raw = result[0].value
                return flattenMel(raw)
            }
        }
    }

    /** Aplana la salida del modelo mel (forma [1,1,T,32] o [1,T,32]) a lista de frames [32], con x/10+2. */
    private fun flattenMel(raw: Any?): List<FloatArray> {
        // Descender por las dimensiones de batch hasta llegar al eje temporal T.
        var node: Any? = raw
        // raw es un array anidado de FloatArray; descender mientras el elemento no sea ya [T][32].
        while (node is Array<*> && node.isNotEmpty() && node[0] is Array<*> &&
            (node[0] as Array<*>).isNotEmpty() && (node[0] as Array<*>)[0] is Array<*>
        ) {
            node = node[0]
        }
        @Suppress("UNCHECKED_CAST")
        val frames = node as Array<FloatArray> // [T][32]
        val out = ArrayList<FloatArray>(frames.size)
        for (frame in frames) {
            val scaled = FloatArray(frame.size)
            for (i in frame.indices) scaled[i] = frame[i] / 10f + 2f
            out.add(scaled)
        }
        return out
    }

    /** embedding_model.onnx: por cada ventana [1,76,32,1] produce un embedding [96]. */
    private fun produceEmbeddings() {
        // Avanzar de 8 en 8 frames mientras quepa una ventana completa de 76.
        while (melConsumed + EMB_WINDOW <= melBuffer.size) {
            val embedding = runEmbedding(melConsumed)
            embedBuffer.addLast(embedding)
            if (embedBuffer.size > EMB_MAX) embedBuffer.removeFirst()
            melConsumed += EMB_STEP
        }
        // Recortar frames mel ya consumidos para que melConsumed no crezca sin limite.
        if (melConsumed >= EMB_WINDOW) {
            val drop = melConsumed - (EMB_WINDOW - EMB_STEP)
            if (drop > 0) {
                repeat(drop) { melBuffer.removeFirst() }
                melConsumed -= drop
            }
        }
    }

    /** Ejecuta el modelo de embedding sobre la ventana mel [start, start+76). */
    private fun runEmbedding(start: Int): FloatArray {
        // Construir tensor [1, 76, 32, 1] en orden row-major.
        val buf = FloatBuffer.allocate(EMB_WINDOW * MEL_BINS)
        for (t in 0 until EMB_WINDOW) {
            val frame = melBuffer.elementAt(start + t)
            buf.put(frame, 0, MEL_BINS)
        }
        buf.rewind()
        val input = OnnxTensor.createTensor(
            env,
            buf,
            longArrayOf(1, EMB_WINDOW.toLong(), MEL_BINS.toLong(), 1)
        )
        input.use {
            embSession.run(mapOf(embInputName to it)).use { result ->
                // Salida tipica [1,1,1,96]; aplanar al vector de 96.
                return flatten96(result[0].value)
            }
        }
    }

    /** Aplana la salida del embedding (forma [1,1,1,96] o similar) a un FloatArray[96]. */
    private fun flatten96(raw: Any?): FloatArray {
        var node: Any? = raw
        while (node is Array<*> && node.isNotEmpty() && node[0] is Array<*>) {
            node = node[0]
        }
        return node as FloatArray
    }

    /** hey_mycroft: entrada [1,16,96] con los ultimos 16 embeddings -> score [1,1]. */
    private fun runWakeword(): Float {
        val buf = FloatBuffer.allocate(WW_WINDOW * EMB_DIM)
        val startIdx = embedBuffer.size - WW_WINDOW
        for (i in 0 until WW_WINDOW) {
            buf.put(embedBuffer.elementAt(startIdx + i), 0, EMB_DIM)
        }
        buf.rewind()
        val input = OnnxTensor.createTensor(
            env,
            buf,
            longArrayOf(1, WW_WINDOW.toLong(), EMB_DIM.toLong())
        )
        input.use {
            wwSession.run(mapOf(wwInputName to it)).use { result ->
                return flattenScalar(result[0].value)
            }
        }
    }

    /** Extrae el score escalar de una salida [1,1] (o anidada). */
    private fun flattenScalar(raw: Any?): Float {
        var node: Any? = raw
        while (node is Array<*> && node.isNotEmpty()) node = node[0]
        return when (node) {
            is Float -> node
            else -> (raw as? FloatArray)?.firstOrNull() ?: 0f
        }
    }

    /** Mantiene melBuffer dentro del limite de ~10 s. */
    private fun trimMel() {
        while (melBuffer.size > MEL_MAX_FRAMES) {
            melBuffer.removeFirst()
            if (melConsumed > 0) melConsumed--
        }
    }

    /** Reinicia los buffers deslizantes (tras una deteccion o al reanudar la escucha). */
    fun reset() {
        melBuffer.clear()
        melConsumed = 0
        embedBuffer.clear()
    }

    /** Libera sesiones ONNX y el entorno. */
    override fun close() {
        melSession.close()
        embSession.close()
        wwSession.close()
        // OrtEnvironment es un singleton compartido; no se cierra aqui.
    }
}
