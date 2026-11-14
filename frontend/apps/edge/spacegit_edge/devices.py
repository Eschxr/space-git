import os
import re
from pathlib import Path


def cameras():
    if os.name != "nt":
        return [{"index":int(p.name[5:]),"label":p.name} for p in sorted(Path("/dev").glob("video[0-9]*"))
                if p.name[5:].isdigit()]
    from .directshow import cameras as directshow_cameras

    return directshow_cameras()


def displays():
    if os.name == "nt":
        import ctypes
        return ctypes.windll.user32.GetSystemMetrics(80) or None
    import subprocess
    try:
        r=subprocess.run(["xrandr","--listactivemonitors"],capture_output=True,text=True,timeout=3,check=True)
        return int(r.stdout.splitlines()[0].split()[-1])
    except (OSError,subprocess.SubprocessError,ValueError,IndexError):
        return None


def monitor_layout():
    """Stable topology signature when the host provides monitor geometry."""
    if os.name=="nt":
        import ctypes as c
        from ctypes import wintypes as w
        class Info(c.Structure):
            _fields_=[("size",w.DWORD),("screen",w.RECT),("work",w.RECT),("flags",w.DWORD),("name",w.WCHAR*32)]
        found=[]
        cb_type=c.WINFUNCTYPE(w.BOOL,w.HANDLE,w.HDC,c.POINTER(w.RECT),w.LPARAM)
        @cb_type
        def add(h,_dc,_rect,_data):
            info=Info()
            info.size=c.sizeof(info)
            if c.windll.user32.GetMonitorInfoW(h,c.byref(info)):
                r=info.screen
                found.append(dict(id=info.name,primary=bool(info.flags&1),rect=[r.left,r.top,r.right-r.left,r.bottom-r.top]))
            return True
        # HMONITOR is pointer-sized on 64-bit Windows.
        c.windll.user32.GetMonitorInfoW.argtypes=[w.HANDLE,c.POINTER(Info)]
        c.windll.user32.EnumDisplayMonitors(None,None,add,0)
        return found
    import subprocess
    try:
        r=subprocess.run(["xrandr","--listactivemonitors"],capture_output=True,text=True,timeout=3,check=True)
        found=[]
        for line in r.stdout.splitlines()[1:]:
            m=re.search(r"(?P<w>\d+)/\d+x(?P<h>\d+)/\d+\+(?P<x>-?\d+)\+(?P<y>-?\d+)\s+(?P<id>\S+)",line)
            if m:
                found.append(dict(id=m["id"],primary="*" in line.split()[1],rect=[int(m[k]) for k in ("x","y","w","h")]))
        return found
    except (OSError,subprocess.SubprocessError):
        return []
