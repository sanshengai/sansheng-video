# Case mechanisms: two A/B scene drawings

`scene.js` is original canvas artwork for two bounded experiments. It adapts
mechanisms described in pinned prompt references; it does not reproduce or
validate the upstream videos. No third-party video, audio, font or demo code is
bundled here. Choose and license those dependencies separately.

| Kind | Same content in A/B | A | B |
| --- | --- | --- | --- |
| `teaching` | A ball, tables, `on / under / between` | Separate states with short fades | Continuous ball motion and table separation |
| `demo` | Actual query results, selection, detail | Separate result/detail layouts | Selected card retains its identity as it expands |

These drawings are optional examples, not a default production template.
They do not test character acting, generated lighting or native video audio.

## Caller contract

Create a project-local HTML composition with one `1280x720` canvas. Load the
project's licensed font as `CaseRounded` (or deliberately use the system font
fallback), local GSAP, exported `derived/events.js`, configuration, then
`scene.js`. Set the composition duration to the timeline duration. The script
registers `window.__timelines.root` only after fonts are ready. Each frame is a
function of absolute video time, so forward, reverse and cold seeking must agree.

Example configuration; use real CLI results for `results` in a demo:

```javascript
window.caseExperiment = {
  kind: "demo", // or "teaching"
  variant: "B", // or "A"
  query: "功能演示 布局 声音点缀",
  results: searchOutput.results,
  musicCredit: "The selected track's required attribution"
};
```

`searchOutput` comes from `scripts/video_case_reference.py search`. The demo
uses each result's `id`, `title_zh` and `content_kind`; keep its visible label
that the UI is a demonstration using actual search data. Do not claim it is a
recording of a deployed product.

Export one ordinary production timeline, with these visual event IDs:

| Kind | Example duration | Event starts, seconds |
| --- | --- | --- |
| teaching | 22.4 | `state-on: 2.6`, `state-under: 8`, `state-between: 13`, `state-recap: 18.2` |
| demo | 15.4 | `show-results: 3.4`, `show-detail: 7.4`, `finish: 12.4` |

For teaching captions, use the existing verified narration evidence and export
`voice-0` through `voice-4` with their real block text and timings. The example
times leave reading windows; they are not word-level forced alignment.

Follow [the existing production workflow](../../references/production.md) for
timeline export, dependencies, asset locks, SFX application, rendering and
narration/music mixing. Only executed source, font and media files enter build
dependencies. Prompt references are documentation, not runtime dependencies.

## What to inspect

- At the teaching transition, the ball must travel around the table edge before
  reaching `under`; pause on each relationship long enough to understand it.
- Around demo `7.4–8.2s`, retire secondary cards before showing detail text.
  Detail text is clipped inside the growing selected card and appears late in
  the expansion. The initial simultaneous fade caused overlapping text in a
  local sampled-frame inspection; the current drawing separates those tasks.
- Check intermediate frames, not just settled layouts. Inspect at mobile size.
- Use the same audio identities, wording, dimensions, runtime and frame rate
  within each pair. If testing sound alignment, disclose that extra variable:
  file-start alignment versus measured amplitude-peak alignment is a bounded
  experiment, not proof of a perceptual improvement. A measured peak can differ
  from perceptual onset or the right dramatic accent.
- Listen to the final render for tone, masking and relative volume. An audio
  track, a loudness value or an SFX receipt does not prove the sound is suitable.

Record technical checks, sampled-frame review, full playback, listening and
user preference separately. This example does not auto-approve any of them.
