#!/usr/bin/env python3
"""Download official product galleries and page-served 3D files for VANTA v1.3.

The input registry contains one verified source page per catalog item. The scraper
keeps source metadata and never labels reconstructed geometry as manufacturer CAD.
"""
from __future__ import annotations
import argparse, asyncio, hashlib, io, json, re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/'assets/data/product-reference-registry-v13.json'
PHOTO_ROOT=ROOT/'assets/reference-photos'
CAPTURE_ROOT=ROOT/'assets/library/source-pages-v13'
MODEL_ROOT=ROOT/'assets/library/captured-3d-v13'
MANIFEST=ROOT/'assets/data/photo-source-manifest-v13.json'
IMAGE_EXT={'.jpg','.jpeg','.png','.webp','.avif'}
MODEL_EXT={'.glb','.gltf','.usdz','.obj','.fbx','.stp','.step','.stl','.3mf'}
BAD_WORDS=('logo','icon','sprite','avatar','favicon','payment','social','flag','cookie','banner','badge','thumb')
GOOD_WORDS=('product','gallery','media','upload','original','angle','front','side','back','overview','image','assets')


def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def load_registry():return json.loads(REGISTRY.read_text(encoding='utf-8'))['items']

def image_score(url,ct,data,img):
    u=url.lower();w,h=img.size;score=0
    score += min((w*h)//250_000,12)
    score += sum(2 for x in GOOD_WORDS if x in u)
    score -= sum(6 for x in BAD_WORDS if x in u)
    if ct.startswith('image/'):score+=3
    if max(w,h)>=1000:score+=5
    if min(w,h)<180:score-=20
    if w/h>5 or h/w>5:score-=8
    if len(data)>150_000:score+=3
    return score


def normalize_image(data:bytes,dst:Path):
    im=Image.open(io.BytesIO(data)).convert('RGBA')
    if max(im.size)>1800:
        im.thumbnail((1800,1800),Image.Resampling.LANCZOS)
    dst.parent.mkdir(parents=True,exist_ok=True)
    im.save(dst,'WEBP',quality=92,method=6)
    return im.size

async def scrape_one(browser,key,item,max_images=6,overwrite=False):
    cat,pid=key.split('/',1);out=PHOTO_ROOT/cat/pid;out.mkdir(parents=True,exist_ok=True)
    cap=CAPTURE_ROOT/cat/pid;cap.mkdir(parents=True,exist_ok=True)
    result={'projectId':key,'vendor':item['vendor'],'name':item['confirmed_name'],'sourcePage':item['url'],
            'verificationStatus':item['status'],'images':[],'captured3d':[],'errors':[]}
    if not overwrite and (out/'manifest.json').exists():
        try:return json.loads((out/'manifest.json').read_text(encoding='utf-8'))
        except Exception:pass
    context=await browser.new_context(viewport={'width':1440,'height':1100},locale='en-US',ignore_https_errors=True)
    page=await context.new_page(); candidates=[]; models=[]

    async def accept_image(url,body,ct,bonus=0):
        try:
            im=Image.open(io.BytesIO(body)); im.load()
            s=image_score(url,ct,body,im)+bonus
            if s>-5:candidates.append((s,url,ct,body,im.size))
        except Exception:pass

    async def response_handler(resp):
        try:
            url=resp.url;ct=(resp.headers.get('content-type') or '').split(';')[0].lower();ext=Path(urlparse(url).path).suffix.lower()
            if ext in IMAGE_EXT or ct.startswith('image/'):
                body=await resp.body()
                if len(body)>12_000:await accept_image(url,body,ct)
            if ext in MODEL_EXT or any(x in ct for x in ('model/','gltf','step','stl','3mf')):
                body=await resp.body()
                if len(body)>20_000:models.append((url,ct,body,ext))
        except Exception:pass
    page.on('response',response_handler)

    if item.get('reference_image'):
        try:
            r=await context.request.get(item['reference_image'],timeout=30000)
            if r.ok:
                body=await r.body();ct=(r.headers.get('content-type') or '').split(';')[0]
                await accept_image(item['reference_image'],body,ct,25)
        except Exception as e:result['errors'].append('reference: '+str(e))

    try:
        await page.goto(item['url'],wait_until='domcontentloaded',timeout=45000)
        await page.wait_for_timeout(2200)
        for label in ('Accept all','Accept','I agree','Allow all','Agree','Принять все','Принять'):
            try:
                loc=page.get_by_text(label,exact=False).first
                if await loc.count(): await loc.click(timeout=800)
            except Exception:pass
        await page.evaluate("window.scrollTo(0, Math.min(document.body.scrollHeight, 4500))")
        await page.wait_for_timeout(1800)
        dom=await page.evaluate("""() => {
          const out=[];
          const add=x=>{if(typeof x==='string'&&x.trim())out.push(x.trim())};
          document.querySelectorAll('meta[property="og:image"],meta[property="og:image:secure_url"],meta[name="twitter:image"]').forEach(n=>add(n.content));
          document.querySelectorAll('img,source').forEach(n=>{
            ['src','data-src','data-lazy-src','data-original','data-zoom-image'].forEach(k=>add(n.getAttribute(k)));
            const ss=n.getAttribute('srcset')||n.getAttribute('data-srcset');
            if(ss)ss.split(',').forEach(x=>add(x.trim().split(/\\s+/)[0]));
          });
          document.querySelectorAll('[style*="background-image"]').forEach(n=>{
            const m=(n.getAttribute('style')||'').match(/url\(["']?([^"')]+)["']?\)/); if(m)add(m[1]);
          });
          document.querySelectorAll('script[type="application/ld+json"]').forEach(n=>{
            try{const walk=o=>{if(!o)return;if(typeof o==='string'){if(/^https?:/.test(o)&&/\\.(png|jpe?g|webp|avif)(\\?|$)/i.test(o))add(o);return}if(Array.isArray(o))o.forEach(walk);else if(typeof o==='object')Object.values(o).forEach(walk)};walk(JSON.parse(n.textContent))}catch(e){}
          });
          return [...new Set(out)];
        }""")
        for raw in dom[:180]:
            try:
                full=urljoin(page.url,raw);r=await context.request.get(full,timeout=22000)
                if r.ok:
                    body=await r.body();ct=(r.headers.get('content-type') or '').split(';')[0]
                    if len(body)>12_000:await accept_image(full,body,ct,5 if 'og:image' in raw else 0)
            except Exception:pass
        await page.screenshot(path=str(cap/'page.png'),full_page=False)
        (cap/'source-url.txt').write_text(page.url,encoding='utf-8')
    except Exception as e:result['errors'].append('page: '+str(e))

    seen=set(); candidates.sort(key=lambda x:x[0],reverse=True)
    for score,url,ct,body,size in candidates:
        digest=sha(body)
        if digest in seen:continue
        seen.add(digest)
        try:
            idx=len(result['images']);dst=out/f'{idx:02d}.webp';normalized_size=normalize_image(body,dst)
            result['images'].append({'path':str(dst.relative_to(ROOT)).replace('\\','/'),'sourceUrl':url,'sha256':sha(dst.read_bytes()),'sourceSize':size,'normalizedSize':normalized_size,'score':score})
            if len(result['images'])>=max_images:break
        except Exception as e:result['errors'].append('image: '+str(e))

    mseen=set()
    for url,ct,body,ext in models:
        digest=sha(body)
        if digest in mseen:continue
        mseen.add(digest);folder=MODEL_ROOT/cat/pid;folder.mkdir(parents=True,exist_ok=True)
        ext=ext or '.bin';dst=folder/f'source-{len(result["captured3d"]):02d}{ext}';dst.write_bytes(body)
        result['captured3d'].append({'path':str(dst.relative_to(ROOT)).replace('\\','/'),'sourceUrl':url,'contentType':ct,'sha256':digest,'status':'needs-license-and-dimension-review'})
        if len(result['captured3d'])>=6:break

    result['status']='gallery-captured' if result['images'] else 'page-only-no-gallery'
    (out/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    await context.close();return result

async def main_async(args):
    items=load_registry();jobs=[]
    for key,item in items.items():
        if args.category and item['category']!=args.category:continue
        if args.query and args.query.lower() not in f"{item['vendor']} {item['name']} {item['confirmed_name']}".lower():continue
        jobs.append((key,item))
    if args.limit:jobs=jobs[:args.limit]
    if args.dry_run:
        print(json.dumps({'jobs':len(jobs),'category':args.category},ensure_ascii=False));return
    from playwright.async_api import async_playwright
    results=[];sem=asyncio.Semaphore(max(1,args.workers))
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True,args=['--disable-blink-features=AutomationControlled','--no-sandbox'])
        async def guarded(k,i):
            async with sem:return await scrape_one(browser,k,i,args.max_images,args.overwrite)
        tasks=[asyncio.create_task(guarded(k,i)) for k,i in jobs]
        for n,t in enumerate(asyncio.as_completed(tasks),1):
            try:
                r=await t;results.append(r);print(f"[{n}/{len(tasks)}] {r['projectId']} {r['status']} images={len(r['images'])} 3d={len(r['captured3d'])}",flush=True)
            except Exception as e:print('ERROR',repr(e),flush=True)
        await browser.close()
    merged={}
    for mf in PHOTO_ROOT.glob('*/*/manifest.json'):
        try:
            r=json.loads(mf.read_text(encoding='utf-8'));merged[r['projectId']]=r
        except Exception:pass
    summary={'version':'1.3','count':len(merged),'withImages':sum(bool(x.get('images')) for x in merged.values()),'captured3dFiles':sum(len(x.get('captured3d',[])) for x in merged.values()),'items':merged}
    MANIFEST.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print('SUMMARY',summary['count'],summary['withImages'],summary['captured3dFiles'])

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--category');ap.add_argument('--query');ap.add_argument('--limit',type=int);ap.add_argument('--workers',type=int,default=3);ap.add_argument('--max-images',type=int,default=6);ap.add_argument('--overwrite',action='store_true');ap.add_argument('--dry-run',action='store_true');args=ap.parse_args();asyncio.run(main_async(args))
if __name__=='__main__':main()
