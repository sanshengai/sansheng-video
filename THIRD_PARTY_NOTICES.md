# Third-party notices

Original project code and instructions are MIT. The following adapted portions retain their upstream terms; the MIT root license does not replace Apache-2.0 terms on those portions.

| File | Upstream | Locked commit | Terms |
|---|---|---|---|
| scripts/vendor/lemo-opuscar/catalog.json | lemomo-ai/lemo-opuscar (style catalog + OPUSCAR 98) | d33bdea74eeecde3922b0fbad227f0d3dc7afe75 | Pinned LICENSE/README state MIT (full text alongside catalog); original author article states CC BY 4.0 for style documents/films. Retain Lemomo / LemoLab attribution, source link and modifications; see references/lemo-opuscar.md |
| scripts/vendor/motion-prompt/cli.mjs; examples/motion-sfx/kit-lp.js and ripple.js | showheyohtaki/motion-prompt | 770eefb7091cc725ab0eb6d4ef5cbf28b28e282c | MIT, full copyright/license in scripts/vendor/motion-prompt/LICENSE; CLI unchanged, example adapted with modifications in its README |
| scripts/validate_edl.py and tests/test_edl_validation.py | guigulaoshi/music-video-director-skill, mvd/validate.py | 06abf674e936eefd69f053759f673e3c72f71e2e | MIT, full copyright/license in LICENSES/music-video-director-MIT.txt |
| scripts/normalize_loudness.py | KyaniteLabs/mcp-video, mcp_video/engine_audio_normalize.py | ba9d64048f095688ee3d3b18aa1d3f1fa7a0cd7e | Apache-2.0, full license in LICENSES/mcp-video-Apache-2.0.txt |
| scripts/check_merge_compat.py | KyaniteLabs/mcp-video, mcp_video/merge_guardrails.py | ba9d64048f095688ee3d3b18aa1d3f1fa7a0cd7e | Apache-2.0, same license |

Adaptations remove upstream application dependencies, expose standalone CLI operations and add voiceover-led EDL and media checks. Further portability changes are documented in CHANGELOG. Original source attribution is retained in each file.

## Separately installed runtime dependencies

- [HyperFrames](https://github.com/heygen-com/hyperframes), Apache-2.0; adapter tested against 0.8.72.
- [GSAP](https://gsap.com/standard-license), standard license; used by project-authored animations, not bundled.
- [Playwright](https://github.com/microsoft/playwright), Apache-2.0; browser verification only, not bundled.
- [FFmpeg](https://ffmpeg.org/legal.html), license depends on the installed build; executable not bundled.

Fonts, music, footage and generated assets must carry their own usage rights. Research credits for method-only references are in references/sources.md; the selected Motion Prompt example code and a Lemo reference catalog are distributed with their notices; upstream example media and full production installers are not bundled.
