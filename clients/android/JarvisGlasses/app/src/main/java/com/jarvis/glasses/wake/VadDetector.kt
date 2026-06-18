package com.jarvis.glasses.wake

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.content.Context
import java.nio.FloatBuffer
import java.nio.LongBuffer

/**
 * Silero VAD (silero_vad.onnx, variante v4) sobre ONNX Runtime.
 *
 * Entradas del grafo:
 *  - "input" float32 [batch, sequence]  (muestras normalizadas a [-1,1])
 *  - "sr"    int64    escalar           (frecuencia de muestreo, 16000)
 *  - "h"     float32 [2, batch, 64]     (estado LSTM)
 *  - "c"     float32 [2, batch, 64]     (estado LSTM)
 * Salidas:
 *  - "output" float32 [batch, 1]        (probabilidad de voz)
 *  - "hn", "cn"                         (nuevos estados, se realimentan)
 *
 * Mantiene el estado recurrente h/c entre llamadas para hacer endpointing.
 */
class VadDetector(ctx: Context) {

    private val env: OrtEnvironment = OrtEnvironment.getEnvironment()
    private val session: OrtSession

    // Estado recurrente LSTM [2, 1, 64].
    private val stateDims = longArrayOf(2, 1, 64)
    private var h = FloatArray(2 * 1 * 64)
    private var c = FloatArray(2 * 1 * 64)

    // Frecuencia de muestreo fija (gafas a 16 kHz).
    private val sampleRate = 16000L

    init {
        val bytes = ctx.assets.open("silero_vad.onnx").use { it.readBytes() }
        val opts = OrtSession.SessionOptions().apply {
            setIntraOpNumThreads(1)
            setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
        }
        session = env.createSession(bytes, opts)
    }

    /**
     * Devuelve true si el frame contiene voz (prob > 0.5).
     * frame16k: muestras int16 @16kHz (típicamente 1280 = 80 ms; el modelo v4
     * acepta longitud de secuencia variable).
     */
    @Synchronized
    fun isSpeech(frame16k: ShortArray): Boolean {
        // int16 -> float32 normalizado a [-1, 1].
        val audio = FloatArray(frame16k.size) { frame16k[it] / 32768.0f }

        val inputTensor = OnnxTensor.createTensor(
            env,
            FloatBuffer.wrap(audio),
            longArrayOf(1, frame16k.size.toLong())
        )
        val srTensor = OnnxTensor.createTensor(
            env,
            LongBuffer.wrap(longArrayOf(sampleRate)),
            longArrayOf()
        )
        val hTensor = OnnxTensor.createTensor(env, FloatBuffer.wrap(h), stateDims)
        val cTensor = OnnxTensor.createTensor(env, FloatBuffer.wrap(c), stateDims)

        val inputs = mapOf(
            "input" to inputTensor,
            "sr" to srTensor,
            "h" to hTensor,
            "c" to cTensor
        )

        var prob: Float
        session.run(inputs).use { result ->
            @Suppress("UNCHECKED_CAST")
            val out = (result[0].value as Array<FloatArray>)
            prob = out[0][0]
            // Realimentar el estado recurrente (hn, cn).
            h = flattenState(result[1].value)
            c = flattenState(result[2].value)
        }

        inputTensor.close()
        srTensor.close()
        hTensor.close()
        cTensor.close()

        return prob > 0.5f
    }

    /** Reinicia el estado recurrente (al empezar una nueva captura). */
    @Synchronized
    fun reset() {
        h = FloatArray(2 * 1 * 64)
        c = FloatArray(2 * 1 * 64)
    }

    @Synchronized
    fun close() {
        session.close()
    }

    /** Aplana el estado [2,1,64] devuelto por ONNX a un FloatArray contiguo. */
    private fun flattenState(value: Any): FloatArray {
        @Suppress("UNCHECKED_CAST")
        val arr = value as Array<Array<FloatArray>>
        val out = FloatArray(2 * 1 * 64)
        var idx = 0
        for (i in 0 until 2) {
            for (j in arr[i].indices) {
                val row = arr[i][j]
                System.arraycopy(row, 0, out, idx, row.size)
                idx += row.size
            }
        }
        return out
    }
}
