package com.jarvis.glasses.util

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.PowerManager
import android.provider.Settings

/**
 * Ayudas para la optimización de batería: el servicio en primer plano
 * debe quedar exento para escuchar la wake word de forma continua.
 */
object Power {

    /** True si la app ya está exenta de la optimización de batería. */
    fun isIgnoringBatteryOptimizations(ctx: Context): Boolean {
        val pm = ctx.getSystemService(Context.POWER_SERVICE) as PowerManager
        return pm.isIgnoringBatteryOptimizations(ctx.packageName)
    }

    /**
     * Lanza el diálogo del sistema para solicitar la exención.
     * Usa FLAG_ACTIVITY_NEW_TASK por si se invoca desde un Context no-Activity.
     */
    fun requestIgnoreBatteryOptimizations(ctx: Context) {
        if (isIgnoringBatteryOptimizations(ctx)) return
        val intent = Intent(
            Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
            Uri.parse("package:${ctx.packageName}")
        ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        ctx.startActivity(intent)
    }
}
