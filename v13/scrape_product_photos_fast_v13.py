#!/usr/bin/env python3
from __future__ import annotations
import argparse, asyncio, hashlib, io, json
from pathlib import Path
from urllib.parse import urljoin, urlparse
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/'assets/data/product-reference-registry-v13.json'
PHOTO_ROOT=ROOT/'assets/reference-photos'
MODEL_ROOT=ROOT/'assets/library/captured-3d-v13'
MANIFEST=ROOT/'assets/data/photo-source-manifest-v13.json'
IMAGE_EXT={'.jpg','.jpeg','.png','.webp','.avif'}
MODEL_EXT={'.glb','.gltf','.usdz','.obj','.fbx','.stp','.step','.stl','.3mf'}
BAD=('logo','icon','sprite','avatar','favicon','payment','social','flag','cookie','badge','placeholder','loading')
GOOD=('product','gallery','media','upload','original','angle','front','side','back','overview','image','assets','zoom')

def sha(b): return hashlib.sha256(b).hexdigest()
def score(url,data,im,bonus=0):
    u=url.lower(); w,h=im.size; s=bonus+min((w*h)//220_000,12)
    s+=sum(2 for x in GOOD if x in u); s-=sum(7 for x in BAD if x in u)
    if max(w,h)>=1000:s+=6
    if min(w,h)<220:s-=25
    if w/h>5 or h/w>5:s-=9
    if len(data)>140_000:s+=3
    return s

def normalize(data,dst):
    im=Image.open(io.BytesIO(data)).convert('RGBA')
    if max(im.size)>1280:im.thumbnail((1280,1280),Image.Resampling.LANCZOS)
    dst.parent.mkdir(parents=True,exist_ok=True); im.save(dst,'WEBP',quality=86,method=6)
    return im.size

async def scrape_one(context,key,item,max_images,sem):
  async with sem:
    cat,pid=key.split('/',1); out=PHOTO_ROOT/cat/pid; out.mkdir(parents=True,exist_ok=True)
    result={'projectId':key,'vendor':item['vendor'],'name':item['confirmed_name'],'sourcePage':item['url'],'verificationStatus':item['status'],'images':[],'captured3d':[],'errors':[]}
    page=await context.new_page(); candidates=[]; models=[]; response_tasks=[]
    async def handle(resp):
      try:
        url=resp.url; ct=(resp.headers.get('content-type') or '').split(';')[0].lower(); ext=Path(urlparse(url).path).suffix.lower()
        if ext in IMAGE_EXT or ct.startswith('image/'):
          body=await resp.body()
          if 12000<len(body)<9_000_000:
            try:
              im=Image.open(io.BytesIO(body)); im.load(); s=score(url,body,im)
              if s>-4:candidates.append((s,url,body,im.size))
            except: pass
        elif ext in MODEL_EXT or any(x in ct for x in ('model/','gltf','step','stl','3mf')):
          body=await resp.body()
          if 20_000<len(body)<150_000_000:models.append((url,ct,body,ext or '.bin'))
      except: pass
    page.on('response',lambda r: response_tasks.append(asyncio.create_task(handle(r))))
    try:
      if item.get('reference_image'):
        try:
          r=await context.request.get(item['reference_image'],timeout=15000)
          if r.ok:
            b=await r.body(); im=Image.open(io.BytesIO(b)); im.load(); candidates.append((score(item['reference_image'],b,im,30),item['reference_image'],b,im.size))
        except Exception as e: result['errors'].append('reference:'+str(e)[:180])
      await page.goto(item['url'],wait_until='domcontentloaded',timeout=22000)
      await page.wait_for_timeout(900)
      for label in ('Accept all','Accept','I agree','Allow all','Agree','Принять все','Принять'):
        try:
          loc=page.get_by_text(label,exact=False).first
          if await loc.count(): await loc.click(timeout=400)
        except: pass
      await page.evaluate('window.scrollTo(0, Math.min(document.body.scrollHeight, 2800))')
      await page.wait_for_timeout(750)
      urls=await page.evaluate("""() => {const a=[]; const add=x=>{if(typeof x==='string'&&x.trim())a.push(x.trim())}; document.querySelectorAll('meta[property="og:image"],meta[property="og:image:secure_url"],meta[name="twitter:image"]').forEach(n=>add(n.content)); document.querySelectorAll('img').forEach(n=>{['src','data-src','data-lazy-src','data-original','data-zoom-image'].forEach(k=>add(n.getAttribute(k))); const ss=n.getAttribute('srcset')||n.getAttribute('data-srcset'); if(ss)ss.split(',').forEach(x=>add(x.trim().split(/\\s+/)[0]))}); return [...new Set(a)].slice(0,20)}""")
      async def fetch_url(raw):
        try:
          full=urljoin(page.url,raw); r=await context.request.get(full,timeout=12000)
          if r.ok:
            b=await r.body()
            if 12000<len(b)<9_000_000:
              im=Image.open(io.BytesIO(b)); im.load(); s=score(full,b,im,5)
              if s>-4:candidates.append((s,full,b,im.size))
        except: pass
      await asyncio.gather(*(fetch_url(u) for u in urls),return_exceptions=True)
    except Exception as e: result['errors'].append('page:'+str(e)[:240])
    await page.close()
    if response_tasks: await asyncio.gather(*response_tasks,return_exceptions=True)
    seen=set(); candidates.sort(key=lambda x:x[0],reverse=True)
    for s,url,b,source_size in candidates:
      digest=sha(b)
      if digest in seen:continue
      seen.add(digest)
      try:
        dst=out/f'{len(result["images"]):02d}.webp'; norm=normalize(b,dst)
        result['images'].append({'path':str(dst.relative_to(ROOT)).replace('\\','/'),'sourceUrl':url,'sha256':sha(dst.read_bytes()),'sourceSize':source_size,'normalizedSize':norm,'score':s})
        if len(result['images'])>=max_images:break
      except Exception as e:result['errors'].append('image:'+str(e)[:160])
    mseen=set()
    for url,ct,b,ext in models:
      digest=sha(b)
      if digest in mseen:continue
      mseen.add(digest); folder=MODEL_ROOT/cat/pid; folder.mkdir(parents=True,exist_ok=True); dst=folder/f'source-{len(result["captured3d"]):02d}{ext}'; dst.write_bytes(b)
      result['captured3d'].append({'path':str(dst.relative_to(ROOT)).replace('\\','/'),'sourceUrl':url,'contentType':ct,'sha256':digest,'status':'needs-license-and-dimension-review'})
      if len(result['captured3d'])>=4:break
    result['status']='gallery-captured' if result['images'] else 'page-only-no-gallery'
    (out/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

async def run(args):
  items=json.loads(REGISTRY.read_text(encoding='utf-8'))['items']; jobs=[(k,v) for k,v in items.items() if not args.category or v['category']==args.category]
  if args.limit:jobs=jobs[:args.limit]
  if args.dry_run:print(json.dumps({'jobs':len(jobs)}));return
  from playwright.async_api import async_playwright
  sem=asyncio.Semaphore(args.workers)
  async with async_playwright() as pw:
    browser=await pw.chromium.launch(headless=True,args=['--no-sandbox','--disable-blink-features=AutomationControlled'])
    context=await browser.new_context(viewport={'width':1365,'height':900},locale='en-US',ignore_https_errors=True,service_workers='block')
    async def route(route):
      if route.request.resource_type in {'font','media'}: await route.abort()
      else: await route.continue_()
    await context.route('**/*',route)
    tasks=[asyncio.create_task(scrape_one(context,k,v,args.max_images,sem)) for k,v in jobs]
    for i,t in enumerate(asyncio.as_completed(tasks),1):
      try:
        r=await t; print(f'[{i}/{len(tasks)}] {r["projectId"]} {r["status"]} images={len(r["images"])} 3d={len(r["captured3d"])}',flush=True)
      except Exception as e: print('ERROR',repr(e),flush=True)
    await context.close(); await browser.close()
  merged={}
  for mf in PHOTO_ROOT.glob('*/*/manifest.json'):
    try:r=json.loads(mf.read_text());merged[r['projectId']]=r
    except:pass
  summary={'version':'1.3','count':len(merged),'withImages':sum(bool(x.get('images')) for x in merged.values()),'captured3dFiles':sum(len(x.get('captured3d',[])) for x in merged.values()),'items':merged}
  MANIFEST.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8'); print('SUMMARY',summary['count'],summary['withImages'],summary['captured3dFiles'])
def main():
  p=argparse.ArgumentParser();p.add_argument('--category');p.add_argument('--limit',type=int);p.add_argument('--workers',type=int,default=12);p.add_argument('--max-images',type=int,default=3);p.add_argument('--dry-run',action='store_true');args=p.parse_args();asyncio.run(run(args))
if __name__=='__main__':main()
