# Community benchmark on NVIDIA RTX PRO 4000 Blackwell

Measured on 2026-11-18 with `tools/strata_bench.py` (suite 1, 3 runs per test, medians with ranges). Speeds are the engine's own timings; first-token times are measured by the client over HTTP. Speed only: no correctness check was run.

## Hardware and software

- GPU and VRAM: NVIDIA RTX PRO 4000 Blackwell, 24 GiB VRAM
- CPU: Intel(R) Core(TM) Ultra 7 270K Plus (24 cores, 24 threads); installed RAM: 125.1 GiB; storage: nvme0n1 WD_BLACK SN7100 2TB nvme
- OS: Linux 7.0.0-42-generic; GPU driver: 595.99.02; CUDA (driver supports up to): 13.2; engine built for CUDA 13.0
- Strata: project 0.1.59.1, commit dbb2d168; engine 0.1.58
- GPU detail (after the run, near idle): power_limit_w=145.00, power_draw_w=143.88, pcie=gen5 x8, pstate=P1, temp_c=78
- Background workloads: not recorded (GPU power limit/draw read above)

## Model and configuration

- Model and quantization: qwen3.8-flash-next-iq3_s
- Context: 131072 tokens; parallel slots: 1
- Settings: the install's own configuration, unchanged; thinking off for the suite; temperature 0

```text
strata --pack iq3_s --native Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf --ple-gguf Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00002-of-00002.gguf --expert-profile expert-profile.bin --expert-cache auto --prefill auto --spec 4 --spec-min-p 0.5 --mtp rt --max-context 131072 --kv int8 --ple-io ram --kv-resident 32768 --vision --vram-reserve-mib 700 --pool-workers 15
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
| short chat | 46 (43-51) | 0 | 100 (100-100) | 9 | not measured | 103.1 (96.6-137.0) | 0.36 (0.33-0.40) |
| 4K prompt, fresh | 4019 (4019-4019) | 0 (0-0) | 24 cap | 3 | 2148.2 (2126.8-2150.7) | not measured | 1.89 (1.89-1.91) |
| 16K prompt, fresh | 16058 (16058-16058) | 0 (0-0) | 24 cap | 3 | 2755.1 (2748.7-2795.0) | not measured | 5.85 (5.77-5.86) |
| agent session, follow-up turns | 13797 (13740-13816) at the last turn | see below | up to 64 | 3 | see below | 116.6 (95.9-141.9) | 1.56 (1.07-1.96) |

Ranges are the lowest and highest of the runs; `Runs` counts requests that returned a token.

### Agent session (conversation cache)

Cache hit over the follow-up turns: 70.0 % (69.9-70.0); earlier-turn tokens read again per session: 73 (2-74) (earlier turns that the cache did not hold; the 12946 (12946-12946) new tokens of the files are read once); first turn (nothing cached) first token: 1.09 s (0.97-1.18).

| Turn (run 1) | Prompt tokens | Reused | Read | Prompt tok/s | First token (s) | Decode tok/s |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 609 | 0 | 609 | 643.1 | 0.966 | 79.9 |
| 1 | 4043 | 623 | 3420 | 1899.1 | 1.821 | 109.2 |
| 2 | 5576 | 4107 | 1469 | 1329.4 | 1.123 | 121.5 |
| 3 | 8822 | 5640 | 3182 | 1797.7 | 1.79 | 128.5 |
| 4 | 11016 | 8848 | 2168 | 1619.6 | 1.358 | 133.1 |
| 5 | 13740 | 11031 | 2709 | 1717.7 | 1.597 | 95.9 |

Per-request data: `results.json`. Engine log lines from the start: `engine-log-excerpt.txt` (when this run started the server).

## Correctness and limitations

Not measured: this is a speed suite. The conversation uses the model's own replies, so token counts differ a little between runs. Machine details come from the server, `nvidia-smi`/`rocm-smi` and the OS; background load is not recorded. Total time of the suite: 72 s.
