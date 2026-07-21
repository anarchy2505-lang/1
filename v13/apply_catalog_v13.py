from __future__ import annotations
import json, re, shutil, hashlib
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
VERIFIED=ROOT/'verified_links_final.json'
verified=json.loads(VERIFIED.read_text(encoding='utf-8'))
changes={k:v for k,v in verified.items() if v.get('confirmed_name') and v['confirmed_name']!=v['name']}

# update JSON recursively with category context

def update_obj(obj, category=None, key_hint=None):
    count=0
    if isinstance(obj, dict):
        # category groups
        for cat in ['case','cpu','motherboard','gpu','cooler','ram','storage','psu','fans','cables']:
            if cat in obj and isinstance(obj[cat], dict):
                c=update_obj(obj[cat], cat, cat); count+=c
        # keyed item, e.g. case/o11evo
        if key_hint in verified and isinstance(obj,dict):
            rec=verified[key_hint]
            if obj.get('name') != rec['confirmed_name']:
                obj['name']=rec['confirmed_name']; count+=1
            if 'officialUrl' in obj or rec.get('url'):
                obj['officialUrl']=rec.get('url') or obj.get('officialUrl')
            if rec.get('reference_image'):
                obj['referenceImage']=rec['reference_image']
            obj['verificationStatus']=rec.get('status')
        # item with category/id
        item_cat=obj.get('category') or category
        item_id=obj.get('id')
        project_id=f'{item_cat}/{item_id}' if item_cat and item_id else None
        if project_id in verified:
            rec=verified[project_id]
            if obj.get('name') != rec['confirmed_name']:
                obj['name']=rec['confirmed_name']; count+=1
            if 'title' in obj and obj.get('title')==rec.get('name'):
                obj['title']=rec['confirmed_name']
            if 'officialUrl' in obj or rec.get('url'):
                obj['officialUrl']=rec.get('url') or obj.get('officialUrl')
            if 'productUrl' in obj or rec.get('url'):
                obj['productUrl']=rec.get('url') or obj.get('productUrl')
            if rec.get('reference_image'):
                obj['referenceImage']=rec['reference_image']
                if 'image' in obj and not obj.get('image'):
                    obj['image']=rec['reference_image']
            obj['verificationStatus']=rec.get('status')
            obj['verifiedSourceUrl']=rec.get('url')
        # recurse all values, avoid redoing category keys already but okay
        for k,v in list(obj.items()):
            if isinstance(v,(dict,list)):
                count += update_obj(v, category, k)
    elif isinstance(obj,list):
        for v in obj:
            count += update_obj(v, category, None)
    return count

json_files=[]
for p in ROOT.rglob('*.json'):
    if any(part in {'backup-before-v1.2','reports'} for part in p.parts):
        continue
    try:
        d=json.loads(p.read_text(encoding='utf-8-sig'))
    except Exception:
        continue
    n=update_obj(d)
    if n or p.name in {'catalog-v07.json','catalog-v08.json','catalog-v09.json','catalog-source.json','product-media-v10.json','library-index-v10.json'}:
        p.write_text(json.dumps(d,ensure_ascii=False,separators=(',',':') if p.name.startswith('catalog-v0') else None,indent=None if p.name.startswith('catalog-v0') else 2),encoding='utf-8')
        json_files.append((str(p.relative_to(ROOT)),n))

# direct text replacements in JS/MD/TXT/BAT where names are embedded
text_ext={'.js','.md','.txt','.html','.py','.bat','.ps1'}
text_files=[]
for p in ROOT.rglob('*'):
    if not p.is_file() or p.suffix.lower() not in text_ext:
        continue
    if any(part.startswith('backup-') for part in p.parts):
        continue
    try: text=p.read_text(encoding='utf-8-sig')
    except Exception: continue
    orig=text
    for project_id,rec in changes.items():
        text=text.replace(rec['name'],rec['confirmed_name'])
    if text!=orig:
        p.write_text(text,encoding='utf-8')
        text_files.append(str(p.relative_to(ROOT)))

# regenerate JS wrappers from JSON exactly
pairs=[('assets/data/library-index-v10.json','assets/data/library-index-v10.js','window.VANTA_LIBRARY_INDEX'),
       ('assets/data/product-media-v10.json','assets/data/product-media-v10.js','window.VANTA_PRODUCT_MEDIA')]
for j,jsp,var in pairs:
    d=json.loads((ROOT/j).read_text(encoding='utf-8-sig'))
    (ROOT/jsp).write_text(var+'='+json.dumps(d,ensure_ascii=False,separators=(',',':'))+';\n',encoding='utf-8')

# verified registry included in project
registry={
 'version':'1.3',
 'generatedAt':datetime.now(timezone.utc).isoformat(),
 'purpose':'Authoritative product-name and photo-source registry for VANTA photo-backed 3D asset production.',
 'items':verified,
 'summary':{
   'count':len(verified),
   'renamed':len(changes),
   'exact':sum(v['status'].startswith('verified-exact') for v in verified.values()),
   'normalized':sum(v['status']=='verified-normalized' for v in verified.values()),
   'invalidOriginalNames':sum(v['status']=='invalid-generated-name' for v in verified.values()),
 }
}
(ROOT/'assets/data/product-reference-registry-v13.json').write_text(json.dumps(registry,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'assets/data/product-reference-registry-v13.js').write_text('window.VANTA_PRODUCT_REFERENCE_REGISTRY='+json.dumps(registry,ensure_ascii=False,separators=(',',':'))+';\n',encoding='utf-8')

# report
report={
 'version':'1.3', 'pass':'Verified Catalog Names', 'renamedCount':len(changes),
 'renames':[{'projectId':k,'oldName':v['name'],'newName':v['confirmed_name'],'status':v['status'],'url':v['url']} for k,v in changes.items()],
 'jsonFiles':json_files,'textFiles':text_files
}
(ROOT/'reports/catalog-name-corrections-v13.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
md=['# VANTA v1.3 — исправление каталога','',f'Исправлено наименований: **{len(changes)}**.','', '| ID | Было | Стало | Статус |','|---|---|---|---|']
for k,v in changes.items(): md.append(f"| `{k}` | {v['name']} | {v['confirmed_name']} | {v['status']} |")
(ROOT/'reports/catalog-name-corrections-v13.md').write_text('\n'.join(md)+'\n',encoding='utf-8')

print('renamed',len(changes),'json files',len(json_files),'text files',len(text_files))
for row in json_files: print('JSON',row)
