"""Validate review/output binding; does not establish human review truth."""
from pathlib import Path
import json
from production_timeline import digest as sha256

def verify_production_review(project, output, review):
    """Bind the existing final review to current production evidence, if any."""
    project, output = Path(project).resolve(), Path(output).resolve()
    if not output.is_relative_to(project):
        raise ValueError("交付文件须在项目内")
    if not isinstance(review, dict) or review.get("approved") is not True or review.get("output_sha256") != sha256(output):
        raise ValueError("缺少对当前交付文件的真实验收记录")
    evidence = {}
    build = project / "derived/production-build.json"
    if build.exists():
        from production_timeline import check
        check(build)
        evidence["production_build_sha256"] = sha256(build)
        if review.get("production_build_sha256") != evidence["production_build_sha256"]:
            raise ValueError("验收记录未绑定当前 production build")
    elif "production_build_sha256" in review:
        raise ValueError("验收记录绑定的 production build 缺失")
    automatic = output.with_suffix(".render.json")
    explicit = review.get("render_receipt")
    receipt = None
    if explicit is not None:
        if not isinstance(explicit, str) or not explicit:
            raise ValueError("render_receipt 须为项目内回执路径")
        receipt = (project / explicit).resolve()
        if not receipt.is_relative_to(project):
            raise ValueError("render receipt 须在项目内")
        if automatic.exists() and receipt != automatic.resolve():
            raise ValueError("render receipt 与交付文件对应回执不一致")
    elif automatic.exists():
        receipt = automatic.resolve()
    if receipt is not None:
        from render_production import verify
        verified = verify(receipt)
        data = json.loads(receipt.read_text())
        if Path(verified["output"]).resolve() != output or data.get("output_sha256") != sha256(output):
            raise ValueError("render receipt 不属于当前交付文件")
        if build.exists() and Path(data["build_path"]).resolve() != build.resolve():
            raise ValueError("render receipt 不属于当前 production build")
        evidence["render_receipt_sha256"] = sha256(receipt)
        if review.get("render_receipt_sha256") != evidence["render_receipt_sha256"]:
            raise ValueError("验收记录未绑定当前 render receipt")
        evidence["render_receipt"] = str(receipt)
        from production_sound_review import current_plan, verify_listening
        plan, plan_sha = current_plan(data["build_path"])
        if data.get("sound_review_plan_sha256") != plan_sha:
            raise ValueError("成片须重新导出并绑定声音试听计划，旧技术回执不等于试听通过")
        if data.get("verification", {}).get("has_audio") is True:
            evidence["audio_review"] = verify_listening(review, plan, plan_sha, sha256(output))
    elif "render_receipt_sha256" in review:
        raise ValueError("验收记录缺少对应 render receipt")
    return evidence
