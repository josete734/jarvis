package com.jarvis.glasses.net

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * Cliente HTTP contra el servidor Jarvis.
 * Envía el audio de la orden y recibe el WAV de respuesta.
 */
class JarvisClient(baseUrl: String, private val secret: String) {

    // Normaliza la URL base eliminando la barra final para evitar "//voice".
    private val base: String = baseUrl.trimEnd('/')

    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(60, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .callTimeout(60, TimeUnit.SECONDS)
        .build()

    /**
     * POST {baseUrl}/voice con el WAV PCM16 16kHz mono.
     * Devuelve el WAV de respuesta. Lanza IOException si el estado != 200.
     */
    suspend fun voice(wav: ByteArray): ByteArray {
        val mediaType = "audio/wav".toMediaType()
        val request = Request.Builder()
            .url("$base/voice")
            .header("X-Jarvis-Events-Secret", secret)
            .post(wav.toRequestBody(mediaType))
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw IOException("Jarvis /voice devolvió HTTP ${response.code}")
            }
            val body = response.body ?: throw IOException("Respuesta sin cuerpo")
            return body.bytes()
        }
    }
}
