#!/usr/bin/env python3
"""
parse.py - Audio parsing wrapper for server.py's STT whisper-based parser.

Accepts an audio file, base64-encodes it, and POSTs it to the server's /parse
endpoint. On success, prints the detected language followed by the transcribed
text.

Usage:
    parse.py audio.wav
    parse.py audio.wav --server http://localhost:8000/tts
"""

import argparse
import base64
import json
import os
import sys
import urllib.request
import urllib.error


def parse_args():
    parser = argparse.ArgumentParser(
        description="Parse audio using the dots.tts REST API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default server
  %(prog)s recording.wav

  # Override server
  %(prog)s recording.wav --server http://localhost:8000/tts
        """
    )
    parser.add_argument("audio_file", help="Path to input audio file")
    parser.add_argument("--server", default="http://saturn-lm:8181/parse", help="API server URL")
    return parser.parse_args()


def load_audio_base64(path: str) -> str:
    """Read the audio file and return its base64-encoded contents."""
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
        # Server responded with an error — print whatever it gave us
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        print(f"Error: HTTP {e.code} - {e.reason}", file=sys.stderr)
        if body:
            print(f"Response: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        # Server is unreachable — generic fallback
        print(f"Error: Failed to connect to server: {e.reason}", file=sys.stderr)
        sys.exit(1)


def main():
    args = parse_args()

    # Validate input file exists
    if not os.path.isfile(args.audio_file):
        print(f"Error: Audio file not found: {args.audio_file}", file=sys.stderr)
        sys.exit(1)

    # Prepare payload
    audio_b64 = load_audio_base64(args.audio_file)
    payload = {"audio_base64": audio_b64}

    # Send request
    response = send_request(args.server, payload)

    # Extract and print results
    language = response.get("language", "unknown")
    text = response.get("text", "")

    if not text:
        print("Error: No transcribed text in server response", file=sys.stderr)
        print(json.dumps(response, indent=2), file=sys.stderr)
        sys.exit(1)

    print(f"Language: {language}")
    print(text)


if __name__ == "__main__":
    main()
