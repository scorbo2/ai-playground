# Community benchmark on NVIDIA GeForce RTX 4070

Measured on 2026-11-18 with `tools/strata_bench.py` (suite 1, 3 runs per test, medians with ranges). Speeds are the engine's own timings; first-token times are measured by the client over HTTP. Speed only: no correctness check was run.

## Hardware and software

- GPU and VRAM: NVIDIA GeForce RTX 4070, 12 GiB VRAM
- CPU: 13th Gen Intel(R) Core(TM) i7-13700KF (16 cores, 24 threads); installed RAM: 125.6 GiB; storage: sda     WDC WD8002FZWX-00BKUA0 sata; nvme1n1 WD Blue SN5100 2TB     nvme; nvme2n1 CT1000P3PSSD8          nvme; nvme0n1 ORICO                  nvme
- OS: Linux 7.0.0-42-generic; GPU driver: 595.99.02; CUDA (driver supports up to): 13.2; engine built for CUDA 13.0
- Strata: project 0.1.61, commit c7757280; engine 0.1.62
- GPU detail (after the run, near idle): power_limit_w=200.00, power_draw_w=77.35, pcie=gen1 x16, pstate=P2, temp_c=56
- Background workloads: not recorded (GPU power limit/draw read above)

## Model and configuration

- Model and quantization: qwen3.8-flash-next-iq3_s
- Context: 131072 tokens; parallel slots: 1
- Settings: the install's own configuration, unchanged; thinking off for the suite; temperature 0

```text
strata --pack iq3_s --native Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf --ple-gguf Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00002-of-00002.gguf --expert-profile expert-profile.bin --expert-cache auto --prefill auto --spec 4 --mtp rt --max-context 131072 --kv int8 --ple-io ram --kv-resident 32768 --vision --spec-min-p 0.70 --pcie-frac 0.00 --adapt-every 1 --adapt-swaps 80 --adapt-decay 0.97
```

## Method

Run by `python tools/strata_bench.py` against the HTTP API of a Strata server (started by the benchmark from the install configuration); model loading is not timed. One warm-up chat and a 1K prompt are discarded first. Every prompt starts with a unique tag, so the conversation cache cannot help the fresh-prompt tests.

- short chat: the three questions of `tools/ab_engine.py`, up to 100 new tokens, 3 runs
- 4K / 16K prompts: generated word lists sized by a calibration request, 24 new tokens, 3 fresh prompts each
- agent session: system prompt and four tools, then 5 turns that each add about 1500 words of a project file and continue from the model's own earlier answers (the way agent clients resend a conversation), 64 new tokens per turn, 3 sessions; the cache numbers come from the answer's usage (`cached_tokens`) and timings (`prompt_n`)
- concurrency (when run): N requests sent at the same moment, total tokens over the wall time of the burst, latency over all requests

## Results

| Configuration | Actual prompt tokens | Reused tokens | Generated tokens | Runs | Prompt tok/s median and range | Decode tok/s median and range | TTFT seconds median and range |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| short chat | 46 (43-51) | 0 | 100 (100-100) | 9 | not measured | 28.8 (22.6-41.2) | 0.84 (0.72-1.02) |
| 4K prompt, fresh | 4019 (4019-4019) | 0 (0-0) | 24 cap | 3 | 130.9 (128.9-134.3) | not measured | 30.76 (29.98-31.23) |
| 16K prompt, fresh | 16058 (16058-16058) | 0 (0-0) | 24 cap | 3 | 192.0 (188.9-192.1) | not measured | 83.69 (83.63-85.05) |
| agent session, follow-up turns | 13162 (13143-13196) at the last turn | see below | up to 64 | 3 | see below | 35.2 (13.1-38.8) | 20.27 (15.88-30.41) |

Ranges are the lowest and highest of the runs; `Runs` counts requests that returned a token.

### Agent session (conversation cache)

Cache hit over the follow-up turns: 69.2 % (69.2-69.2); earlier-turn tokens read again per session: 5 (5-5) (earlier turns that the cache did not hold; the 12324 (12324-12324) new tokens of the files are read once); first turn (nothing cached) first token: 12.43 s (12.31-12.83).

| Turn (run 1) | Prompt tokens | Reused | Read | Prompt tok/s | First token (s) | Decode tok/s |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 609 | 0 | 609 | 49.7 | 12.309 | 22.0 |
| 1 | 3432 | 627 | 2805 | 135.7 | 20.719 | 28.7 |
| 2 | 4965 | 3495 | 1470 | 92.2 | 16.008 | 28.2 |
| 3 | 8193 | 5028 | 3165 | 105.1 | 30.216 | 35.2 |
| 4 | 10267 | 8236 | 2031 | 118.9 | 17.144 | 38.8 |
| 5 | 13162 | 10304 | 2858 | 138.7 | 20.666 | 38.6 |

Per-request data: `results.json`. Engine log lines from the start: `engine-log-excerpt.txt` (when this run started the server).

## Correctness and limitations

Not measured: this is a speed suite. The conversation uses the model's own replies, so token counts differ a little between runs. Machine details come from the server, `nvidia-smi`/`rocm-smi` and the OS; background load is not recorded. Total time of the suite: 781 s.
