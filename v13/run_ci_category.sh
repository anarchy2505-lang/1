#!/usr/bin/env bash
set -euo pipefail
CATEGORY="${1:?category required}"
rm -rf workspace "vanta-category-${CATEGORY}" "vanta-category-${CATEGORY}.zip"
mkdir -p workspace/tools workspace/assets/data workspace/assets/glb workspace/reports
python - "$CATEGORY" <<'PY'
import base64,hashlib,json,pathlib,sys,zlib
category=sys.argv[1];root=pathlib.Path('workspace');parts=[pathlib.Path('v13/registry.parts/registry.part01').read_text().strip()]
for i in range(2,8):
 p=pathlib.Path(f'v13/registry.parts/registry.part{i:02d}.txt');lines=p.read_text().splitlines();parts.append(''.join(lines[1:]).strip())
packed=''.join(parts)
assert len(packed)==26184 and hashlib.sha256(packed.encode()).hexdigest()=='b1e00c396a171eb15603ec03bcfd08504b1377f5c826112baa4a92dfedfa64d8'
raw=zlib.decompress(base64.b64decode(packed));assert hashlib.sha256(raw).hexdigest()=='c389886985364ee04500f0f6f023fc2c8c73a00cca83641da19a8f49a27e2f80'
items=json.loads(raw);assert len(items)==341
registry={'version':'1.3','items':items,'summary':{'count':len(items),'category':category,'categoryCount':sum(v['category']==category for v in items.values())}}
(root/'assets/data/product-reference-registry-v13.json').write_text(json.dumps(registry,ensure_ascii=False,indent=2),encoding='utf-8')
name_map={k:{'oldName':v.get('name'),'newName':v.get('confirmed_name') or v.get('name'),'status':v.get('status'),'sourceUrl':v.get('url')} for k,v in items.items() if v['category']==category}
(root/f'assets/data/catalog-name-map-v13-{category}.json').write_text(json.dumps(name_map,ensure_ascii=False,indent=2),encoding='utf-8')
print(registry['summary'])
PY
cp v13/scrape_product_photos_fast_v13.py workspace/tools/
cp v13/build_photo_assets_standalone_v13.py workspace/tools/
(
 cd workspace
 python tools/scrape_product_photos_fast_v13.py --category "$CATEGORY" --workers 8 --max-images 3
 python tools/build_photo_assets_standalone_v13.py --category "$CATEGORY"
 python - "$CATEGORY" <<'PY'
import json,pathlib,sys
cat=sys.argv[1];root=pathlib.Path('.');reg=json.loads((root/'assets/data/product-reference-registry-v13.json').read_text())['items'];expected=sum(v['category']==cat for v in reg.values());glbs=list((root/'assets/glb'/cat).glob('*.glb'));photos=json.loads((root/'assets/data/photo-source-manifest-v13.json').read_text());items={k:v for k,v in photos['items'].items() if k.startswith(cat+'/')}
if len(glbs)!=expected:raise SystemExit(f'{cat}: expected {expected} GLBs got {len(glbs)}')
report={'result':'PASS','category':cat,'expected':expected,'glbFiles':len(glbs),'itemsWithCapturedPhotos':sum(bool(x.get('images')) for x in items.values()),'capturedPhotoFiles':sum(len(x.get('images',[])) for x in items.values()),'captured3dFiles':sum(len(x.get('captured3d',[])) for x in items.values()),'totalGlbBytes':sum(p.stat().st_size for p in glbs),'items':items}
(root/f'reports/QA_VANTA_V13_{cat}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k!='items'},indent=2))
(root/f'assets/data/photo-source-manifest-v13-{cat}.json').write_text(json.dumps({'version':'1.3','category':cat,'items':items},ensure_ascii=False,indent=2),encoding='utf-8')
PY
)
OUT="vanta-category-${CATEGORY}"
mkdir -p "$OUT/assets/glb" "$OUT/assets/data" "$OUT/assets/library" "$OUT/reports"
cp -R "workspace/assets/glb/${CATEGORY}" "$OUT/assets/glb/"
cp -R "workspace/assets/reference-photos/${CATEGORY}" "$OUT/assets/reference-photos-${CATEGORY}"
[ ! -d "workspace/assets/library/captured-3d-v13/${CATEGORY}" ] || cp -R "workspace/assets/library/captured-3d-v13/${CATEGORY}" "$OUT/assets/library/captured-3d-v13-${CATEGORY}"
cp "workspace/assets/data/photo-source-manifest-v13-${CATEGORY}.json" "$OUT/assets/data/"
cp "workspace/assets/data/catalog-name-map-v13-${CATEGORY}.json" "$OUT/assets/data/"
cp "workspace/reports/QA_VANTA_V13_${CATEGORY}.json" "$OUT/reports/"
zip -0 -r "vanta-category-${CATEGORY}.zip" "$OUT" >/dev/null
