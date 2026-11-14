"""Generate a printable SVG sheet using the exact edge marker dictionary."""
import argparse
from pathlib import Path
import cv2

p=argparse.ArgumentParser(description=__doc__)
p.add_argument("--dictionary",default="DICT_4X4_250",choices=["DICT_4X4_250","DICT_5X5_250","DICT_6X6_250"])
p.add_argument("--output",default="data/aruco-cards.svg")
args=p.parse_args()
dictionary=cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco,args.dictionary))
ids=[0,1,2,3,*range(17,23)]
width,height=210,297
edge=45
out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" viewBox="0 0 {width} {height}">',
     '<rect width="100%" height="100%" fill="white"/>']
for i,marker in enumerate(ids):
    x,y=18+(i%3)*65,12+(i//3)*67
    side=dictionary.markerSize+2
    pixels=cv2.aruco.generateImageMarker(dictionary,marker,side)
    for row,col in zip(*(pixels==0).nonzero()):
        out.append(f'<rect x="{x+col*edge/side}" y="{y+row*edge/side}" width="{edge/side}" height="{edge/side}"/>')
    out.append(f'<text x="{x}" y="{y+edge+7}" font-family="sans-serif" font-size="4">{marker} / {"wall anchor" if marker<4 else "object card"}</text>')
out.append('<text x="18" y="283" font-family="sans-serif" font-size="3.5">SPACEGIT / Print actual size. Measure the black edge before calibration.</text></svg>')
target=Path(args.output)
target.parent.mkdir(parents=True,exist_ok=True)
target.write_text("\n".join(out),encoding="utf-8")
print(target)
