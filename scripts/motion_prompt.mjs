#!/usr/bin/env node
// MIT upstream CLI, pinned code and matching data; see vendor/motion-prompt/UPSTREAM.json.
const pin = '770eefb7091cc725ab0eb6d4ef5cbf28b28e282c';
process.env.MOTION_PROMPT_BASE ||= `https://raw.githubusercontent.com/showheyohtaki/motion-prompt/${pin}/api/v1`;
await import('./vendor/motion-prompt/cli.mjs');
