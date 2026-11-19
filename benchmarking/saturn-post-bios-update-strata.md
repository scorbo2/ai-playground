# Community benchmark on NVIDIA GeForce RTX 4070

Measured on 2026-11-19 with `tools/strata_bench.py` (suite 1, 3 runs per test, medians with ranges). Speeds are the engine's own timings; first-token times are measured by the client over HTTP. Speed only: no correctness check was run.

## Hardware and software

- GPU and VRAM: NVIDIA GeForce RTX 4070, 12 GiB VRAM
- CPU: 13th Gen Intel(R) Core(TM) i7-13700KF (16 cores, 24 threads); installed RAM: 125.6 GiB; storage: sda     WDC WD8002FZWX-00BKUA0 sata; nvme0n1 WD Blue SN5100 2TB     nvme; nvme1n1 CT1000P3PSSD8          nvme; nvme2n1 ORICO                  nvme
- OS: Linux 7.0.0-43-generic; GPU driver: 595.99.02; CUDA (driver supports up to): 13.2; engine built for CUDA 13.0
- Strata: project 0.1.61, commit c7757280; engine 0.1.62
- GPU detail (after the run, near idle): power_limit_w=200.00, power_draw_w=108.16, pcie=gen4 x16, pstate=P2, temp_c=48
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
| short chat | 46 (43-51) | 0 | 100 (100-100) | 9 | not measured | 46.7 (43.4-57.6) | 0.66 (0.55-0.79) |
| 4K prompt, fresh | 4019 (4019-4019) | 0 (0-0) | 24 cap | 3 | 1252.6 (1250.7-1254.8) | not measured | 3.24 (3.23-3.25) |
| 16K prompt, fresh | 16058 (16058-16058) | 0 (0-0) | 24 cap | 3 | 1492.1 (1490.1-1497.2) | not measured | 10.79 (10.76-10.81) |
| agent session, follow-up turns | 13172 (13141-13187) at the last turn | see below | up to 64 | 3 | see below | 53.0 (45.8-60.5) | 3.18 (2.47-3.35) |

Ranges are the lowest and highest of the runs; `Runs` counts requests that returned a token.

### Agent session (conversation cache)

Cache hit over the follow-up turns: 69.2 % (69.2-69.2); earlier-turn tokens read again per session: 5 (5-5) (earlier turns that the cache did not hold; the 12324 (12324-12324) new tokens of the files are read once); first turn (nothing cached) first token: 2.41 s (2.18-2.41).

| Turn (run 1) | Prompt tokens | Reused | Read | Prompt tok/s | First token (s) | Decode tok/s |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 609 | 0 | 609 | 283.8 | 2.176 | 35.3 |
| 1 | 3434 | 629 | 2805 | 877.3 | 3.229 | 45.8 |
| 2 | 4967 | 3497 | 1470 | 602.9 | 2.47 | 47.7 |
| 3 | 8195 | 5030 | 3165 | 954.3 | 3.353 | 48.8 |
| 4 | 10261 | 8230 | 2031 | 754.4 | 2.727 | 54.0 |
| 5 | 13141 | 10283 | 2858 | 886.9 | 3.254 | 58.2 |

Per-request data: `results.json`. Engine log lines from the start: `engine-log-excerpt.txt` (when this run started the server).

## Correctness and limitations

Not measured: this is a speed suite. The conversation uses the model's own replies, so token counts differ a little between runs. Machine details come from the server, `nvidia-smi`/`rocm-smi` and the OS; background load is not recorded. Total time of the suite: 142 s.
