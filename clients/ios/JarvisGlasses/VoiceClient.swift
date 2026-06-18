import AVFoundation
import Foundation

/// Cliente de voz de Jarvis para las gafas Meta (micro+altavoz Bluetooth HFP).
///
/// Flujo: push-to-talk -> graba del micro ACTIVO (las gafas, vía HFP) -> POST /voice
/// a Jarvis -> recibe un WAV con la voz del mayordomo -> lo reproduce por las gafas.
///
/// Clave (confirmado en la doc de Meta): el micro de las gafas se capta por el perfil
/// Bluetooth HFP estándar. Hay que pedir la sesión con `.allowBluetoothHFP` para que
/// iOS rute la ENTRADA a las gafas (si no, usa el micro del iPhone).
@MainActor
final class VoiceClient: NSObject, ObservableObject, AVAudioPlayerDelegate {
    enum State: String { case idle = "Listo", recording = "Escuchando…", thinking = "Jarvis piensa…", speaking = "Jarvis responde", error = "Error" }

    @Published var state: State = .idle
    @Published var transcript: String = ""
    @Published var reply: String = ""
    @Published var routedToGlasses: Bool = false

    private var recorder: AVAudioRecorder?
    private var player: AVAudioPlayer?
    private let fileURL = FileManager.default.temporaryDirectory.appendingPathComponent("jarvis_in.m4a")

    // Config (se rellena desde Ajustes de la app)
    var serverURL: String { UserDefaults.standard.string(forKey: "serverURL") ?? "" }
    var secret: String { UserDefaults.standard.string(forKey: "secret") ?? "" }

    // MARK: - Sesión de audio (rutea micro+altavoz a las gafas por HFP)
    private func configureSession() throws {
        let s = AVAudioSession.sharedInstance()
        // .videoChat da una AEC suave (micro y altavoz en las gafas); .allowBluetoothHFP
        // es lo que habilita la captura del micro de las gafas.
        try s.setCategory(.playAndRecord, mode: .videoChat,
                          options: [.allowBluetoothHFP, .defaultToSpeaker, .duckOthers])
        try s.setActive(true)
        // ¿La entrada activa es un dispositivo Bluetooth (las gafas)?
        let inputs = s.currentRoute.inputs.map { $0.portType }
        routedToGlasses = inputs.contains(.bluetoothHFP)
    }

    // MARK: - Grabar
    func startRecording() {
        do {
            try configureSession()
            let settings: [String: Any] = [
                AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
                AVSampleRateKey: 16000, AVNumberOfChannelsKey: 1,
                AVEncoderAudioQualityKey: AVAudioQuality.medium.rawValue,
            ]
            recorder = try AVAudioRecorder(url: fileURL, settings: settings)
            recorder?.record()
            state = .recording
        } catch {
            reply = "No pude abrir el micro: \(error.localizedDescription)"
            state = .error
        }
    }

    /// Para de grabar y manda el audio a Jarvis.
    func stopAndSend() {
        guard let rec = recorder, rec.isRecording else { return }
        rec.stop()
        recorder = nil
        state = .thinking
        Task { await upload() }
    }

    // MARK: - Subir a /voice y reproducir la respuesta
    private func upload() async {
        guard let base = URL(string: serverURL), !secret.isEmpty else {
            reply = "Configura la URL del servidor y el secreto en Ajustes."; state = .error; return
        }
        do {
            let audio = try Data(contentsOf: fileURL)
            var req = URLRequest(url: base.appendingPathComponent("voice"))
            req.httpMethod = "POST"
            req.setValue(secret, forHTTPHeaderField: "X-Jarvis-Events-Secret")
            req.setValue("audio/m4a", forHTTPHeaderField: "Content-Type")
            req.httpBody = audio
            req.timeoutInterval = 60

            let (data, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse else { throw URLError(.badServerResponse) }
            if http.statusCode == 422 { reply = "No te he entendido, repite."; state = .idle; return }
            guard http.statusCode == 200 else { reply = "Servidor: HTTP \(http.statusCode)"; state = .error; return }

            transcript = (http.value(forHTTPHeaderField: "X-Transcript")?.removingPercentEncoding) ?? ""
            reply = (http.value(forHTTPHeaderField: "X-Reply")?.removingPercentEncoding) ?? ""
            try playWav(data)
        } catch {
            reply = "Fallo de red: \(error.localizedDescription)"; state = .error
        }
    }

    private func playWav(_ data: Data) throws {
        player = try AVAudioPlayer(data: data)
        player?.delegate = self
        player?.play()                 // sale por la salida activa = las gafas
        state = .speaking
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in self.state = .idle }
    }
}
