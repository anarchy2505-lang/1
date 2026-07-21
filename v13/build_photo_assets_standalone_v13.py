#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/'assets/data/product-reference-registry-v13.json'
PHOTO_MANIFEST=ROOT/'assets/data/photo-source-manifest-v13.json'
OUT=ROOT/'assets/glb'
REPORT=ROOT/'assets/data/asset-upgrade-v13.json'
FONT=next((p for p in ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf','/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf'] if Path(p).exists()),None)

def rgba(h,a=255):
    h=(h or '#777777').lstrip('#');h=h if len(h)==6 else ''.join(c*2 for c in h)
    try:return tuple(int(h[i:i+2],16) for i in (0,2,4))+(a,)
    except:return (119,119,119,a)
def mat(name,color='#777777',metal=.25,rough=.45,alpha=1.0,texture=None):
    return trimesh.visual.material.PBRMaterial(name=name,baseColorFactor=np.array(rgba(color,round(alpha*255)),dtype=np.uint8),baseColorTexture=texture,metallicFactor=metal,roughnessFactor=rough,alphaMode='BLEND' if alpha<1 else 'OPAQUE',doubleSided=True)
def add(s,m,n,color='#777777',metal=.25,rough=.45,alpha=1.0):m.visual.material=mat(n,color,metal,rough,alpha);s.add_geometry(m,node_name=n,geom_name=n)
def box(ext,pos=(0,0,0)):g=trimesh.creation.box(extents=ext);g.apply_translation(pos);return g
def cyl(r,h,pos=(0,0,0),axis='z',sections=32):
    g=trimesh.creation.cylinder(radius=r,height=h,sections=sections)
    if axis=='x':g.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2,[0,1,0]))
    if axis=='y':g.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2,[1,0,0]))
    g.apply_translation(pos);return g
def fan(s,pos,r=.24,depth=.10,axis='z',accent='#76d8ff',name='fan'):
    x,y,z=pos;add(s,box((r*2.25,r*2.25,depth),(x,y,z)),name+'_frame','#20252a',.45,.38);add(s,cyl(r,depth*1.08,pos,axis,48),name+'_ring',accent,.08,.18,.82);add(s,cyl(r*.28,depth*1.18,pos,axis,32),name+'_hub','#353b41',.58,.32)
    for i in range(7):
        a=i*2*math.pi/7;b=box((r*.68,r*.17,depth*.22),(x+math.cos(a)*r*.43,y+math.sin(a)*r*.43,z+depth*.15));b.apply_transform(trimesh.transformations.rotation_matrix(a+.65,[0,0,1],point=[x,y,z]));add(s,b,name+f'_blade_{i}','#bac2c8',.25,.34,.78)
def label_image(text,size=(1024,420)):
    im=Image.new('RGBA',size,rgba('#12161b',244));d=ImageDraw.Draw(im);fs=54
    while fs>18:
        f=ImageFont.truetype(FONT,fs) if FONT else ImageFont.load_default();bb=d.multiline_textbbox((0,0),text,font=f,align='center')
        if bb[2]-bb[0]<size[0]-50 and bb[3]-bb[1]<size[1]-30:break
        fs-=2
    d.multiline_text(((size[0]-(bb[2]-bb[0]))/2,(size[1]-(bb[3]-bb[1]))/2-bb[1]),text,font=f,fill=rgba('#f4f6f7'),align='center');return im
def plane_xy(w,h,z,im):
    v=np.array([[-w/2,-h/2,z],[w/2,-h/2,z],[w/2,h/2,z],[-w/2,h/2,z]],float);f=np.array([[0,1,2],[0,2,3],[2,1,0],[3,2,0]]);uv=np.array([[0,1],[1,1],[1,0],[0,0]],float);m=trimesh.Trimesh(vertices=v,faces=f,process=False);m.visual=trimesh.visual.texture.TextureVisuals(uv=uv,image=im);return m
def plane_yz(h,d,x,im):
    v=np.array([[x,-d/2,-h/2],[x,d/2,-h/2],[x,d/2,h/2],[x,-d/2,h/2]],float);f=np.array([[0,1,2],[0,2,3],[2,1,0],[3,2,0]]);uv=np.array([[0,1],[1,1],[1,0],[0,0]],float);m=trimesh.Trimesh(vertices=v,faces=f,process=False);m.visual=trimesh.visual.texture.TextureVisuals(uv=uv,image=im);return m
def plane_xz(w,d,y,im):
    v=np.array([[-w/2,y,-d/2],[w/2,y,-d/2],[w/2,y,d/2],[-w/2,y,d/2]],float);f=np.array([[0,1,2],[0,2,3],[2,1,0],[3,2,0]]);uv=np.array([[0,1],[1,1],[1,0],[0,0]],float);m=trimesh.Trimesh(vertices=v,faces=f,process=False);m.visual=trimesh.visual.texture.TextureVisuals(uv=uv,image=im);return m
def trim(im):
    im=im.convert('RGBA');arr=np.array(im);rgb=arr[:,:,:3];neutral=(rgb.max(2)-rgb.min(2)<14);white=(rgb.mean(2)>246)&neutral;arr[white,3]=0;out=Image.fromarray(arr,'RGBA');bb=out.getchannel('A').getbbox();out=out.crop(bb) if bb else out
    if max(out.size)>1280:out.thumbnail((1280,1280),Image.Resampling.LANCZOS)
    return out
def palette(v):
    p={'ASUS':('#25292e','#f04a61'),'MSI':('#24282d','#e9eef2'),'Gigabyte':('#252b31','#56a8ff'),'ASRock':('#263036','#72d6ae'),'Lian Li':('#202429','#ff9d53'),'DeepCool':('#20262b','#53e2cf'),'Corsair':('#22262a','#f2d64c'),'AMD':('#26292d','#e96b3c'),'Intel':('#28333c','#4ba5e8'),'NVIDIA':('#2c3336','#82d148')};return p.get(v,('#292e33','#69c9ff'))
def base_scene(cat,item):
    v=item['vendor'];name=item['confirmed_name'];base,accent=palette(v);s=trimesh.Scene();n=(v+' '+name).lower()
    if cat=='case':
        w,h,d=2.5,3.15,2.35;t=.10
        for x in (-w/2+t/2,w/2-t/2):
            for z in (-d/2+t/2,d/2-t/2):add(s,box((t,h,t),(x,0,z)),f'frame_{x}_{z}',base,.72,.28)
        for y in (-h/2+t/2,h/2-t/2):add(s,box((w,t,d),(0,y,0)),f'panel_{y}',base,.58,.35)
        add(s,box((w-.18,h-.18,.035),(0,0,d/2-.03)),'front_glass','#a8d4e6',.02,.08,.16);add(s,box((.035,h-.18,d-.18),(-w/2+.03,0,0)),'side_glass','#a8d4e6',.02,.08,.13)
        for i,y in enumerate(np.linspace(-.75,.75,3)):fan(s,(w/2-.18,y,.25),.18,.08,'x',accent,f'sidefan_{i}')
    elif cat=='cpu':add(s,box((1.25,.12,1.25)),'substrate','#294536' if v=='AMD' else '#28485c',.25,.55);add(s,box((1.02,.10,1.02),(0,.11,0)),'ihs','#d5d7d5',.92,.22)
    elif cat=='motherboard':
        add(s,box((2.25,2.65,.09)),'pcb',base,.18,.62);add(s,box((.72,.72,.12),(-.35,.42,.10)),'socket','#adb4ba',.76,.25)
        for i in range(4):add(s,box((.07,1.25,.11),(.23+i*.14,.52,.10)),f'ram_{i}','#111317',.25,.55)
        for i,y in enumerate((-.35,-.72,-1.02)):add(s,box((1.48,.08,.11),(.25,y,.10)),f'pcie_{i}','#d5d7d8' if i==0 else '#111317',.35,.55)
        add(s,box((.32,1.25,.48),(-1.0,.62,.25)),'io','#343a40',.72,.28);add(s,box((.08,1.65,.035),(1.02,-.12,.075)),'accent',accent,.25,.25,.9)
    elif cat=='gpu':
        fn=2 if any(k in n for k in ('dual','2x','two fan')) else 3;L=2.35;add(s,box((L,.62,.48)),'shroud',base,.48,.34)
        for i,x in enumerate(np.linspace(-L*.30,L*.30,fn)):fan(s,(x,0,.27),.19,.09,'z',accent,f'gpu_fan_{i}')
        add(s,box((L*.95,.05,.44),(0,.34,0)),'backplate','#51585f',.78,.25);add(s,box((.08,.58,.46),(-L/2-.04,0,0)),'bracket','#bdc3c7',.86,.20)
    elif cat=='cooler':
        size=420 if '420' in n else 360 if '360' in n else 280 if '280' in n else 240 if '240' in n else 0
        if size:
            cnt=3 if size in (360,420) else 2;L=2.25 if cnt==3 else 1.55;add(s,box((L,.55,.16),(0,.55,0)),'radiator','#1b1f23',.62,.36)
            for i,x in enumerate(np.linspace(-L*.32,L*.32,cnt)):fan(s,(x,.55,.12),.23,.09,'z',accent,f'radfan_{i}')
            add(s,cyl(.34,.16,(0,-.58,.05),'z',42),'pump',base,.60,.25);add(s,box((.12,1.0,.12),(-.16,0,.02)),'hose_a','#20242a',.12,.55);add(s,box((.12,1.0,.12),(.16,0,.02)),'hose_b','#20242a',.12,.55)
        else:add(s,box((.75,1.15,.72)),'tower','#aab1b6',.83,.23);fan(s,(0,0,.42),.30,.10,'z',accent,'towerfan')
    elif cat=='ram':add(s,box((1.65,.22,.52)),'pcb','#20372c',.25,.54);add(s,box((1.55,.18,.42),(0,.04,0)),'spreader',base,.62,.30);add(s,box((1.35,.06,.10),(0,.14,.18)),'rgb',accent,.06,.15,.92)
    elif cat=='storage':
        add(s,box((1.55,.48,.06)),'pcb','#16402c',.18,.60)
        for i,x in enumerate(np.linspace(-.55,.55,5)):add(s,box((.19,.30,.08),(x,0,.07)),f'chip_{i}','#111419',.30,.48)
    elif cat=='psu':add(s,box((1.55,1.45,1.45)),'body',base,.62,.34);fan(s,(0,0,.76),.52,.08,'z',accent,'psu_fan')
    elif cat=='fans':
        shown=6 if '6' in n else 3
        for i in range(shown):fan(s,((i%3-1)*.62,(.5-i//3)*.62,0),.25,.11,'z',accent,f'fan_{i}')
    else:
        for i,x in enumerate(np.linspace(-.5,.5,8)):add(s,box((.06,1.35,.06),(x,0,0)),f'cable_{i}','#e6e8ea',.10,.46)
    return s
def add_photos(s,cat,paths,item):
    imgs=[]
    for p in paths[:3]:
        try:imgs.append(trim(Image.open(p)))
        except:pass
    if not imgs:imgs=[label_image(item['vendor']+'\n'+item['confirmed_name'])]
    mn,mx=s.bounds;c=(mn+mx)/2;sz=mx-mn;added=[]
    im=imgs[0];a=im.width/max(im.height,1);w=sz[0]*.94;h=min(sz[1]*.94,w/a);w=min(w,h*a);m=plane_xy(w,h,mx[2]+max(sz[2]*.02,.01),im);m.apply_translation((c[0],c[1],0));s.add_geometry(m,node_name='v13_photo_front',geom_name='v13_photo_front');added.append('front')
    if len(imgs)>1 and cat not in ('cpu','motherboard','storage'):
        im=imgs[1];a=im.width/max(im.height,1);d=sz[2]*.94;h=min(sz[1]*.94,d/a);d=min(d,h*a);m=plane_yz(h,d,mx[0]+max(sz[0]*.02,.01),im);m.apply_translation((0,c[1],c[2]));s.add_geometry(m,node_name='v13_photo_side',geom_name='v13_photo_side');added.append('side')
    if len(imgs)>2 and cat in ('case','gpu','psu','cooler'):
        im=imgs[2];a=im.width/max(im.height,1);w=sz[0]*.9;d=min(sz[2]*.9,w/a);w=min(w,d*a);m=plane_xz(w,d,mx[1]+max(sz[1]*.02,.01),im);m.apply_translation((c[0],0,c[2]));s.add_geometry(m,node_name='v13_photo_top',geom_name='v13_photo_top');added.append('top')
    return added
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--category');ap.add_argument('--limit',type=int);args=ap.parse_args();refs=json.loads(REGISTRY.read_text(encoding='utf-8'))['items'];pm=json.loads(PHOTO_MANIFEST.read_text(encoding='utf-8'))['items'] if PHOTO_MANIFEST.exists() else {};jobs=[(k,v) for k,v in refs.items() if not args.category or v['category']==args.category];jobs=jobs[:args.limit] if args.limit else jobs;rows=[]
    for i,(key,item) in enumerate(jobs,1):
        cat,pid=key.split('/',1);s=base_scene(cat,item);rec=pm.get(key,{});paths=[ROOT/x['path'] for x in rec.get('images',[]) if (ROOT/x['path']).exists()];added=add_photos(s,cat,paths,item);s.metadata.update({'vantaVersion':'1.3','projectId':key,'vendor':item['vendor'],'model':item['confirmed_name'],'sourcePage':item['url'],'assetClass':'photo-backed product-specific reference twin','accuracy':'manufacturer imagery on category-specific web geometry; not manufacturer CAD or photogrammetry','photoSources':[x.get('sourceUrl') for x in rec.get('images',[])]});dst=OUT/cat/f'{pid}.glb';dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(s.export(file_type='glb'));rows.append({'projectId':key,'name':item['confirmed_name'],'photos':len(paths),'surfaces':added,'bytes':dst.stat().st_size,'sourcePage':item['url'],'status':'photo-backed' if paths else 'label-fallback'});print(f'[{i}/{len(jobs)}] {key} photos={len(paths)} bytes={dst.stat().st_size}',flush=True)
    REPORT.parent.mkdir(parents=True,exist_ok=True);REPORT.write_text(json.dumps({'version':'1.3','count':len(rows),'items':rows},ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
