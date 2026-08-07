# DeepSeek Live JSON Probe (Phase A.2)

- Time (UTC): `2026-08-07T05:10:43.165412+00:00`
- Model: `deepseek-chat` @ `https://api.deepseek.com`
- Generation backend: `mock` (must stay mock)
- Overall: **PASS**
- Raw evidence JSON: `runs/_deepseek_live_probe/probe_20260807_051043.json`

| Case | CreativePlan | Storyboard | OK | Notes |
|---|---|---|---|---|
| default_brief | pass | pass | yes | - |
| script_mode | pass | pass | yes | - |
| brief_with_reference | pass | pass | yes | - |

## Notes
- API key is redacted; only prefix stored in evidence JSON.
- This probe validates structured JSON only; it does not claim FLUX/H3 quality.
- `.env` `LLM_MODE` restored to `mock` after the probe.
- First probe failed on all storyboards: DeepSeek returned `"shot_id": 1` (int). Fixed by coercing `Shot.shot_id` to `str` and tightening the storyboard system prompt; second probe is the PASS recorded above.
