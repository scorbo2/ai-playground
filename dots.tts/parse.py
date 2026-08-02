#!/usr/bin/env python3
"""
parse.py - Audio transcription client for an OpenAI-compatible STT endpoint.

Sends an audio file as multipart/form-data to the server's
/v1/audio/transcriptions endpoint. On success, prints the detected language
followed by the transcribed text.

Usage:
    parse.py audio.wav
    parse.py audio.wav --server http://localhost:5000/v1/audio/transcriptions
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error


def parse_args():
    parser = argparse.ArgumentParser(
        description="Transcribe audio using an OpenAI-compatible STT endpoint.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default server
  %(prog)s recording.wav

  # Override server
  %(prog)s recording.wav --server http://localhost:5000/v1/audio/transcriptions
        """
    )
    parser.add_argument("audio_file", help="Path to input audio file")
    parser.add_argument(
        "--server",
        default="http://saturn-lm:5000/v1/audio/transcriptions",
        help="API server URL (default: http://saturn-lm:5000/v1/audio/transcriptions)",
    )
    return parser.parse_args()


AUDIO_MIME_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".opus": "audio/opus",
    ".m4a": "audio/mp4",
    ".webm": "audio/webm",
    ".aac": "audio/aac",
    ".pcm": "audio/pcm",
}
DEFAULT_AUDIO_MIME = "audio/unknown"


def guess_audio_mime(file_path: str) -> str:
    """
    Derive a MIME type from the file extension. Falls back to a generic
    'audio/unknown' if the extension is unrecognized or absent.
    """
    _, ext = os.path.splitext(file_path)
    return AUDIO_MIME_TYPES.get(ext.lower(), DEFAULT_AUDIO_MIME)


def build_multipart_boundary() -> str:
    # A simple unique boundary string. No need to import uuid for this.
    return f"----dots-tts-boundary-{os.getpid()}"


def encode_multipart(file_path: str, boundary: str) -> tuple[bytes, str]:
    """
    Build a multipart/form-data body with two fields:
      - file: the audio file (read raw, not base64)
      - response_format: the string "json"

    Returns (body_bytes, content_type_header_value).
    """
    filename = os.path.basename(file_path)
    mime_type = guess_audio_mime(file_path)

    with open(file_path, "rb") as f:
        file_data = f.read()

    lines: list[bytes] = []

    # --file field
    lines.append(f"--{boundary}\r\n".encode())
    lines.append(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
    )
    lines.append(f"Content-Type: {mime_type}\r\n".encode())
    lines.append(b"\r\n")
    lines.append(file_data)
    lines.append(b"\r\n")

    # --response_format field
    lines.append(f"--{boundary}\r\n".encode())
    lines.append(
        b'Content-Disposition: form-data; name="response_format"\r\n'
    )
    lines.append(b"\r\n")
    lines.append(b"json\r\n")

    # Closing boundary
    lines.append(f"--{boundary}--\r\n".encode())

    body = b"".join(lines)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def send_request(server_url: str, file_path: str) -> dict:
    boundary = build_multipart_boundary()
    body, content_type = encode_multipart(file_path, boundary)

    req = urllib.request.Request(
        server_url,
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            if resp.status != 200:
                body_text = resp.read().decode("utf-8", errors="replace")
                print(f"Error: Server returned HTTP {resp.status}", file=sys.stderr)
                print(f"Response: {body_text}", file=sys.stderr)
                sys.exit(1)
            return json.loads(resp.read())

    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace") if e.fp else ""
        print(f"Error: HTTP {e.code} - {e.reason}", file=sys.stderr)
        if body_text:
            print(f"Response: {body_text}", file=sys.stderr)
        sys.exit(1)

    except urllib.error.URLError as e:
        print(f"Error: Failed to connect to server: {e.reason}", file=sys.stderr)
        sys.exit(1)


def main():
    args = parse_args()

    # Validate input file exists
    if not os.path.isfile(args.audio_file):
        print(f"Error: Audio file not found: {args.audio_file}", file=sys.stderr)
        sys.exit(1)

    # Send request
    response = send_request(args.server, args.audio_file)

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
