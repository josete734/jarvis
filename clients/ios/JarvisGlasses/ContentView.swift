import SwiftUI

struct ContentView: View {
    @StateObject private var client = VoiceClient()
    @AppStorage("serverURL") private var serverURL = ""
    @AppStorage("secret") private var secret = ""
    @State private var showSettings = false

    var body: some View {
        VStack(spacing: 28) {
            HStack {
                Circle().fill(client.routedToGlasses ? .green : .orange).frame(width: 10, height: 10)
                Text(client.routedToGlasses ? "Micro: gafas (HFP)" : "Micro: iPhone")
                    .font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button { showSettings = true } label: { Image(systemName: "gearshape") }
            }

            Spacer()
            Text(client.state.rawValue).font(.title2).bold()
                .foregroundStyle(client.state == .error ? .red : .primary)

            if !client.transcript.isEmpty {
                Text("Tú: \(client.transcript)").font(.callout).foregroundStyle(.secondary)
            }
            if !client.reply.isEmpty {
                Text(client.reply).font(.title3).multilineTextAlignment(.center)
                    .padding().background(.quaternary, in: RoundedRectangle(cornerRadius: 16))
            }
            Spacer()

            // Push-to-talk: mantén pulsado para hablar, suelta para enviar.
            Circle()
                .fill(client.state == .recording ? Color.red : Color.accentColor)
                .frame(width: 130, height: 130)
                .overlay(Image(systemName: "mic.fill").font(.system(size: 48)).foregroundStyle(.white))
                .scaleEffect(client.state == .recording ? 1.1 : 1.0)
                .animation(.spring(duration: 0.2), value: client.state)
                .gesture(
                    DragGesture(minimumDistance: 0)
                        .onChanged { _ in if client.state == .idle || client.state == .speaking { client.startRecording() } }
                        .onEnded { _ in if client.state == .recording { client.stopAndSend() } }
                )
            Text("Mantén pulsado y habla").font(.footnote).foregroundStyle(.secondary)
        }
        .padding()
        .sheet(isPresented: $showSettings) {
            NavigationStack {
                Form {
                    Section("Servidor Jarvis") {
                        TextField("https://host.tailnet.ts.net  o  http://192.168.0.32:8070", text: $serverURL)
                            .autocorrectionDisabled().textInputAutocapitalization(.never)
                        SecureField("Secreto (EVENTS_SECRET)", text: $secret)
                    }
                    Section(footer: Text("Empareja antes las gafas con la app Meta AI; luego en Ajustes > Bluetooth del iPhone deben quedar conectadas para «llamadas y audio».")) { EmptyView() }
                }
                .navigationTitle("Ajustes")
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Listo") { showSettings = false } } }
            }
        }
    }
}
