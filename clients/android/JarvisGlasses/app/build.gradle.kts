plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    // Compose Compiler de Kotlin 2.0 (sustituye a kotlinCompilerExtensionVersion).
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.jarvis.glasses"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.jarvis.glasses"
        minSdk = 28
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
        // Los modelos ONNX deben quedar sin comprimir para mapearlos en memoria.
        jniLibs {
            useLegacyPackaging = false
        }
    }

    // Mantener los .onnx sin comprimir dentro del APK.
    androidResources {
        noCompress.add("onnx")
    }
}

dependencies {
    // ONNX Runtime (wake word + VAD).
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.20.0")

    // Red HTTP.
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    // Jetpack Compose (BOM gestiona versiones coherentes).
    implementation(platform("androidx.compose:compose-bom:2024.09.03"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.9.2")
    debugImplementation("androidx.compose.ui:ui-tooling")

    // Ciclo de vida (servicio + runtime).
    implementation("androidx.lifecycle:lifecycle-service:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")

    // Persistencia de ajustes.
    implementation("androidx.datastore:datastore-preferences:1.1.1")

    // Corrutinas.
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}
