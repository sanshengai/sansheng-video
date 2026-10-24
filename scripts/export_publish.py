#!/usr/bin/env python3
"""Export an accepted delivery to the neutral publishing contract; never renders/uploads."""
import argparse
import json
from pathlib import Path
import re
from package_delivery import digest


def export(delivery_path, targets_path, output, *, job_id='video-publish'):
    delivery_path = Path(delivery_path).resolve()
    root = delivery_path.parent
    report = json.loads(delivery_path.read_text(encoding='utf-8'))
    targets = json.loads(Path(targets_path).read_text(encoding='utf-8')).get('targets')
    if report.get('kind') != 'video-delivery/1' or report.get('review_status') != 'user_accepted' or not report.get('review_source'):
        raise ValueError('需要绑定作者实际反馈的已接受交付回执；不伪造接受状态')
    if report.get('technical', {}).get('full_decode') is not True:
        raise ValueError('交付回执缺完整解码证据')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', job_id):
        raise ValueError('非法 job_id')
    assets = []
    for ident, kind, field in (('video','video','video'), ('cover','image','poster')):
        rel = report.get(field)
        if not isinstance(rel, str) or Path(rel).is_absolute():
            raise ValueError('交付文件必须是回执目录下的相对路径')
        path = (root/rel).resolve()
        expected = report.get('files', {}).get(rel)
        if not path.is_relative_to(root) or not path.is_file() or not path.stat().st_size or digest(path) != expected:
            raise ValueError(f'交付文件已改变、缺失或越界：{field}')
        assets.append(dict(id=ident,kind=kind,path=rel,sha256=expected))
    if not isinstance(targets, list) or not targets:
        raise ValueError('targets 不能为空')
    for target in targets:
        if not all(target.get(k) for k in ('id','platform','account','endpoint')) or target.get('content_type') != 'video':
            raise ValueError('每个目标需明确平台、账号、终点和 video 类型')
        target.setdefault('title', report['suggested_title'])
        target.setdefault('text', report['summary'])
        target['asset_ids'] = ['video','cover']
        target['cover_asset_id'] = 'cover'
        target['document_id'] = 'delivery-receipt'
    manifest = dict(schema_version=1,job_id=job_id,producer='sansheng-video',content_status='final',source_root=str(root),
                    documents=[dict(id='delivery-receipt',path=delivery_path.name,format='text',sha256=digest(delivery_path))],
                    assets=assets,media_slots=[],targets=targets)
    path = Path(output).resolve()
    value = json.dumps(manifest,ensure_ascii=False,indent=2)+'\n'
    if path.exists() and path.read_text(encoding='utf-8') != value:
        raise ValueError('发布包已存在且内容不同；使用新的修订路径')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(value,encoding='utf-8')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('delivery')
    parser.add_argument('--targets', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--job-id', default='video-publish')
    args = parser.parse_args()
    try:
        path = export(args.delivery,args.targets,args.output,job_id=args.job_id)
        print(json.dumps(dict(ok=True,manifest=str(path)),ensure_ascii=False))
        return 0
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps(dict(ok=False,error=str(exc)),ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
