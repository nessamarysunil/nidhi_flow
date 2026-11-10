import os
import sys
import io
import wave
import struct
import math
import requests
from dotenv import load_dotenv

# Load .env
load_dotenv()

GNANI_API_KEY = os.getenv("GNANI_API_KEY", "")
GNANI_STT_URL = os.getenv("GNANI_STT_URL", "https://api.vachana.ai/stt/v3")

def generate_dummy_wav(duration_sec: float = 1.0, sample_rate: int = 16000, freq: float = 440.0) -> bytes:
    """
    Synthesizes a 1-second 16kHz mono dummy .wav clip using the standard wave module.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)             # 1 channel (mono)
        wf.setsampwidth(2)             # 2 bytes per sample (16-bit)
        wf.setframerate(sample_rate)   # 16000 Hz
        num_samples = int(duration_sec * sample_rate)
        for i in range(num_samples):
            # 440 Hz tone with 50% amplitude
            val = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * freq * i / sample_rate))
            wf.writeframesraw(struct.pack("<h", val))
    buf.seek(0)
    return buf.read()

def run_gate_test():
    print("=" * 60)
    print("       SabhaLedger - Day 0 Gate Test for Gnani AI STT       ")
    print("=" * 60)
    print(f"Target STT URL : {GNANI_STT_URL}")
    masked_key = f"{GNANI_API_KEY[:8]}...{GNANI_API_KEY[-4:]}" if len(GNANI_API_KEY) > 12 else "(not set)"
    print(f"API Key ID     : {masked_key}")

    if not GNANI_API_KEY:
        print("\n[FAIL] GNANI_API_KEY is not defined in .env or environment!")
        return 1

    print("\n1. Synthesizing 1-second 16kHz mono WAV clip...")
    wav_bytes = generate_dummy_wav(duration_sec=1.0, sample_rate=16000, freq=440.0)
    print(f"   Generated dummy audio: {len(wav_bytes)} bytes.")

    print("\n2. Sending POST request to Gnani Vachana STT v3...")
    headers = {
        "X-API-Key-ID": GNANI_API_KEY
    }
    data = {
        "model": "prisma-v3.0",
        "language_code": "ml-IN,en-IN",
        "output_format": "transcribe"
    }
    files = {
        "audio_file": ("dummy_16khz.wav", wav_bytes, "audio/wav")
    }

    try:
        response = requests.post(
            GNANI_STT_URL,
            headers=headers,
            data=data,
            files=files,
            timeout=30
        )

        print(f"\n3. Response Status Code: {response.status_code}")
        print("   Response Body:")
        print("   " + response.text[:500])

        if response.status_code == 200:
            print("\n[PASS] Day 0 Gate Test Passed: HTTP 200 OK received from Gnani AI STT endpoint.")
            return 0
        else:
            print(f"\n[FAIL] Day 0 Gate Test Failed: Received HTTP {response.status_code}.")
            return 1

    except requests.exceptions.RequestException as e:
        print(f"\n[FAIL] Day 0 Gate Test Failed due to connection/network error:")
        print(f"   {str(e)}")
        print("\nNote: Ensure network connectivity is enabled (or run outside sandbox).")
        return 2

if __name__ == "__main__":
    sys.exit(run_gate_test())

