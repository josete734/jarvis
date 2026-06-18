package com.jarvis.glasses

import com.jarvis.glasses.data.Settings

import android.Manifest
import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.jarvis.glasses.util.Power
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    // Solicita en bloque los permisos que necesita el servicio de micro.
    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { /* el usuario decide; el servicio degrada si falta alguno */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { MaterialTheme { AppScreen(::ensurePermissions, ::startWake, ::stopWake) } }
    }

    /** Pide RECORD_AUDIO, POST_NOTIFICATIONS, BLUETOOTH_CONNECT y exencion de bateria. */
    private fun ensurePermissions() {
        val perms = mutableListOf(Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            perms += Manifest.permission.POST_NOTIFICATIONS
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            perms += Manifest.permission.BLUETOOTH_CONNECT
        }
        permissionLauncher.launch(perms.toTypedArray())
        if (!Power.isIgnoringBatteryOptimizations(this)) {
            Power.requestIgnoreBatteryOptimizations(this)
        }
    }

    private fun startWake() {
        val intent = Intent(this, WakeService::class.java)
        ContextCompat.startForegroundService(this, intent)
    }

    private fun stopWake() {
        stopService(Intent(this, WakeService::class.java))
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AppScreen(
    onRequestPermissions: () -> Unit,
    onStart: () -> Unit,
    onStop: () -> Unit,
) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val settings = remember { Settings(ctx) }

    var url by remember { mutableStateOf("") }
    var secret by remember { mutableStateOf("") }
    var loaded by remember { mutableStateOf(false) }

    val state by WakeService.STATE.collectAsState()
    val micRouted by WakeService.MIC_ROUTED.collectAsState()

    // Carga inicial de la configuracion guardada.
    if (!loaded) {
        loaded = true
        scope.launch {
            url = settings.serverUrl.first()
            secret = settings.secret.first()
        }
    }

    Scaffold(
        topBar = { TopAppBar(title = { Text("Jarvis Glasses") }) }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            OutlinedTextField(
                value = url,
                onValueChange = { url = it },
                label = { Text("URL del servidor") },
                placeholder = { Text("https://host.tailnet.ts.net o http://192.168.0.32:8070") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                value = secret,
                onValueChange = { secret = it },
                label = { Text("Secreto (X-Jarvis-Events-Secret)") },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                modifier = Modifier.fillMaxWidth()
            )

            Button(
                onClick = {
                    scope.launch {
                        // Conserva el umbral actual al guardar URL/secreto.
                        val th = settings.threshold.first()
                        settings.save(url.trim(), secret.trim(), th)
                    }
                },
                modifier = Modifier.fillMaxWidth()
            ) { Text("Guardar configuracion") }

            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp)) {
                    Text("Estado", style = MaterialTheme.typography.labelMedium)
                    Text(state, style = MaterialTheme.typography.headlineSmall)
                    Spacer(Modifier.height(8.dp))
                    Text(
                        if (micRouted) "Micro: gafas (BLE/SCO)" else "Micro: no enrutado a las gafas",
                        style = MaterialTheme.typography.bodyMedium
                    )
                }
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Button(
                    onClick = {
                        onRequestPermissions()
                        onStart()
                    },
                    modifier = Modifier.fillMaxWidth().padding(end = 0.dp)
                ) { Text("Iniciar") }
            }
            OutlinedButton(
                onClick = onStop,
                modifier = Modifier.fillMaxWidth()
            ) { Text("Parar") }

            Text(
                "Di \"Hey Mycroft\" seguido de tu orden en una sola frase.",
                style = MaterialTheme.typography.bodySmall
            )
        }
    }
}
