# dots.tts

These are support scripts for use with [dots.tts](https://github.com/rednote-hilab/dots.tts) in a local environment.

- `server.py` - a simple REST API around `dots.tts`:
  - `POST /synthesize` clones a voice given reference audio, returns the requested text in that cloned voice.
  - `GET /health` simple health check to confirm server is up
  - `POST /parse` accepts base64-encoded audio and transcribes it using `whisper` on the server. Handles language detection automatically.
- `speak.sh` - A simple bash script to hit the REST API (quick and dirty version).
- `speak.py` - A newer and much-improved version of speak.sh... use this one, it's highly configurable.
- `parse.py` - A wrapper around the `/parse` endpoint... turns an audio file into a transcript, with language detection.

