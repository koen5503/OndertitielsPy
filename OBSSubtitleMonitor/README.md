# OBS Subtitle Monitor - iPad App

## Xcode Project Aanmaken

De Swift bronbestanden staan klaar. Volg deze stappen om het Xcode project te maken:

### 1. Open Xcode

```
File → New → Project
```

### 2. Kies template

- Platform: **iOS**
- Template: **App**
- Click Next

### 3. Configureer project

- Product Name: `OBSSubtitleMonitor`
- Team: *Jouw Developer Account*
- Organization Identifier: `com.jouwdomein`
- Interface: **SwiftUI**
- Language: **Swift**
- Click Next

### 4. Kies locatie

Sla op in: `/Users/koen/OBS_Python_ondertitels/OBSSubtitleMonitor_Xcode`

### 5. Kopieer bronbestanden

Vervang de standaard bestanden met:

- `OBSSubtitleMonitor/OBSSubtitleMonitorApp.swift` → App entry point
- `OBSSubtitleMonitor/ContentView.swift` → UI met 3 kolommen
- `OBSSubtitleMonitor/WebSocketService.swift` → WebSocket verbinding (nieuw toevoegen)

### 6. Build & Run

- Kies iPad Simulator of je echte iPad
- ⌘R om te builden

## Bestanden

| Bestand | Beschrijving |
|---------|--------------|
| `OBSSubtitleMonitorApp.swift` | App entry point |
| `ContentView.swift` | UI met 3 kolommen, pause button, settings |
| `WebSocketService.swift` | WebSocket client, message parsing |

## Gebruik

1. Start de Python pipeline op je Mac
2. Open de app op iPad
3. Voer het IP-adres van je Mac in
4. Klik "Verbinden"
