// WebSocketService.swift
import Foundation
import Combine

// MARK: - Message Types
struct SubtitleMessage: Codable {
    let type: String
    let text: String?
    let is_final: Bool?
    let id: Int?
    let source_id: Int?
    let lang: String?
    let paused: Bool?
    let timestamp: String?
}

// MARK: - Subtitle Entry
struct SubtitleEntry: Identifiable {
    let id: Int
    var text: String
    var isFinal: Bool
    let timestamp: Date
}

// MARK: - WebSocket Service
@MainActor
class WebSocketService: ObservableObject {
    @Published var isConnected = false
    @Published var isPaused = false
    @Published var currentLang = "de"
    
    @Published var originalEntries: [SubtitleEntry] = []
    @Published var translatedEntries: [SubtitleEntry] = []
    @Published var translated2Entries: [SubtitleEntry] = []
    
    private var webSocketTask: URLSessionWebSocketTask?
    private var serverURL: URL?
    private var reconnectTimer: Timer?
    
    func connect(to urlString: String) {
        guard let url = URL(string: urlString) else { return }
        serverURL = url
        
        let session = URLSession(configuration: .default)
        webSocketTask = session.webSocketTask(with: url)
        webSocketTask?.resume()
        
        isConnected = true
        receiveMessage()
    }
    
    func disconnect() {
        webSocketTask?.cancel(with: .goingAway, reason: nil)
        webSocketTask = nil
        isConnected = false
    }
    
    private func receiveMessage() {
        webSocketTask?.receive { [weak self] result in
            Task { @MainActor in
                switch result {
                case .success(let message):
                    switch message {
                    case .string(let text):
                        self?.handleMessage(text)
                    default:
                        break
                    }
                    self?.receiveMessage()
                case .failure(_):
                    self?.isConnected = false
                    self?.scheduleReconnect()
                }
            }
        }
    }
    
    private func handleMessage(_ text: String) {
        guard let data = text.data(using: .utf8),
              let message = try? JSONDecoder().decode(SubtitleMessage.self, from: data) else {
            return
        }
        
        switch message.type {
        case "status":
            if let paused = message.paused {
                isPaused = paused
            }
            if let lang = message.lang {
                currentLang = lang
            }
            
        case "original":
            guard let msgText = message.text, let msgId = message.id else { return }
            if let index = originalEntries.firstIndex(where: { $0.id == msgId }) {
                originalEntries[index].text = msgText
                originalEntries[index].isFinal = message.is_final ?? false
            } else {
                let entry = SubtitleEntry(
                    id: msgId,
                    text: msgText,
                    isFinal: message.is_final ?? false,
                    timestamp: Date()
                )
                originalEntries.append(entry)
                if originalEntries.count > 50 {
                    originalEntries.removeFirst()
                }
            }
            
        case "translated":
            guard let msgText = message.text, let sourceId = message.source_id else { return }
            let entry = SubtitleEntry(
                id: sourceId,
                text: msgText,
                isFinal: true,
                timestamp: Date()
            )
            translatedEntries.append(entry)
            if translatedEntries.count > 50 {
                translatedEntries.removeFirst()
            }
            
        case "translated2":
            guard let msgText = message.text, let sourceId = message.source_id else { return }
            let entry = SubtitleEntry(
                id: sourceId,
                text: msgText,
                isFinal: true,
                timestamp: Date()
            )
            translated2Entries.append(entry)
            if translated2Entries.count > 50 {
                translated2Entries.removeFirst()
            }
            
        default:
            break
        }
    }
    
    func sendPause() {
        let message = ["type": isPaused ? "resume" : "pause"]
        sendJSON(message)
    }
    
    func setLanguage(_ lang: String) {
        let message = ["type": "set_language", "lang": lang]
        sendJSON(message)
    }
    
    private func sendJSON(_ dict: [String: String]) {
        guard let data = try? JSONSerialization.data(withJSONObject: dict),
              let string = String(data: data, encoding: .utf8) else { return }
        webSocketTask?.send(.string(string)) { _ in }
    }
    
    private func scheduleReconnect() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) { [weak self] in
            guard let self = self, let url = self.serverURL else { return }
            self.connect(to: url.absoluteString)
        }
    }
}
