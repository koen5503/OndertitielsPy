# OBS AI Subtitle Pipeline

Live spraak-naar-ondertiteling pipeline met realtime vertaling.

## Features

- **PyAudio** non-blocking audio capture
- **Google Cloud STT V2** real-time speech-to-text (Nederlands)
- **Gemini 2.0 Flash** voor vertaling naar Engels
- **Silence stretcher** — detecteert pauzes van 200ms en verlengt ze naar 1.5s voor snellere finalisatie
- **WebSocket monitor** — real-time weergave van output + vertaling
- **YouTube Caption API** output (optioneel)

## Bestanden

| File | Beschrijving |
|------|--------------|
| [obs_subtitle_pipeline.py](obs_subtitle_pipeline.py) | Hoofd script |
| [monitor.html](monitor.html) | WebSocket monitor UI (2 kolommen) |
| [requirements.txt](requirements.txt) | Dependencies |

## Gebruik

```bash
# 1. Installeer dependencies
pip install -r requirements.txt

# 2. Configureer
export GOOGLE_PROJECT_ID="ondertitels-486017"
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
export YOUTUBE_CAPTION_URL="https://..."  # Optioneel

# 3. Start
python obs_subtitle_pipeline.py

# 4. Open monitor.html in browser voor live weergave
```

## Monitor UI

Open `monitor.html` in je browser na het starten van de pipeline:

- **Links**: Output (Nederlands) — STT transcriptie
- **Rechts**: Translated (EN) — Gemini vertaling

## Problemen Oplossen

### Audio Device Selectie overslaan

```bash
export AUDIO_DEVICE="AirPods"  # of deel van de naam
```

### Gevoeligheid aanpassen

Standaard worden zachte geluiden (RMS < 150) genegeerd:

```bash
export AUDIO_RMS_THRESHOLD="50"   # Verhoog gevoeligheid
export AUDIO_RMS_THRESHOLD="300"  # Minder ruis
```

Stop met `Ctrl+C`.
