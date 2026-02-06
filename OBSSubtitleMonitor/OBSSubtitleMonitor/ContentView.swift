// ContentView.swift
import SwiftUI

struct ContentView: View {
    @StateObject private var wsService = WebSocketService()
    @State private var serverIP = "192.168.1.100"
    @State private var isShowingSettings = true
    
    let languages = [
        ("de", "Deutsch"),
        ("fr", "Français"),
        ("es", "Español"),
        ("pt", "Português"),
        ("it", "Italiano"),
        ("pl", "Polski"),
        ("ru", "Русский (Russian)"),
        ("uk", "Українська (Ukrainian)"),
        ("zh", "中文 (Chinese)"),
        ("ja", "日本語 (Japanese)")
    ]
    
    var body: some View {
        VStack(spacing: 0) {
            // Top bar
            HStack {
                Button(action: { wsService.sendPause() }) {
                    HStack {
                        Image(systemName: wsService.isPaused ? "play.fill" : "pause.fill")
                        Text(wsService.isPaused ? "Resume" : "Pause")
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .background(wsService.isPaused ? Color.red : Color.green)
                    .foregroundColor(.white)
                    .cornerRadius(8)
                }
                .disabled(!wsService.isConnected)
                
                Spacer()
                
                Button(action: { isShowingSettings = true }) {
                    Image(systemName: "gear")
                        .font(.title2)
                }
                
                Circle()
                    .fill(wsService.isConnected ? Color.green : Color.red)
                    .frame(width: 12, height: 12)
                
                Text(wsService.isConnected ? "Verbonden" : "Niet verbonden")
                    .foregroundColor(wsService.isConnected ? .green : .red)
            }
            .padding()
            .background(Color(.systemGray6))
            
            // Three columns
            HStack(spacing: 12) {
                // Original (NL)
                SubtitleColumn(
                    title: "📡 Output (NL)",
                    entries: wsService.originalEntries,
                    color: .primary
                )
                
                // Translated (EN)
                SubtitleColumn(
                    title: "🌍 English",
                    entries: wsService.translatedEntries,
                    color: .blue
                )
                
                // Dynamic language
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text("🌐")
                        Picker("", selection: Binding(
                            get: { wsService.currentLang },
                            set: { wsService.setLanguage($0) }
                        )) {
                            ForEach(languages, id: \.0) { lang in
                                Text(lang.1).tag(lang.0)
                            }
                        }
                        .pickerStyle(.menu)
                        .disabled(!wsService.isConnected)
                    }
                    .font(.headline)
                    
                    SubtitleList(entries: wsService.translated2Entries, color: .orange)
                }
                .padding()
                .background(Color(.systemGray6))
                .cornerRadius(12)
            }
            .padding()
        }
        .sheet(isPresented: $isShowingSettings) {
            SettingsSheet(
                serverIP: $serverIP,
                isConnected: wsService.isConnected,
                onConnect: {
                    wsService.connect(to: "ws://\(serverIP):8765")
                    isShowingSettings = false
                },
                onDisconnect: {
                    wsService.disconnect()
                }
            )
        }
    }
}

struct SubtitleColumn: View {
    let title: String
    let entries: [SubtitleEntry]
    let color: Color
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)
            
            SubtitleList(entries: entries, color: color)
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }
}

struct SubtitleList: View {
    let entries: [SubtitleEntry]
    let color: Color
    
    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(entries) { entry in
                        Text(entry.text)
                            .foregroundColor(entry.isFinal ? color : .gray)
                            .opacity(entry.isFinal ? 1.0 : 0.7)
                            .padding(8)
                            .background(Color(.systemBackground))
                            .cornerRadius(6)
                            .id(entry.id)
                    }
                }
            }
            .onChange(of: entries.count) { _ in
                if let last = entries.last {
                    withAnimation {
                        proxy.scrollTo(last.id, anchor: .bottom)
                    }
                }
            }
        }
    }
}

struct SettingsSheet: View {
    @Binding var serverIP: String
    let isConnected: Bool
    let onConnect: () -> Void
    let onDisconnect: () -> Void
    @Environment(\.dismiss) var dismiss
    
    var body: some View {
        NavigationView {
            Form {
                Section("Server") {
                    TextField("IP Adres", text: $serverIP)
                        .keyboardType(.decimalPad)
                    
                    Text("Voer het IP-adres in van de computer waar de Python pipeline draait.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                Section {
                    if isConnected {
                        Button("Verbinding verbreken", role: .destructive) {
                            onDisconnect()
                        }
                    } else {
                        Button("Verbinden") {
                            onConnect()
                        }
                    }
                }
            }
            .navigationTitle("Instellingen")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Klaar") {
                        dismiss()
                    }
                }
            }
        }
    }
}

#Preview {
    ContentView()
}
