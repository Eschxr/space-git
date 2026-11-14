"""Bounded exporter for the binary triangle PLY files produced by COLMAP."""
import json
from pathlib import Path
import struct
import zipfile

import numpy as np
from PIL import Image

TYPES={"char":"i1","uchar":"u1","short":"i2","ushort":"u2","int":"i4","uint":"u4","float":"f4","double":"f8",
       "int8":"i1","uint8":"u1","int16":"i2","uint16":"u2","int32":"i4","uint32":"u4","float32":"f4","float64":"f8"}
FACE_LISTS={"vertex_indices":3,"vertex_index":3,"texcoord":6,"texcoords":6,"tex_coord":6}
TRI_LIMIT=420_000
BYTE_LIMIT=64*1024**2


def ply_header(f):
    if f.readline(128).strip()!=b"ply" or f.readline(128).strip()!=b"format binary_little_endian 1.0":
        raise ValueError("Expected the binary little-endian COLMAP PLY format")
    elements=[]
    for _ in range(80):
        line=f.readline(2048)
        if not line:
            break
        parts=line.decode("ascii").split()
        if not parts or parts[0] in ("comment","obj_info"):
            continue
        if parts==["end_header"]:
            return elements
        if parts[0]=="element" and len(parts)==3:
            elements.append((parts[1],int(parts[2]),[]))
        elif parts[0]=="property" and elements:
            elements[-1][2].append(parts[1:])
        else:
            raise ValueError("Unexpected COLMAP PLY header")
    raise ValueError("Incomplete PLY header")


def point_count(path):
    with path.open("rb") as f:
        for kind,n,_ in ply_header(f):
            if kind=="vertex" and n>0:
                return n
    raise ValueError("PLY has no vertices")


def mesh_arrays(path):
    if path.stat().st_size>BYTE_LIMIT:
        raise ValueError("Mesh exceeds the 64 MB conversion limit")
    elements={}
    with path.open("rb") as f:
        for name,n,props in ply_header(f):
            if name not in ("vertex","face") or not 3<=n<=TRI_LIMIT or name in elements:
                raise ValueError("Expected a bounded vertex and triangle mesh")
            fields,counts=[],{}
            for prop in props:
                if len(prop)==2 and prop[0] in TYPES:
                    fields.append((prop[1],"<"+TYPES[prop[0]]))
                elif len(prop)==4 and prop[0]=="list" and name=="face" and prop[3] in FACE_LISTS and all(t in TYPES for t in prop[1:3]):
                    _,c,v,key=prop
                    counts[key]=FACE_LISTS[key]
                    fields.extend([(key+"_n","<"+TYPES[c]),(key,"<"+TYPES[v],(counts[key],))])
                else:
                    raise ValueError("Unexpected PLY property")
            if not fields:
                raise ValueError("Mesh element has no properties")
            dtype=np.dtype(fields)
            data=np.fromfile(f,dtype,count=n)
            if len(data)!=n or any(not np.all(data[k+"_n"]==count) for k,count in counts.items()):
                raise ValueError("Mesh contains truncated or non-triangle faces")
            elements[name]=data
    vertex,face=elements.get("vertex"),elements.get("face")
    if vertex is None or face is None or not {"x","y","z"}<=set(vertex.dtype.names):
        raise ValueError("PLY has no usable surface geometry")
    indices=next((face[k] for k in ("vertex_indices","vertex_index") if k in face.dtype.names),None)
    if indices is None or indices.min()<0 or indices.max()>=len(vertex):
        raise ValueError("PLY contains invalid vertex indices")
    xyz=np.column_stack([vertex[k] for k in "xyz"]).astype("<f4")
    if not np.isfinite(xyz).all() or np.abs(xyz).max()>1e8:
        raise ValueError("Mesh coordinates are invalid")
    uv=next((face[k].reshape(-1,3,2).astype("<f4") for k in ("texcoord","texcoords","tex_coord") if k in face.dtype.names),None)
    if uv is not None and (not np.isfinite(uv).all() or np.max(np.abs(uv))>2):
        raise ValueError("Texture coordinates are invalid")
    tri=xyz[indices]
    if (np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)>1e-12).sum()<3:
        raise ValueError("No usable surface triangles")
    return xyz,indices.astype("<u4"),uv


def as_glb(path,xyz,indices,uv=None,atlas=None):
    textured=uv is not None and atlas is not None
    normals=np.zeros_like(xyz)
    tri=xyz[indices]
    fn=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    for j in range(3):
        np.add.at(normals,indices[:,j],fn)
    norm=np.linalg.norm(normals,axis=1)
    normals[norm<1e-15]=[0,0,1]
    normals/=np.linalg.norm(normals,axis=1)[:,None]
    if textured:
        normals=normals[indices].reshape(-1,3)
        xyz=tri.reshape(-1,3)
        indices=np.arange(len(xyz),dtype="<u4").reshape(-1,3)
        uv=uv.reshape(-1,2).copy()
        # OBJ/PLY use bottom-left UVs; glTF uses top-left texture coordinates.
        uv[:,1]=1-uv[:,1]
    content=bytearray()
    views=[]
    accessors=[]
    def view(raw,target=None):
        pad=(-len(content))%4
        content.extend(b"\0"*pad)
        v=dict(buffer=0,byteOffset=len(content),byteLength=len(raw))
        if target:
            v["target"]=target
        views.append(v)
        content.extend(raw)
        return len(views)-1
    def attr(data,kind,type_,target,limits=False):
        a=dict(bufferView=view(np.ascontiguousarray(data).tobytes(),target),componentType=kind,count=len(data),type=type_)
        if limits:
            a.update(min=data.min(axis=0).tolist(),max=data.max(axis=0).tolist())
        accessors.append(a)
        return len(accessors)-1
    attrs={"POSITION":attr(xyz,5126,"VEC3",34962,True),"NORMAL":attr(normals.astype("<f4"),5126,"VEC3",34962)}
    primitive={"attributes":attrs,"indices":attr(indices.ravel(),5125,"SCALAR",34963),"material":0}
    doc={"asset":{"version":"2.0","generator":"SpaceGit COLMAP exporter"},"scene":0,"scenes":[{"nodes":[0]}],
         "nodes":[{"mesh":0,"name":"COLMAP visual geometry (unregistered)"}],"meshes":[{"primitives":[primitive]}],
         "bufferViews":views,"accessors":accessors,"materials":[{"doubleSided":True,"pbrMetallicRoughness":{
             "metallicFactor":0,"roughnessFactor":.94,"baseColorFactor":[.65,.72,.78,1]}}]}
    if textured:
        attrs["TEXCOORD_0"]=attr(uv,5126,"VEC2",34962)
        doc.update(images=[{"mimeType":"image/png","bufferView":view(atlas)}],textures=[{"source":0}])
        doc["materials"][0]["pbrMetallicRoughness"].update(baseColorFactor=[1,1,1,1],baseColorTexture={"index":0})
    content.extend(b"\0"*((-len(content))%4))
    doc["buffers"]=[{"byteLength":len(content)}]
    meta=json.dumps(doc,separators=(",",":"),allow_nan=False).encode()
    meta+=b" "*((-len(meta))%4)
    total=28+len(meta)+len(content)
    if total>BYTE_LIMIT:
        raise ValueError("GLB exceeds the 64 MB export limit")
    with path.open("wb") as f:
        f.write(struct.pack("<4sII",b"glTF",2,total))
        f.write(struct.pack("<I4s",len(meta),b"JSON"));f.write(meta)
        f.write(struct.pack("<I4s",len(content),b"BIN\0"));f.write(content)


def export_mesh(mesh,work,texture=None):
    xyz,faces,uv=mesh_arrays(mesh)
    atlas=None
    if texture is not None:
        if uv is None or texture.stat().st_size>36*1024**2:
            raise ValueError("COLMAP texture atlas or per-face UVs are unavailable or too large")
        with Image.open(texture) as im:
            if im.format!="PNG" or max(im.size)>8192 or im.width*im.height>40_000_000:
                raise ValueError("Texture atlas exceeds the 8192 px or 40 megapixel limit")
            im.verify()
        atlas=texture.read_bytes()
    as_glb(work/"model.glb",xyz,faces,uv,atlas)
    with (work/"model.obj").open("w",encoding="ascii",newline="\n") as f:
        f.write("# SpaceGit / arbitrary COLMAP coordinate frame\n")
        if atlas:
            f.write("mtllib model.mtl\nusemtl atlas\n")
        np.savetxt(f,xyz,fmt="v %.8g %.8g %.8g")
        if atlas:
            np.savetxt(f,uv.reshape(-1,2),fmt="vt %.8g %.8g")
            for i,face in enumerate(faces):
                a,b,c=map(lambda v:int(v)+1,face)
                j=i*3+1
                f.write(f"f {a}/{j} {b}/{j+1} {c}/{j+2}\n")
        else:
            np.savetxt(f,faces+1,fmt="f %d %d %d")
    names=["model.glb","model.obj"]
    if atlas:
        (work/"model.mtl").write_text("newmtl atlas\nKd 1 1 1\nmap_Kd texture.png\n",encoding="ascii")
        (work/"texture.png").write_bytes(atlas)
        with zipfile.ZipFile(work/"textured-obj.zip","w",zipfile.ZIP_DEFLATED) as archive:
            for name in ("model.obj","model.mtl","texture.png"):
                archive.write(work/name,name)
        names.append("textured-obj.zip")
    return names,len(faces)
