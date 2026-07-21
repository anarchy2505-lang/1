#!/usr/bin/env python3
"""Build photo-backed GLB product twins for VANTA v1.3.

This pass embeds verified manufacturer imagery as UV-textured product surfaces on
category-specific 3D geometry. It is intentionally labelled as a reference twin,
not manufacturer CAD or photogrammetry.
"""
from __future__ import annotations
import argparse, hashlib, io, json, math
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image, ImageChops

ROOT=Path(__file__).resolve().parents[1]
CATALOG=ROOT/'assets/data/catalog-v09.json'
REGISTRY=ROOT/'assets/data/product-reference-registry-v13.json'
PHOTO_MANIFEST=ROOT/'assets/data/photo-source-manifest-v13.json'
GLB_ROOT=ROOT/'assets/glb'
REPORT=ROOT/'assets/data/asset-upgrade-v13.json'


def bounds(scene):
    b=scene.bounds;mn,mx=b;return mn,mx,(mn+mx)/2,(mx-mn)

def trim_and_key(im:Image.Image)->Image.Image:
    im=im.convert('RGBA')
    arr=np.array(im).astype(np.uint8)
    rgb=arr[:,:,:3];alpha=arr[:,:,3].astype(np.float32)
    neutral=(rgb.max(axis=2)-rgb.min(axis=2)<10)
    white=(rgb.mean(axis=2)>247)&neutral
    import cv2
    mask=(white.astype(np.uint8)*255)
    ff=mask.copy();h,w=mask.shape;fmask=np.zeros((h+2,w+2),np.uint8)
    cv2.floodFill(ff,fmask,(0,0),128)
    bg=ff==128
    alpha[bg]=0
    arr[:,:,3]=alpha.astype(np.uint8)
    out=Image.fromarray(arr,'RGBA')
    bb=out.getchannel('A').getbbox()
    if bb:out=out.crop(bb)
    if max(out.size)>1400:out.thumbnail((1400,1400),Image.Resampling.LANCZOS)
    return out

def plane_xy(width,height,z,image,name):
    v=np.array([[-width/2,-height/2,z],[width/2,-height/2,z],[width/2,height/2,z],[-width/2,height/2,z]],float)
    f=np.array([[0,1,2],[0,2,3],[2,1,0],[3,2,0]])
    uv=np.array([[0,1],[1,1],[1,0],[0,0]],float)
    m=trimesh.Trimesh(vertices=v,faces=f,process=False)
    m.visual=trimesh.visual.texture.TextureVisuals(uv=uv,image=image)
    return m

def plane_yz(height,depth,x,image,name):
    v=np.array([[x,-depth/2,-height/2],[x,depth/2,-height/2],[x,depth/2,height/2],[x,-depth/2,height/2]],float)
    f=np.array([[0,1,2],[0,2,3],[2,1,0],[3,2,0]])
    uv=np.array([[0,1],[1,1],[1,0],[0,0]],float)
    m=trimesh.Trimesh(vertices=v,faces=f,process=False)
    m.visual=trimesh.visual.texture.TextureVisuals(uv=uv,image=image)
    return m

def plane_xz(width,depth,y,image,name):
    v=np.array([[-width/2,y,-depth/2],[width/2,y,-depth/2],[width/2,y,depth/2],[-width/2,y,depth/2]],float)
    f=np.array([[0,1,2],[0,2,3],[2,1,0],[3,2,0]])
    uv=np.array([[0,1],[1,1],[1,0],[0,0]],float)
    m=trimesh.Trimesh(vertices=v,faces=f,process=False)
    m.visual=trimesh.visual.texture.TextureVisuals(uv=uv,image=image)
    return m

def fit_dims(img, max_w,max_h):
    a=img.width/max(img.height,1);w=max_w;h=w/a
    if h>max_h:h=max_h;w=h*a
    return w,h

def add_photo_surfaces(scene,category,images,source_urls):
    mn,mx,c,sz=bounds(scene);added=[]
    for node in list(scene.graph.nodes_geometry):
        if str(node).startswith('v13_photo_'):
            try:scene.delete_geometry(node)
            except Exception:pass
    prepared=[]
    for p in images[:3]:
        try:prepared.append(trim_and_key(Image.open(p)))
        except Exception:pass
    if not prepared:return added
    im=prepared[0];w,h=fit_dims(im,sz[0]*.94,sz[1]*.94)
    front=plane_xy(w,h,mx[2]+max(sz[2]*.015,.002),im,'front')
    front.apply_translation((c[0],c[1],0));scene.add_geometry(front,node_name='v13_photo_front',geom_name='v13_photo_front');added.append('front')
    if len(prepared)>1 and category not in {'cpu','motherboard','storage'}:
        im2=prepared[1];h2,d2=fit_dims(im2,sz[2]*.94,sz[1]*.94)
        side=plane_yz(h2,d2,mx[0]+max(sz[0]*.015,.002),im2,'side')
        side.apply_translation((0,c[1],c[2]));scene.add_geometry(side,node_name='v13_photo_side',geom_name='v13_photo_side');added.append('side')
    if len(prepared)>2 and category in {'case','gpu','psu','cooler'}:
        im3=prepared[2];w3,d3=fit_dims(im3,sz[0]*.90,sz[2]*.90)
        top=plane_xz(w3,d3,mx[1]+max(sz[1]*.015,.002),im3,'top')
        top.apply_translation((c[0],0,c[2]));scene.add_geometry(top,node_name='v13_photo_top',geom_name='v13_photo_top');added.append('top')
    scene.metadata.update({'vantaVersion':'1.3','assetPass':'Verified Photo Surface Pass','assetClass':'photo-backed product-specific reference twin','accuracy':'manufacturer imagery embedded on web geometry; not manufacturer CAD or photogrammetry','photoSourceUrls':source_urls})
    return added

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--category');ap.add_argument('--limit',type=int);ap.add_argument('--overwrite',action='store_true');args=ap.parse_args()
    catalog=json.loads(CATALOG.read_text(encoding='utf-8'))
    refs=json.loads(REGISTRY.read_text(encoding='utf-8'))['items']
    pm=json.loads(PHOTO_MANIFEST.read_text(encoding='utf-8'))['items'] if PHOTO_MANIFEST.exists() else {}
    rows=[];jobs=[]
    for cat,group in catalog.items():
        if args.category and cat!=args.category:continue
        for o in group['options']:jobs.append((cat,o))
    if args.limit:jobs=jobs[:args.limit]
    for n,(cat,o) in enumerate(jobs,1):
        key=f'{cat}/{o["id"]}';path=GLB_ROOT/cat/f'{o["id"]}.glb';scene=trimesh.load(path,force='scene',process=False)
        rec=pm.get(key,{});photos=[ROOT/x['path'] for x in rec.get('images',[]) if (ROOT/x['path']).exists()]
        source_urls=[x['sourceUrl'] for x in rec.get('images',[])]
        if not photos:
            fallback=ROOT/'assets/renders'/cat/f'{o["id"]}.webp'
            if fallback.exists():photos=[fallback];source_urls=[refs[key]['url']+'#fallback-render']
        added=add_photo_surfaces(scene,cat,photos,source_urls)
        payload=scene.export(file_type='glb');path.write_bytes(payload)
        rows.append({'projectId':key,'name':o['name'],'photoCount':len(photos),'surfaces':added,'bytes':len(payload),'sourcePage':refs[key]['url'],'status':'photo-backed' if rec.get('images') else 'render-fallback'})
        print(f'[{n}/{len(jobs)}] {key} photos={len(photos)} surfaces={len(added)} bytes={len(payload)}',flush=True)
    REPORT.write_text(json.dumps({'version':'1.3','pass':'Verified Photo Surface Pass','count':len(rows),'items':rows},ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
