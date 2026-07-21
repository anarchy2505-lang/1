#!/usr/bin/env bash
set -euo pipefail
rm -rf workspace VANTA-v1.3-Verified-Photo-Assets VANTA-v1.3-Verified-Photo-Assets.zip
mkdir -p workspace/tools workspace/assets/data workspace/assets/glb workspace/reports
python - <<'PY'
import base64, json, pathlib, zlib
root=pathlib.Path('workspace')
items=json.loads(zlib.decompress(base64.b64decode(pathlib.Path('v13/verified_links_final.json.zlib.b64').read_text())))
registry={'version':'1.3','purpose':'Verified names and product-photo sources for VANTA assets','items':items,'summary':{'count':len(items),'renamed':sum(v.get('confirmed_name') and v.get('confirmed_name')!=v.get('name') for v in items.values()),'exact':sum(str(v.get('status','')).startswith('verified-exact') for v in items.values()),'normalized':sum(v.get('status')=='verified-normalized' for v in items.values()),'invalidOriginalNames':sum(v.get('status')=='invalid-generated-name' for v in items.values())}}
(root/'assets/data/product-reference-registry-v13.json').write_text(json.dumps(registry,ensure_ascii=False,indent=2),encoding='utf-8')
name_map={k:{'oldName':v.get('name'),'newName':v.get('confirmed_name') or v.get('name'),'status':v.get('status'),'sourceUrl':v.get('url')} for k,v in items.items()}
(root/'assets/data/catalog-name-map-v13.json').write_text(json.dumps(name_map,ensure_ascii=False,indent=2),encoding='utf-8')
PY
cp v13/scrape_product_photos_v13.py workspace/tools/
cp v13/build_photo_assets_standalone_v13.py workspace/tools/
sed -i 's/(1800,1800)/(1280,1280)/g; s/quality=92/quality=86/g' workspace/tools/scrape_product_photos_v13.py
(
  cd workspace
  python tools/scrape_product_photos_v13.py --workers 6 --max-images 3
  python tools/build_photo_assets_standalone_v13.py
  python - <<'PY'
import json,pathlib
root=pathlib.Path('.')
registry=json.loads((root/'assets/data/product-reference-registry-v13.json').read_text())['items']
photos=json.loads((root/'assets/data/photo-source-manifest-v13.json').read_text())
glbs=list((root/'assets/glb').glob('*/*.glb'))
missing=[]
for key in registry:
    cat,pid=key.split('/',1)
    if not (root/'assets/glb'/cat/f'{pid}.glb').exists():missing.append(key)
if len(registry)!=341 or len(glbs)!=341 or missing:raise SystemExit(f'Invalid output registry={len(registry)} glb={len(glbs)} missing={missing[:10]}')
report={'result':'PASS','catalogItems':len(registry),'glbFiles':len(glbs),'itemsWithCapturedPhotos':sum(bool(x.get('images')) for x in photos.get('items',{}).values()),'capturedPhotoFiles':sum(len(x.get('images',[])) for x in photos.get('items',{}).values()),'captured3dFiles':sum(len(x.get('captured3d',[])) for x in photos.get('items',{}).values()),'totalGlbBytes':sum(p.stat().st_size for p in glbs),'missing':missing,'note':'Photo-backed product-specific web twins; not manufacturer CAD or photogrammetry unless a captured source file is separately reviewed.'}
(root/'reports/QA_VANTA_V13.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
(root/'reports/QA_VANTA_V13.txt').write_text('\n'.join(f'{k}: {v}' for k,v in report.items()),encoding='utf-8')
print(json.dumps(report,indent=2))
PY
)
PATCH='VANTA-v1.3-Verified-Photo-Assets'
mkdir -p "$PATCH/assets/data" "$PATCH/assets/library" "$PATCH/reports" "$PATCH/tools"
cp -R workspace/assets/glb "$PATCH/assets/"
cp -R workspace/assets/reference-photos "$PATCH/assets/"
[ ! -d workspace/assets/library/captured-3d-v13 ] || cp -R workspace/assets/library/captured-3d-v13 "$PATCH/assets/library/"
cp workspace/assets/data/*.json "$PATCH/assets/data/"
cp workspace/reports/QA_VANTA_V13.* "$PATCH/reports/"
cp workspace/tools/*.py "$PATCH/tools/"
cat > "$PATCH/README.txt" <<'EOF'
VANTA v1.3 — Verified Photo Asset Pack

341 GLB-ассет, проверенные фотоматериалы, карта исправления названий и метаданные источников.
Автоматически созданные GLB — товарно-специфичные web-двойники на объёмной геометрии.
Они не являются CAD производителя или полной фотограмметрией. Захваченные готовые 3D/CAD-файлы
следует проверять по лицензии, масштабу и совместимости до публикации.
EOF
python - <<'PY'
from pathlib import Path
Path('VANTA-v1.3-Verified-Photo-Assets/INSTALL-PATCH.bat').write_text(r'''@echo off
setlocal
cd /d "%~dp0"
set "TARGET=%~dp0.."
set "BACKUP=%TARGET%\backup-before-v1.3"
if not exist "%TARGET%\VANTA Asset Studio.exe" (
  echo ERROR: Put this patch folder inside the VANTA portable folder.
  pause
  exit /b 1
)
if not exist "%BACKUP%" mkdir "%BACKUP%"
if exist "%TARGET%\assets\glb" xcopy "%TARGET%\assets\glb" "%BACKUP%\assets\glb\" /E /I /Y >nul
xcopy "%~dp0assets" "%TARGET%\assets\" /E /I /Y
echo SUCCESS: VANTA v1.3 photo assets installed.
pause
''',encoding='utf-8')
PY
zip -0 -r VANTA-v1.3-Verified-Photo-Assets.zip "$PATCH" >/dev/null
sha256sum VANTA-v1.3-Verified-Photo-Assets.zip > VANTA-v1.3-Verified-Photo-Assets.zip.sha256
du -sh "$PATCH" VANTA-v1.3-Verified-Photo-Assets.zip
