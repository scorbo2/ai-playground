#!/usr/bin/env python3
"""
speak.py - TTS wrapper for dots.tts REST API

A configurable Python replacement for speak.sh. Maintains the original API contract
while adding CLI arguments for full customization.

Usage:
    speak.py "Your text to speak"
    speak.py "Hello" --language es --steps 20 --output-file result.wav
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error


def parse_args():
    parser = argparse.ArgumentParser(
        description="Synthesize speech using the dots.tts REST API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use all defaults (backward compatible with speak.sh)
  %(prog)s "Hello, how are you?"

  # Custom language, steps, and save to file
  %(prog)s "Bonjour le monde" --language fr --steps 20 --output-file greeting.wav

  # Override reference files and server
  %(prog)s "Test" --ref-audio my_voice.wav --ref-audio-transcript my_voice.txt --server http://localhost:8000/tts
        """
    )
    parser.add_argument("text", help="Text string to synthesize")
    parser.add_argument("--language", default="en", help="Language code (default: en)")
    parser.add_argument("--server", default="http://saturn-lm:8181/synthesize", help="API server URL")
    parser.add_argument("--ref-audio", default="/home/scorbett/audio/reference.wav", help="Path to reference audio WAV file")
    parser.add_argument("--ref-audio-transcript", default="/home/scorbett/audio/reference.txt", help="Path to reference transcript text file")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for generation (default: null)")
    parser.add_argument("--steps", type=int, default=12, choices=range(1, 31), metavar="[1-30]", help="Number of generation steps (default: 12)")
    parser.add_argument("--output-file", default="", help="Path to save output WAV. If empty, plays via aplay and discards")
    return parser.parse_args()


def validate_files(ref_audio: str, ref_transcript: str):
    if not os.path.isfile(ref_audio):
        print(f"Error: Reference audio file not found or not readable: {ref_audio}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(ref_transcript):
        print(f"Error: Reference transcript file not found or not readable: {ref_transcript}", file=sys.stderr)
        sys.exit(1)


def load_and_clean_transcript(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    # Collapses all whitespace (including newlines) into single spaces and trims
    return " ".join(raw.split())


def load_audio_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def send_request(server_url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        server_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            if resp.status != 200:
                body = resp.read().decode("utf-8", errors="replace")
                print(f"Error: Server returned HTTP {resp.status}", file=sys.stderr)
                print(f"Response: {body}", file=sys.stderr)
                sys.exit(1)
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"Error: HTTP {e.code} - {e.reason}", file=sys.stderr)
        if e.fp:
            print(f"Response: {e.read().decode('utf-8', errors='replace')}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: Failed to connect to server: {e.reason}", file=sys.stderr)
        sys.exit(1)


def handle_output(audio_bytes: bytes, output_file: str):
    if output_file:
        if os.path.exists(output_file):
            try:
                resp = input(f"File '{output_file}' already exists. Overwrite? [y/N] ").strip().lower()
                if resp != "y":
                    print("Aborted.")
                    return
            except EOFError:
                print("\nAborted (no stdin).")
                return
        with open(output_file, "wb") as f:
            f.write(audio_bytes)
        print(f"✅ Saved audio to {output_file}")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        subprocess.run(["aplay", "-q", tmp_path], check=True)
    except FileNotFoundError:
        print("Error: 'aplay' not found. Please install ALSA utilities or use --output-file to save.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error: aplay failed with code {e.returncode}", file=sys.stderr)
        sys.exit(1)
    finally:
        os.unlink(tmp_path)


def main():
    args = parse_args()

    # Validate input files exist
    validate_files(args.ref_audio, args.ref_audio_transcript)

    # Prepare payload components
    prompt_text = load_and_clean_transcript(args.ref_audio_transcript)
    audio_b64 = load_audio_base64(args.ref_audio)

    payload = {
        "text": args.text,
        "prompt_text": prompt_text,
        "audio_base64": audio_b64,
        "seed": args.seed,
        "num_steps": args.steps,
        "language": args.language
    }

    # Send request
    print("📡 Sending synthesis request...")
    response = send_request(args.server, payload)

    # Extract audio
    if "audio_base64" not in response or not response["audio_base64"]:
        print("Error: No 'audio_base64' field in server response", file=sys.stderr)
        print(json.dumps(response, indent=2), file=sys.stderr)
        sys.exit(1)

    audio_bytes = base64.b64decode(response["audio_base64"])

    # Handle output
    print("🔊 Processing audio...")
    handle_output(audio_bytes, args.output_file)


if __name__ == "__main__":
    main()

