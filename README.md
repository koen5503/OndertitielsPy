# OBS AI Subtitle Pipeline - Walkthrough

## Wat is gebouwd

Live spraak-naar-ondertiteling pipeline met:

- **PyAudio** non-blocking audio capture
- **Google Cloud STT V2** real-time speech-to-text
- **Gemini 2.0 Flash** (via Vertex AI) voor zinsverkorting (>12 woorden → max 10)
- **YouTube Caption API** output (logging tot URL ingesteld)

## Wijzigingen sessie

| Probleem | Oplossing |
|----------|-----------|
| FINAL transcripts kwamen niet door | Alle interim en final transcripts direct doorsturen |
| Gemini model niet gevonden | Ge-update naar `gemini-2.0-flash-001` |
| Gemini output was Engels | Prompt aangepast naar Nederlands |
| Variable scope bug | Tracking variabelen buiten loop geplaatst |

## Bestanden

| File | Beschrijving |
|------|--------------|
| [obs_subtitle_pipeline.py](obs_subtitle_pipeline.py) | Hoofd script |
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
```

## Problemen Oplossen

### "Alleen audio chunks, geen tekst"

Dit betekent meestal dat de verkeerde microfoon is geselecteerd (bijv. NDI Audio zonder signaal).
Start het script opnieuw en kies expliciet de juiste microfoon (bijv. MacBook of AirPods) in het menu.

### Audio Device Selectie overslaan

Wil je niet elke keer kiezen? Zet de environment variable:

```bash
export AUDIO_DEVICE="AirPods"  # of deel van de naam
```

### Gevoeligheid aanpassen

Standaard worden zachte geluiden (ruis/stilte) genegeerd (RMS < 150).
Als de microfoon te zacht is, verlaag dit getal:

```bash
export AUDIO_RMS_THRESHOLD="50"
```

Als er te veel ruis doorkomt, verhoog het (bijv. 300).

Stop met `Ctrl+C`.

## Verificatie Resultaten

- ✅ **STT**: Real-time transcripts in Nederlands
- ✅ **Gemini**: Verkort lange zinnen in Nederlands, bv:
  - `"Lange zin, geen pauze: kan de transcriptie het aan?"`
  - `"Ik spreek een lange zin zonder pauze om te testen."`
- ✅ **Output**: Timestamps + tekst klaar voor YouTube CC
- ✅ **Graceful shutdown**: Clean exit op Ctrl+C
