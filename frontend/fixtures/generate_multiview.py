"""Produce deterministic rendered views of textured planes at different depths.

These images are a synthetic test dataset, not photographs of a physical room.
The known camera motion includes parallax and is not passed to COLMAP.
"""
import argparse
from pathlib import Path
import cv2
import numpy as np

def texture(seed, label):
    rng=np.random.default_rng(seed)
    im=np.full((750,1000,3),(51,77,100),np.uint8)
    for _ in range(1500):
        x,y=rng.integers((0,0),(1000,750))
        color=tuple(int(c) for c in rng.integers(20,240,3))
        if rng.random()<.5:
            cv2.circle(im,(int(x),int(y)),int(rng.integers(2,12)),color,-1,cv2.LINE_AA)
        else:
            cv2.rectangle(im,(int(x),int(y)),(int(x)+int(rng.integers(4,30)),int(y)+int(rng.integers(3,28))),color,-1)
    for i in range(8):
        cv2.putText(im,f"{label} / {seed}-{i}",(36,65+85*i),cv2.FONT_HERSHEY_DUPLEX,.88,(245,238,211),2,cv2.LINE_AA)
    return im

def render(out, count=14):
    out.mkdir(parents=True,exist_ok=True)
    planes=[
        ([[-2.4,-1.6,4.7],[2.4,-1.6,4.7],[2.4,1.6,4.7],[-2.4,1.6,4.7]],texture(7,"BACK")),
        ([[-1.1,-.72,3.6],[-.15,-.7,3.8],[-.15,.31,3.8],[-1.1,.31,3.6]],texture(31,"EXHIBIT A")),
        ([[.27,-.63,4.05],[1.04,-.7,3.55],[1.04,.53,3.55],[.27,.58,4.05]],texture(42,"EXHIBIT B")),
        ([[-.23,.34,3.3],[.24,.36,3.41],[.24,.86,3.41],[-.23,.83,3.3]],texture(68,"EXHIBIT C")),
    ]
    k=np.array([[790.,0,480],[0,790,320],[0,0,1]])
    for i in range(count):
        phase=(i/(count-1)-.5)*2.2
        eye=np.array([.9*np.sin(phase),.20*np.sin(3*phase),.06*np.cos(phase)])
        z=np.array([0.,0.,3.9])-eye
        z/=np.linalg.norm(z)
        x=np.cross([0,1,0],z);x/=np.linalg.norm(x)
        y=np.cross(z,x)
        basis=np.array([x,y,z])
        frame=np.full((640,960,3),26,np.uint8)
        for corners,im in planes:
            xyz=(np.array(corners)-eye)@basis.T
            dst=xyz@k.T
            dst=(dst[:,:2]/dst[:,2:]).astype(np.float32)
            src=np.array([[0,0],[999,0],[999,749],[0,749]],np.float32)
            m=cv2.getPerspectiveTransform(src,dst)
            cv2.warpPerspective(im,m,(960,640),dst=frame,borderMode=cv2.BORDER_TRANSPARENT)
        cv2.imwrite(str(out/f"view-{i:02}.jpg"),frame,[cv2.IMWRITE_JPEG_QUALITY,94])

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("output",type=Path)
    render(p.parse_args().output)
