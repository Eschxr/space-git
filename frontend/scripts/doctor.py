"""Report readiness without reading camera frames or printing secrets."""
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"apps/edge"))
from spacegit_edge import devices

def listening(port):
    with socket.socket() as s:
        s.settimeout(.3)
        return s.connect_ex(("127.0.0.1",port))==0

def gpu():
    binary=shutil.which("nvidia-smi")
    if not binary:
        return {"driver":False,"cuda_version":None}
    try:
        p=subprocess.run([binary],capture_output=True,text=True,timeout=5)
        import re
        cuda=re.search(r"CUDA Version:\s*([0-9.]+)",p.stdout)
        return {"driver":p.returncode==0,"cuda_version":cuda[1] if cuda else None}
    except (OSError,subprocess.TimeoutExpired):
        return {"driver":False,"cuda_version":None}

root=Path(os.getenv("SPACEGIT_DATA",ROOT/"data"))
print(json.dumps(dict(cameras=devices.cameras(),displays=devices.displays(),
    ffmpeg=bool(shutil.which("ffmpeg")),colmap=bool(shutil.which(os.getenv("SPACEGIT_COLMAP","colmap"))),
    gpu=gpu(),ports={p:"listening" if listening(p) else "no listener" for p in (3000,8000)},
    database={"sqlite":sqlite3.sqlite_version,"live":(root/"live.sqlite3").is_file()},
    storage={"exists":root.is_dir(),"free_gib":round(shutil.disk_usage(root if root.exists() else ROOT).free/(1024**3),1),
    "phone_https_configured":bool(os.getenv("SPACEGIT_MOBILE_ORIGIN"))},
    key_configured=bool(os.getenv("SPACEGIT_TOKEN"))),indent=2))
