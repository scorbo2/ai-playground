# KittenTTS server implementation review

Two independent attempts to add KittenTTS 2 support using the `new-tts-engine` skill.
Both pass their full test suites (**Qwen**: 304 tests, **Kimi**: 319 tests).

---

## Qwen — Grade: A−

### Correct

| Point | Detail |
|---|---|
| `KITTENTTS_DEVICE` defaults to `"auto"` | AGENTS.md explicitly requires this; the snapshot test pops `device` because it's machine-dependent |
| KittenTTS2 guard uses `hasattr(model, "decode_presets")` | AGENTS.md specifies this attribute exactly |
| Unknown `voice` returns **422** | AGENTS.md: *"422 with a sample list"* — Kimi sends 400 |
| `preset` is runtime-validated (not a hardcoded `Literal`) | Presets are checkpoint data from `config.json`, not guaranteed across repos |
| Has `envs/kittentts/` (Phase 6 complete) | Kimi has no env |
| Stub mirrors the real constructor signature (`decoder`/`weights`/`device` kwargs) | More faithful to the real `kittenml` package |
| Temperature `ge=0.0`, `top_p ge=0.0` | More permissive and correct; the engine accepts 0.0 |
| `seed_everything()` called before each generation | Consistent with other servers |

### Missing

- `use_reference_prompt` — a real, named parameter in the engine's `generate()` signature that Kimi exposes
- `repetition_penalty` and `use_emotion` — real `advanced=` knobs Kimi surfaces as first-class fields and forwards
- No maximum-duration check (`_check_reference_audio` only validates the 5 s floor, not the 30 s ceiling)
- `preset` has `default=None` — Kimi's `Literal["stable", "expressive"]` with default `"stable"` is more user-friendly and matches the engine's own known presets

---

## Kimi — Grade: B

### Correct

| Point | Detail |
|---|---|
| Exposes `use_reference_prompt` | Real `generate()` parameter (`use_reference_prompt=None`) |
| Exposes `repetition_penalty`, `use_emotion` | Real `advanced=` knobs with correct defaults (1.1 and `None`) |
| Max-duration check in `_check_reference_audio` | Engine docs say 5–30 s; Kimi enforces the ceiling |
| `max_duration_s: 30.0` in capabilities | Correct |
| `Literal["stable", "expressive"]` with default `"stable"` | These are the known presets; advertising the enum helps clients |
| More complete test suite (319 vs 304) | Covers whitespace transcript/voice, 30 s rejection, all advanced-field forwarding, `use_emotion` |

### Wrong

| Bug | Why it matters |
|---|---|
| `KITTENTTS_DEVICE` defaults to `"cuda"`, no `"auto"` option | Breaks on any CPU-only machine; AGENTS.md mandates `auto` |
| Unknown voice returns **400** | AGENTS.md and the server's own docstring say 422 |
| KittenTTS2 guard checks `advanced_options` | AGENTS.md says `decode_presets`; both exist on a KittenTTS2 object, but the spec is explicit |
| Temperature `ge=0.3`, `top_p ge=0.5` | Unnecessarily restrictive; the engine accepts 0.0 |
| No `envs/kittentts/` | Incomplete per the skill's Phase 6 checklist |

---

## Verdict: merge Qwen

Qwen is architecturally correct where it counts: it gets device handling right (the most
operationally impactful difference), uses the right HTTP status codes, follows AGENTS.md
on the legacy-guard attribute, and is the only implementation with a uv environment.

Kimi's device default and 400→422 errors are actual bugs — they would silently break on
CPU-only machines and give clients the wrong status codes. Qwen's gaps are omissions, not
bugs.

### Before merging, bring these across from Kimi

1. Add `use_reference_prompt`, `repetition_penalty`, and `use_emotion` fields to
   `SynthesisRequest` and forward them in the `generate()` call.
2. Add the `> 30 s` ceiling check to `_check_reference_audio` and `max_duration_s: 30.0`
   to `CAPABILITIES`.
3. Change `preset` default from `None` to `"stable"` (consider adding the `Literal` or at
   least documenting the known values in the field description).
4. Port the extra tests: whitespace validators for `reference_text` and `voice`, the 30 s
   rejection test, and the full advanced-forwarding coverage for `repetition_penalty` and
   `use_emotion`.
