import cv2, numpy as np
from shapely.geometry import Polygon, Point, box
from shapely.ops import unary_union
from shapely import affinity
m=cv2.imread('mask110.png',0)
Y0,Y1=65,705                       # top of head, butt end in the photo (px)
SX,SY=260/381, 460/(Y1-Y0)          # px -> mm (width 260, length 460)
# --- head outline: polar contour around the head centre, mirrored and smoothed
hm=m.copy(); hm[425:]=0
cs,_=cv2.findContours(hm,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)
c=max(cs,key=cv2.contourArea)[:,0,:].astype(float)
CX0,CY0=219.5,240.0
ang=np.arctan2(c[:,1]-CY0,c[:,0]-CX0); rad=np.hypot(c[:,0]-CX0,c[:,1]-CY0)
o=np.argsort(ang); ang,rad=ang[o],rad[o]
th=np.radians(np.arange(-180,180,0.5))
r=np.interp(th,ang,rad,period=2*np.pi)
rm=np.interp(np.arctan2(np.sin(th),-np.cos(th)),th,r,period=2*np.pi)   # mirror across vertical axis
r=(r+rm)/2
k=np.exp(-0.5*(np.arange(-24,25)/8.0)**2); k/=k.sum()
r=np.convolve(np.concatenate([r[-24:],r,r[:24]]),k,mode='valid')
headpts=[(float(rr*np.cos(t)),float(CY0+rr*np.sin(t))) for rr,t in zip(r,th)]
headpoly=Polygon(headpts).buffer(0)
headpoly=headpoly.intersection(box(-300,0,300,372))
prof=[]
for y in range(360,421,4):
    xs=np.where(m[y]>0)[0]; prof.append((y,(xs.max()-xs.min())/2))
# throat + handle (measured, strap/plastic removed)
prof+= [(430,80),(440,75),(450,68.5),(460,62),(470,56),(480,49.5),(490,42),(500,35.5),(510,31),(520,29.5)]
prof+= [(y,29.5) for y in range(530,681,10)] + [(686,33),(694,35),(700,34),(704,30),(705,0)]
right=[(0,360)]+[(w,y) for y,w in prof]
pts=[(w,y) for w,y in right[1:]]+[(-w,y) for w,y in reversed(right[1:-1])]
outline=unary_union([headpoly,Polygon(pts).buffer(0)]).buffer(6,join_style=1).buffer(-6,join_style=1)
head=outline.intersection(box(-300,0,300,425))
# slot (crescent) under the face and triangular opening in the bridge
def quad(p0,p1,p2,n=40):
    return [((1-t)**2*p0[0]+2*(1-t)*t*p1[0]+t*t*p2[0],(1-t)**2*p0[1]+2*(1-t)*t*p1[1]+t*t*p2[1]) for t in np.linspace(0,1,n)]
top=quad((-90,392),(0,404),(90,392)); bot=quad((90,392),(0,432),(-90,392))
slot=Polygon(top+bot[1:-1]).buffer(2.5,join_style=1)
tri=Polygon([(-37,448),(37,448),(3,496)]).buffer(-9,join_style=1).buffer(9,join_style=1)
tri=affinity.translate(tri,-1.5,0)
face=head.buffer(-10,join_style=1).difference(Polygon(quad((-120,388),(0,398),(120,388))+[(120,450),(-120,450)]).buffer(0))
face=face.buffer(-1).buffer(1)
frame=outline.difference(slot).difference(tri)
# holes: 8 rows, symmetric grid measured on the photo
rows=[(129,6),(155,8),(181,10),(207,10),(233,10),(260,10),(288,8),(316,6)]
holes=[((k-(n-1)/2)*30.2,y) for y,n in rows for k in range(n)]
print('holes',len(holes))
T=lambda x,y:(130+x*SX,(y-Y0)*SY)
def gpath(geom):
    if geom.geom_type=='MultiPolygon': return ' '.join(gpath(g) for g in geom.geoms)
    r=lambda cs:'M'+' L'.join('%.2f,%.2f'%T(x,y) for x,y in list(cs)[:-1])+' Z'
    return r(geom.exterior.coords)+' '+' '.join(r(i.coords) for i in geom.interiors)
HR=4.5
hole_mm=[T(x,y) for x,y in holes]
circ=lambda x,y:f'M{x-HR:.2f},{y:.2f} a{HR},{HR} 0 1,0 {2*HR},0 a{HR},{HR} 0 1,0 {-2*HR},0 Z'
holes_d=' '.join(circ(x,y) for x,y in hole_mm)
grip_top,grip_bot=T(0,522)[1],T(0,684)[1]; gw=29.5*SX
# side view: 38 mm through the head, tapering to the handle
SXo=330; hy=T(0,425)[1]; ny=T(0,510)[1]
side=unary_union([box(SXo,8,SXo+38,hy),Point(SXo+19,19).buffer(19).intersection(box(SXo,0,SXo+38,19)),
     Polygon([(SXo,hy),(SXo+38,hy),(SXo+34,ny),(SXo+4,ny)]),box(SXo+4,ny,SXo+34,T(0,686)[1]),
     box(SXo+2,T(0,686)[1],SXo+36,460)]).buffer(1.5).buffer(-1.5)
def sp(geom): return 'M'+' L'.join('%.2f,%.2f'%c for c in list(geom.exterior.coords)[:-1])+' Z'
def svg(color):
    st=lambda f:(f'fill="{f}"' if color else 'fill="none" stroke="#111113" stroke-width="0.4"')
    o=['<?xml version="1.0" encoding="UTF-8"?>',
    '<svg xmlns="http://www.w3.org/2000/svg" width="390mm" height="486mm" viewBox="-16 -16 390 486">',
    '<title>TEMPRA PD·01 · modello 4054 · racchetta padel a goccia · scala 1:1 (mm)</title>',
    '<defs><pattern id="carbon18k" width="7" height="7" patternUnits="userSpaceOnUse">'
    '<rect width="7" height="7" fill="#1a1a1d"/><rect width="3.5" height="3.5" fill="#2c2c31"/><rect x="3.5" y="3.5" width="3.5" height="3.5" fill="#2c2c31"/></pattern>'
    '<pattern id="overgrip" width="9" height="9" patternUnits="userSpaceOnUse" patternTransform="rotate(-12)">'
    '<rect width="9" height="9" fill="#18181b"/><rect width="9" height="0.9" fill="#34343a"/></pattern></defs>']
    o.append(f'<g id="Telaio"><path d="{gpath(frame)} {holes_d}" fill-rule="evenodd" {st("#111113")}/></g>')
    o.append(f'<g id="Piatto_carbonio_18K"><path d="{gpath(face)} {holes_d}" fill-rule="evenodd" '+('fill="url(#carbon18k)"' if color else st(''))+'/></g>')
    o.append('<g id="Fori_68_diam9">'+''.join(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{HR}" '+('fill="none" stroke="#000" stroke-width="0.3"' if color else st(''))+'/>' for x,y in hole_mm)+'</g>')
    o.append(f'<g id="Impugnatura"><rect x="{130-gw:.2f}" y="{grip_top:.2f}" width="{2*gw:.2f}" height="{grip_bot-grip_top:.2f}" rx="4" '+('fill="url(#overgrip)"' if color else st(''))+'/></g>')
    o.append(f'<g id="Vista_laterale_38mm"><path d="{sp(side)}" {st("#111113")}/></g>')
    q='#E5502A'; t=lambda x,y,s,a="middle":f'<text x="{x}" y="{y}" font-family="Space Mono, monospace" font-size="6" fill="{q}" text-anchor="{a}">{s}</text>'
    o.append('<g id="Quote" stroke-width="0.35">'
      f'<line x1="0" y1="-6" x2="260" y2="-6" stroke="{q}"/><line x1="0" y1="-9" x2="0" y2="-3" stroke="{q}"/><line x1="260" y1="-9" x2="260" y2="-3" stroke="{q}"/>'+t(130,-8.5,"260 mm")+
      f'<line x1="-6" y1="0" x2="-6" y2="460" stroke="{q}"/><line x1="-9" y1="0" x2="-3" y2="0" stroke="{q}"/><line x1="-9" y1="460" x2="-3" y2="460" stroke="{q}"/>'
      f'<text x="-8.5" y="230" font-family="Space Mono, monospace" font-size="6" fill="{q}" text-anchor="middle" transform="rotate(-90 -8.5 230)">460 mm</text>'
      f'<line x1="{SXo}" y1="-6" x2="{SXo+38}" y2="-6" stroke="{q}"/>'+t(SXo+19,-8.5,"38 mm")+
      t(195,420,"TEMPRA PD·01 · mod. 4054","start")+t(195,428,"Goccia · carbonio 18K · EVA 17 nera","start")+
      t(195,436,"68 fori Ø 9 mm · 355 ± 10 g","start")+t(195,444,"Bilanciamento medio · scala 1:1","start")+'</g></svg>')
    return '\n'.join(o)
open('/home/user/campo/grafica/racchetta-pd01-4054.svg','w').write(svg(True))
open('/home/user/campo/grafica/racchetta-pd01-4054-linee.svg','w').write(svg(False))
# overlay check: draw traced outline on the photo
im=cv2.imread('/tmp/claude-0/-home-user-campo/b94b7768-b4cb-54d0-af94-325fd1ab7f35/images/3.png')
cx=219.5
for geom,col in ((outline,(0,0,255)),(slot,(0,255,255)),(tri,(0,255,0)),(face,(255,0,255))):
    for gg in (geom.geoms if geom.geom_type=='MultiPolygon' else [geom]):
        p=np.array([(x+cx,y) for x,y in gg.exterior.coords],np.int32); cv2.polylines(im,[p],True,col,1)
for x,y in holes: cv2.circle(im,(int(x+cx),int(y)),6,(255,255,0),1)
cv2.imwrite('overlay.png',im)
