# Qwen3-TTS

This is a custom REST API that can be stood up in front of a `Qwen3-TTS` instance.
This is very similar to the one for [dots.tts](../dots.tts/server.py).

There are two endpoints:
- `GET /health` verifies that the server is up and reports which model is in use.
- `POST /synthesize` accepts a Json object containing reference audio/transcript, and the text to synthesize.
  The return is a Json object containing base64-encoded audio.

## Using server.py

To set this up, copy `server.py` to your `Qwen3-TTS` project directory:

```
<Qwen3-TTS directory>/server.py
```

Then you can start it with uvicorn:

```
uvicorn server:app --host 0.0.0.0 --port 7777
```

Now you should be able to make REST requests against the `/synthesize` endpoint.
Refer to `speak.sh` or `speak.py` in the [dots.tts directory](../dots.tts) for simple bash and Python examples.

The [TalkWithMe](https://github.com/scorbo2/TalkWithMe) application makes heavy
use of `server.py` for speech synthesis, if you want a more detailed example.

