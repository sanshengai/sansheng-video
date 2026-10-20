"""Bounded, source-backed keyword discovery for Lemo creative mechanisms.

This is a bilingual index, not semantic understanding or an aesthetic scorer.
Only positive, curated aliases affect mechanism ranking; warnings never do.
"""
import hashlib
import json
from pathlib import Path
import re

INDEX = Path(__file__).parent / 'vendor/lemo-opuscar/creative-index.json'
SOURCES = INDEX.with_name('creative-sources.json')
SOURCES_SHA256 = '1077cd0393fecb685e5f92d962b8ce2fb525a7d0fe2df3bc5299e4b2c94eea93'


def load(catalog):
    raw=SOURCES.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SOURCES_SHA256:
        raise ValueError('creative source bindings fingerprint differs')
    bindings=json.loads(raw)
    if (bindings.get('schema')!='lemo-creative-sources/1'
            or bindings.get('catalog_revision')!=catalog['revision']):
        raise ValueError('creative source bindings revision/schema mismatch')
    data=json.loads(INDEX.read_text(encoding='utf-8'))
    if not isinstance(data,dict):
        raise ValueError('creative index must be an object')
    rows=data.get('styles')
    if (data.get('schema')!='lemo-creative-index/1'
            or data.get('catalog_revision')!=catalog['revision']
            or data.get('research_revision')!=bindings['research_revision']
            or not isinstance(data.get('basis'),str) or not data['basis'].strip()
            or not isinstance(rows,list)):
        raise ValueError('creative index revision/schema mismatch')
    if any(not isinstance(r,dict) or not isinstance(r.get('slug'),str) for r in rows):
        raise ValueError('creative index contains malformed style cards')
    ids=[r.get('slug') for r in rows]
    if len(set(ids))!=len(ids) or set(ids)!={r['slug'] for r in catalog['styles']}:
        raise ValueError('creative index style coverage differs from source catalog')
    source_paths={r['slug']:{f['path']:f for f in r['files']} for r in catalog['styles']}
    for row in rows:
        if (not isinstance(row.get('aliases'),list) or not row['aliases']
                or any(not isinstance(a,str) or not a.strip() for a in row['aliases'])
                or any(not isinstance(row.get(k),str) or not row[k].strip()
                       for k in ('use_for','mechanism','visual','sound','needs','limits'))
                or not isinstance(row.get('refs'),list) or not row['refs']):
            raise ValueError('incomplete creative card: '+str(row.get('slug')))
        for ref in row['refs']:
            if not isinstance(ref,str) or not re.fullmatch(
                    r'styles/'+re.escape(row['slug'])+r'/[^\n]+:[1-9]\d*',ref):
                raise ValueError('creative card has unbound source reference: '+row['slug'])
            path,line=ref.rsplit(':',1)
            if path not in source_paths[row['slug']]:
                raise ValueError('creative card source absent from pinned catalog: '+row['slug'])
            bound=bindings['files'].get(path)
            if (not bound or bound['sha256']!=source_paths[row['slug']][path]['sha256']
                    or int(line)>bound['lines']):
                raise ValueError('creative card source line/fingerprint differs: '+row['slug'])
    return data


def positive_query(query):
    if not isinstance(query,str) or not query.strip():
        raise ValueError('nonempty search query required')
    # A deliberately small keyword grammar, not a general negation parser.
    # Whole explicitly negative clauses are not used as positive suggestions.
    clauses=re.split(r'[，,。；;\n]',query.lower())
    positive=[c.strip() for c in clauses
              if c.strip() and not re.match(r'^(不要|不用|避免|不想|别用|exclude\b|avoid\b)',c.strip())]
    return ' '.join(positive)


def alias_match(alias,query):
    if re.fullmatch(r'[a-z0-9 _-]+',alias):
        return bool(re.search(r'(?<![a-z0-9])'+re.escape(alias)+r'(?![a-z0-9])',query))
    return alias in query


def rank(catalog,query):
    q=positive_query(query)
    data=load(catalog)
    by_id={r['slug']:r for r in data['styles']}
    ranked=[]
    for original in catalog['styles']:
        card=by_id[original['slug']]
        matches=[a for a in card['aliases'] if alias_match(a,q)]
        # Specific names are still useful and must remain stable entry points.
        names=[str(original.get(k,'')).lower() for k in ('slug','en','cn')]
        exact=[name for name in names if name and alias_match(name,q)]
        score=12*len(exact)+sum(4 if len(a)>=4 else 2 for a in matches)
        if not score:
            continue
        row={k:v for k,v in original.items() if k not in ('files','shots','refs')}
        row['creative']={k:card[k] for k in ('use_for','mechanism','needs')}
        row['matched_terms']=list(dict.fromkeys(exact+matches))
        ranked.append((score,original['slug'],row))
    ranked.sort(key=lambda r:(-r[0],r[1]))
    # Return fewer than three when only a weak incidental tag matched.
    if ranked:
        ranked=[r for r in ranked if r[0]>=ranked[0][0]*0.3]
    return {'research_revision':data['research_revision'],
            'results':[r[2] for r in ranked[:3]],
            'retrieval_basis':'curated bilingual keywords; references, not execution or quality approval'}


def inspect(catalog,slug):
    data=load(catalog)
    card=next((r for r in data['styles'] if r['slug']==slug),None)
    if card is None:
        raise ValueError('unknown style slug')
    return {'revision':catalog['revision'],'research_revision':data['research_revision'],
            'kind':'creative-mechanism',**{k:v for k,v in card.items() if k!='aliases'},
            'evidence_limit':data['basis']}
