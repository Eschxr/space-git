"""Generate a print-ready A4 checkerboard (10 x 7 squares, 9 x 6 inner corners)."""
import argparse
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output",type=Path,default=Path("data/lens-checkerboard.svg"))
args=parser.parse_args()
sheet=['<svg xmlns="http://www.w3.org/2000/svg" width="297mm" height="210mm" viewBox="0 0 297 210">',
       '<rect width="297" height="210" fill="white"/>']
for y in range(7):
    for x in range(10):
        if (x+y)%2==0:
            sheet.append(f'<rect x="{28+x*24}" y="{13+y*24}" width="24" height="24"/>')
sheet+=['<text x="28" y="196" font-family="sans-serif" font-size="4">SPACEGIT / 24 mm squares / Print actual size and mount on a flat board</text>','</svg>']
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text("\n".join(sheet),encoding="utf-8")
print(args.output)
