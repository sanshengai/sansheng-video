#!/usr/bin/env python3
"""Resolve configured original logos and preview their visible bounds. Pillow is optional."""
import argparse
import hashlib
import json
from pathlib import Path


def resolve(profile, background="dark", role="corner", variant=None):
    profile = Path(profile).resolve()
    brand = json.loads(profile.read_text()).get("brand", {})
    variants = brand.get("variants", {})
    if not isinstance(variants, dict):
        raise ValueError("brand.variants must be an object")
    if variant is not None:
        if variant not in variants:
            raise ValueError("unknown brand variant")
        candidates = [(variant, variants[variant])]
    else:
        candidates = [(name, item) for name, item in variants.items()
                      if item.get("background") == background and role in item.get("roles", [])]
    if len(candidates) > 1:
        raise ValueError("multiple brand variants match; select --variant")
    if candidates:
        name, item = candidates[0]
        if item.get("background") != background or role not in item.get("roles", []):
            raise ValueError("variant does not support requested background/role")
        if item.get("type") not in {"full", "symbol"}:
            raise ValueError("variant type must be full or symbol")
        value = item.get("file")
        kind = item["type"]
    elif variants:
        raise ValueError("no configured brand variant for background/role")
    else:
        name = "logo_on_dark" if background == "dark" else "logo"
        value, kind = brand.get(name), "unspecified_legacy"
    if not isinstance(value, str) or not value:
        raise ValueError("brand logo file missing from configuration")
    asset = (profile.parent / value).resolve()
    if not asset.is_file() or not asset.stat().st_size:
        raise ValueError(f"brand file missing or empty: {asset}")
    return {"variant": name, "type": kind, "file": str(asset),
            "sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
            "background": background, "role": role}


def preview(profile, output, canvas=(1920, 1080), visible_width=.15, margin=.04,
            background="dark", role="corner", variant=None):
    from PIL import Image, ImageDraw
    result = resolve(profile, background, role, variant)
    if len(canvas) != 2 or any(type(n) is not int or n <= 0 for n in canvas):
        raise ValueError("canvas needs positive integer width and height")
    if not 0 < visible_width < 1 or not 0 <= margin < .5:
        raise ValueError("invalid visible width or design margin")
    with Image.open(result["file"]) as original:
        logo = original.convert("RGBA")
    bounds = logo.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError("logo is fully transparent")
    cw, ch = canvas
    scale = cw * visible_width / (bounds[2] - bounds[0])
    lw, lh = max(1, round(logo.width * scale)), max(1, round(logo.height * scale))
    if lw * lh > 64_000_000:
        raise ValueError("transparent padding would produce excessive scaling; inspect original")
    actual_w, actual_h = (bounds[2] - bounds[0]) * scale, (bounds[3] - bounds[1]) * scale
    mx, my = round(cw * margin), round(ch * margin)
    if actual_w + 2 * mx > cw or actual_h + 2 * my > ch:
        raise ValueError("logo visible bounds exceed canvas design margins")
    if role == "ending":
        x, y = (cw - actual_w) / 2, (ch - actual_h) / 2
    else:
        x, y = cw - mx - actual_w, my
    destination = (round(x - bounds[0] * scale), round(y - bounds[1] * scale))
    surface = Image.new("RGBA", canvas, "#11171b" if background == "dark" else "#f7f8fa")
    surface.alpha_composite(logo.resize((lw, lh), Image.Resampling.LANCZOS), destination)
    draw = ImageDraw.Draw(surface)
    draw.rectangle((mx, my, cw - mx - 1, ch - my - 1), outline="#77838d", width=1)
    output = Path(output)
    if output.exists():
        raise ValueError("preview exists; choose a new output")
    output.parent.mkdir(parents=True, exist_ok=True)
    surface.convert("RGB").save(output)
    result.update(canvas=list(canvas), source_size=list(logo.size), alpha_bounds=list(bounds),
                  visible_box=[round(x), round(y), round(x + actual_w), round(y + actual_h)],
                  visible_width_fraction=visible_width, design_margin=margin,
                  preview=str(output.resolve()), status="layout_preview_not_contrast_or_platform_approval")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    parser.add_argument("--background", choices=["dark", "light"], default="dark")
    parser.add_argument("--role", default="corner")
    parser.add_argument("--variant")
    parser.add_argument("--preview", type=Path)
    parser.add_argument("--canvas", type=int, nargs=2, default=[1920, 1080])
    parser.add_argument("--visible-width", type=float, default=.15)
    parser.add_argument("--margin", type=float, default=.04)
    args = parser.parse_args()
    result = (preview(args.profile, args.preview, args.canvas, args.visible_width, args.margin,
                      args.background, args.role, args.variant) if args.preview
              else resolve(args.profile, args.background, args.role, args.variant))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
