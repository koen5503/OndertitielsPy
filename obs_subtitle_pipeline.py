#!/usr/bin/env python3
"""
OBS AI Subtitle Pipeline
Converts live speech to concise subtitles for YouTube CC.

Components:
- PyAudio: Non-blocking audio capture
- Google Cloud STT V2: Speech-to-Text
- Gemini 1.5 Flash: Sentence shortening
- YouTube Caption API: Output
"""

import asyncio
import audioop
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import aiohttp
import vertexai
from vertexai.generative_models import GenerativeModel
import pyaudio
from google.cloud.speech_v2 import SpeechAsyncClient
from google.cloud.speech_v2.types import cloud_speech

# ============================================================================
# Configuration
# ============================================================================

# Audio settings
SAMPLE_RATE = 16000
CHUNK_SIZE = 1600  # 100ms chunks at 16kHz
CHANNELS = 1
FORMAT = pyaudio.paInt16
MIN_RMS_THRESHOLD = int(os.getenv("AUDIO_RMS_THRESHOLD", 150))  # Ignore silence < 150 RMS

# Google Cloud
GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID", "ondertitels-486017")
GOOGLE_LOCATION = os.getenv("GOOGLE_LOCATION", "us-central1")  # Vertex AI region (Gemini available)
_DEFAULT_CREDENTIALS = "/Users/koen/OBS_Python_ondertitels/ondertitels-486017-0ee48ab1ba8d.json"
# Set GOOGLE_APPLICATION_CREDENTIALS if not already set
if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _DEFAULT_CREDENTIALS
GOOGLE_CREDENTIALS = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
STT_LANGUAGE_CODE = os.getenv("STT_LANGUAGE_CODE", "nl-NL")

# Sentence shortening threshold
SHORTEN_THRESHOLD = 12  # words

# YouTube CC
YOUTUBE_CAPTION_URL = os.getenv("YOUTUBE_CAPTION_URL")

# Reconnection
MAX_BACKOFF_SECONDS = 60
INITIAL_BACKOFF_SECONDS = 1


# ============================================================================
# Logging Setup
# ============================================================================

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("obs_subtitle_pipeline.log"),
    ],
)
logger = logging.getLogger("OBS-Subtitle")


# ============================================================================
# Audio Producer (Thread)
# ============================================================================

class AudioProducer:
    """Non-blocking audio capture using PyAudio callback mode."""
    
    def __init__(self, audio_queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        self.audio_queue = audio_queue
        self.loop = loop
        self.running = False
        self.pyaudio_instance: Optional[pyaudio.PyAudio] = None
        self.stream: Optional[pyaudio.Stream] = None
        logger.info("AudioProducer initialized")
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio callback - runs in separate thread."""
        if status:
            logger.warning(f"PyAudio status: {status}")
        
        if self.running:
            # Calculate RMS amplitude
            rms = audioop.rms(in_data, 2)
            
            if rms < MIN_RMS_THRESHOLD:
                # Silence - send zero bytes to keep stream alive but filter noise
                # This prevents "409 Stream timed out" from Google
                silence_chunk = bytes(len(in_data))
                asyncio.run_coroutine_threadsafe(
                    self.audio_queue.put(silence_chunk), self.loop
                )
                return (None, pyaudio.paContinue)
            
            # Thread-safe put to asyncio queue
            asyncio.run_coroutine_threadsafe(
                self.audio_queue.put(in_data), self.loop
            )
            # logger.debug(f"Audio chunk queued: {len(in_data)} bytes (RMS: {rms})")
        
        return (None, pyaudio.paContinue)
    
    def start(self):
        """Start audio capture."""
        logger.info("Starting audio capture...")
        self.pyaudio_instance = pyaudio.PyAudio()
        
        # Get pre-selected device ID from main()
        device_id = int(os.getenv("_SELECTED_AUDIO_DEVICE_ID", "0"))
        dev_info = self.pyaudio_instance.get_device_info_by_index(device_id)
        logger.info(f"Using audio device: {dev_info.get('name')} (id={device_id})")
        
        self.running = True
        self.stream = self.pyaudio_instance.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            input_device_index=device_id,
            frames_per_buffer=CHUNK_SIZE,
            stream_callback=self._audio_callback,
        )
        self.stream.start_stream()
        logger.info(f"Audio stream started: {SAMPLE_RATE}Hz, {CHANNELS}ch, {CHUNK_SIZE} frames/buffer")
    
    def stop(self):
        """Stop audio capture."""
        logger.info("Stopping audio capture...")
        self.running = False
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        
        if self.pyaudio_instance:
            self.pyaudio_instance.terminate()
            self.pyaudio_instance = None
        
        logger.info("Audio capture stopped")


# ============================================================================
# Google Cloud STT Stream Task
# ============================================================================

async def audio_generator(audio_queue: asyncio.Queue):
    """Generate audio chunks for STT stream."""
    while True:
        chunk = await audio_queue.get()
        yield chunk


async def stt_stream_task(
    audio_queue: asyncio.Queue,
    transcript_queue: asyncio.Queue,
    shutdown_event: asyncio.Event,
):
    """
    Consume audio from queue and stream to Google Cloud STT.
    Implements exponential backoff for reconnections.
    """
    logger.info("STT Stream Task started")
    backoff = INITIAL_BACKOFF_SECONDS
    
    while not shutdown_event.is_set():
        try:
            client = SpeechAsyncClient()
            
            # Recognition config
            recognition_config = cloud_speech.RecognitionConfig(
                explicit_decoding_config=cloud_speech.ExplicitDecodingConfig(
                    encoding=cloud_speech.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
                    sample_rate_hertz=SAMPLE_RATE,
                    audio_channel_count=CHANNELS,
                ),
                language_codes=[STT_LANGUAGE_CODE],
                model="long",
                features=cloud_speech.RecognitionFeatures(
                    enable_automatic_punctuation=True,
                ),
            )
            
            streaming_config = cloud_speech.StreamingRecognitionConfig(
                config=recognition_config,
                streaming_features=cloud_speech.StreamingRecognitionFeatures(
                    interim_results=True,
                ),
            )
            
            config_request = cloud_speech.StreamingRecognizeRequest(
                recognizer=f"projects/{GOOGLE_PROJECT_ID}/locations/global/recognizers/_",
                streaming_config=streaming_config,
            )
            
            async def request_generator():
                """Generate requests for the streaming API."""
                yield config_request
                logger.debug("Sent STT config request")
                
                async for chunk in audio_generator(audio_queue):
                    if shutdown_event.is_set():
                        break
                    yield cloud_speech.StreamingRecognizeRequest(audio=chunk)
            
            logger.info("Starting STT streaming session...")
            print("🎤 STT verbonden - wacht op spraak...")
            
            # Track last sent to avoid duplicates
            last_interim_text = ""
            
            async for response in await client.streaming_recognize(
                requests=request_generator()
            ):
                for result in response.results:
                    if result.alternatives:
                        transcript = result.alternatives[0].transcript.strip()
                        is_final = result.is_final
                        confidence = result.alternatives[0].confidence if is_final else 0
                        
                        if not transcript:
                            continue
                        
                        logger.info(
                            f"STT {'[FINAL]' if is_final else '[interim]'}: "
                            f"'{transcript}' (conf: {confidence:.2f})"
                        )
                        
                        # For live subtitles: send ALL transcripts immediately
                        # Only skip if current interim is prefix of last sent
                        if transcript != last_interim_text and not last_interim_text.startswith(transcript):
                            await transcript_queue.put(transcript)
                            logger.debug(f"Transcript queued: '{transcript}'")
                            last_interim_text = transcript
            
            # Reset backoff on successful session
            backoff = INITIAL_BACKOFF_SECONDS
            
        except Exception as e:
            logger.error(f"STT stream error: {e}", exc_info=True)
            
            if shutdown_event.is_set():
                break
            
            logger.info(f"Reconnecting in {backoff} seconds...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
    
    logger.info("STT Stream Task stopped")


# ============================================================================
# Refinement Task (Gemini)
# ============================================================================

async def refinement_task(
    transcript_queue: asyncio.Queue,
    output_queue: asyncio.Queue,
    shutdown_event: asyncio.Event,
):
    """
    Consume transcripts and shorten long sentences using Gemini via Vertex AI.
    """
    logger.info("Refinement Task started")
    
    # Initialize Vertex AI
    vertexai.init(project=GOOGLE_PROJECT_ID, location=GOOGLE_LOCATION)
    model = GenerativeModel("gemini-2.0-flash-001")
    logger.info(f"Vertex AI initialized: project={GOOGLE_PROJECT_ID}, location={GOOGLE_LOCATION}")
    
    while not shutdown_event.is_set():
        try:
            # Wait for transcript with timeout
            try:
                transcript = await asyncio.wait_for(
                    transcript_queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue
            
            word_count = len(transcript.split())
            logger.info(f"Refining transcript: '{transcript}' ({word_count} words)")
            
            if word_count > SHORTEN_THRESHOLD:
                logger.debug(f"Sentence exceeds {SHORTEN_THRESHOLD} words, shortening...")
                
                prompt = (
                    "Herschrijf deze ondertitel beknopt in het Nederlands. "
                    "Maximaal 10 woorden. Geef alleen de tekst.\n\n"
                    f"{transcript}"
                )
                
                try:
                    response = await asyncio.to_thread(
                        model.generate_content, prompt
                    )
                    refined = response.text.strip()
                    logger.info(f"Refined: '{transcript}' -> '{refined}'")
                except Exception as e:
                    logger.error(f"Gemini error: {e}", exc_info=True)
                    refined = transcript  # Fallback to original
            else:
                refined = transcript
                logger.debug(f"No refinement needed: '{refined}'")
            
            await output_queue.put(refined)
            
        except Exception as e:
            logger.error(f"Refinement error: {e}", exc_info=True)
    
    logger.info("Refinement Task stopped")


# ============================================================================
# YouTube CC Output Task
# ============================================================================

async def youtube_output_task(
    output_queue: asyncio.Queue,
    shutdown_event: asyncio.Event,
):
    """
    Dispatch refined subtitles to YouTube Caption API.
    """
    logger.info("YouTube Output Task started")
    
    if not YOUTUBE_CAPTION_URL:
        logger.warning("YOUTUBE_CAPTION_URL not set - output will be logged only")
    
    async with aiohttp.ClientSession() as session:
        while not shutdown_event.is_set():
            try:
                # Wait for output with timeout
                try:
                    text = await asyncio.wait_for(
                        output_queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                timestamp = datetime.now(timezone.utc).isoformat()
                payload = f"{timestamp} {text}"
                
                logger.info(f"OUTPUT: {payload}")
                
                if YOUTUBE_CAPTION_URL:
                    try:
                        async with session.post(
                            YOUTUBE_CAPTION_URL,
                            data=payload,
                            headers={"Content-Type": "text/plain"},
                        ) as resp:
                            logger.debug(
                                f"YouTube CC response: {resp.status} {resp.reason}"
                            )
                            if resp.status != 200:
                                body = await resp.text()
                                logger.warning(f"YouTube CC error body: {body}")
                    except Exception as e:
                        logger.error(f"YouTube CC request failed: {e}", exc_info=True)
                
            except Exception as e:
                logger.error(f"Output error: {e}", exc_info=True)
    
    logger.info("YouTube Output Task stopped")


# ============================================================================
# Main
# ============================================================================

async def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("OBS AI Subtitle Pipeline Starting")
    logger.info("=" * 60)
    
    # Log configuration
    logger.info(f"Project ID: {GOOGLE_PROJECT_ID}")
    logger.info(f"Vertex AI Location: {GOOGLE_LOCATION}")
    logger.info(f"STT Language: {STT_LANGUAGE_CODE}")
    logger.info(f"Shorten Threshold: {SHORTEN_THRESHOLD} words")
    logger.info(f"Audio RMS Threshold: {MIN_RMS_THRESHOLD}")
    logger.info(f"YouTube URL: {'SET' if YOUTUBE_CAPTION_URL else 'NOT SET'}")
    
    # Queues
    audio_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    transcript_queue: asyncio.Queue = asyncio.Queue()
    output_queue: asyncio.Queue = asyncio.Queue()
    
    # Shutdown event
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    
    # Setup signal handlers
    def signal_handler():
        logger.info("Shutdown signal received")
        shutdown_event.set()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    # Start audio producer (in thread)
    audio_producer = AudioProducer(audio_queue, loop)
    audio_thread = threading.Thread(target=audio_producer.start, daemon=True)
    audio_thread.start()
    
    # Give audio producer time to start
    await asyncio.sleep(0.5)
    
    # Start async tasks
    tasks = [
        asyncio.create_task(stt_stream_task(audio_queue, transcript_queue, shutdown_event)),
        asyncio.create_task(refinement_task(transcript_queue, output_queue, shutdown_event)),
        asyncio.create_task(youtube_output_task(output_queue, shutdown_event)),
    ]
    
    logger.info("All tasks started, pipeline running...")
    
    # Wait for shutdown
    await shutdown_event.wait()
    
    logger.info("Shutting down...")
    
    # Stop audio producer
    audio_producer.stop()
    
    # Cancel tasks
    for task in tasks:
        task.cancel()
    
    await asyncio.gather(*tasks, return_exceptions=True)
    
    logger.info("=" * 60)
    logger.info("OBS AI Subtitle Pipeline Stopped")
    logger.info("=" * 60)



if __name__ == "__main__":
    # Select audio device BEFORE starting async loop (so input() works)
    selected_device_id = None
    
    p = pyaudio.PyAudio()
    info = p.get_host_api_info_by_index(0)
    num_devices = info.get("deviceCount", 0)
    
    input_devices = []
    print("\n=== Beschikbare audio inputs ===")
    for i in range(num_devices):
        dev_info = p.get_device_info_by_index(i)
        if dev_info.get("maxInputChannels", 0) > 0:
            input_devices.append((i, dev_info.get('name')))
            print(f"  [{len(input_devices) - 1}] {dev_info.get('name')}")
    
    p.terminate()
    
    if not input_devices:
        print("ERROR: Geen audio input devices gevonden!")
        sys.exit(1)
    
    # Check for env var first
    env_device = os.getenv("AUDIO_DEVICE", "").strip()
    selected_idx = 0
    
    if env_device:
        # Try to match by name (partial match)
        for idx, (dev_id, name) in enumerate(input_devices):
            if env_device.lower() in name.lower():
                selected_idx = idx
                break
        else:
            # Try as index
            try:
                selected_idx = int(env_device)
            except ValueError:
                pass
    elif len(input_devices) > 1:
        # Interactive selection - this now works because we're not in async
        try:
            choice = input(f"\nKies input device [0-{len(input_devices)-1}] (Enter voor 0): ").strip()
            if choice:
                selected_idx = int(choice)
                if selected_idx < 0 or selected_idx >= len(input_devices):
                    selected_idx = 0
        except (ValueError, KeyboardInterrupt):
            print("\nUsing default device 0")
            selected_idx = 0
    
    selected_device_id, device_name = input_devices[selected_idx]
    print(f"\n→ Gebruik: {device_name}\n")
    
    # Store in env for the async code to pick up
    os.environ["_SELECTED_AUDIO_DEVICE_ID"] = str(selected_device_id)
    
    asyncio.run(main())
