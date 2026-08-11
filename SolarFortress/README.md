# Solar Fortress

A clone of the classic "Star Castle" arcade game, built with a local LLM using a proper spec and staged development plan.

## The process

Develop a detailed specification, and break it into development stages: [SolarFortress.md](SolarFortress.md)

(Note that we don't try to one-shot the prompt, as it's too long and complicated)

## The result

A complete, playable game, coded up in an hour or two!

See the result in the [LLM Battle 5](https://www.youtube.com/watch?v=zzOh6e3dm7w) video on YouTube!

## The contenders

- Qwen 3.6 35B A3B - failed!
- Qwen 3.6 27B - succeeded!
- Qwen 3.6 27B "Fable Fusion" - failed!
- Muse Glimmer - check back tomorrow

See the results in each contender's dedicated subdirectory!

```
cd <resultDir>
python3 SolarFortress.py
```

Supported options:

```
  -h, --help       show this help message and exit
  --width WIDTH    Starting window width (minimum 640, default 800)
  --height HEIGHT  Starting window height (minimum 480, default 600)
  --fullscreen     Start in fullscreen mode.
  --test           Run a quick smoke-test and exit.
  --nosound        Disable all audio.
```

