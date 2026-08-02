# dots.tts

These are support scripts for use with [dots.tts](https://github.com/rednote-hilab/dots.tts) in a local environment.

- `server.py` - a simple REST API around `dots.tts`:
  - `POST /synthesize` clones a voice given reference audio, returns the requested text in that cloned voice.
  - `GET /health` simple health check to confirm server is up
- `speak.sh` - A simple bash script to hit the REST API (quick and dirty version).
- `speak.py` - A newer and much-improved version of speak.sh... use this one, it's highly configurable.
- `parse.py` - A simple Python script to transcribe audio from an OpenAI-compatible transcription server.

## Using server.py

This custom Python script can stand up a nice REST API in front of a locally-running `dots.tts` server,
and allow you to make TTS requests from shell scripts or code (example scripts provided above).

To set this up, copy `server.py` to your `dots.tts` project directory:

```
<dots.tts directory>/apps/rest_api/server.py
```

Then you can start it with uvicorn:

```
uvicorn apps.rest_api.server:app --host 0.0.0.0 --port 8181
```

Now you should be able to make REST requests against the `/synthesize` endpoint.
Refer to `speak.sh` or `speak.py` above for simple bash and Python examples.

The [TalkWithMe](https://github.com/scorbo2/TalkWithMe) application makes heavy
use of `server.py` for speech synthesis, if you want a more detailed example.
