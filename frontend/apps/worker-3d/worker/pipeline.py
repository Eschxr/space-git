"""COLMAP optional dense and textured stages; generated artifacts remain separate from scene data."""
import shutil

from .mesh import TRI_LIMIT, export_mesh, ply_header, point_count


def surface(quality,command,root,images,model,publish):
    dense=root/"dense"
    dense.mkdir()
    mesh=root/"mesh.ply"
    if quality in ("dense","textured"):
        if shutil.disk_usage(root).free<3*1024**3:
            raise RuntimeError("Dense reconstruction needs at least 3 GiB of free workspace storage")
    if quality in ("dense","textured","mesh_textured"):
        command("undistorting","Preparing images for multi-view stereo",
                ["image_undistorter","--image_path",str(images),"--input_path",str(model),
                 "--output_path",str(dense),"--output_type","COLMAP","--max_image_size","1400"],600)
    if quality in ("dense","textured"):
        command("dense_stereo","Estimating dense depth on the GPU",
                ["patch_match_stereo","--workspace_path",str(dense),"--workspace_format","COLMAP",
                 "--PatchMatchStereo.gpu_index","0",
                 "--PatchMatchStereo.max_image_size","1152","--PatchMatchStereo.geom_consistency","0",
                 "--PatchMatchStereo.filter","1","--PatchMatchStereo.num_iterations","3",
                 "--PatchMatchStereo.num_samples","8"],1500)
        fused=dense/"fused.ply"
        command("dense_fusion","Fusing depth maps into a dense point cloud",
                ["stereo_fusion","--workspace_path",str(dense),"--workspace_format","COLMAP","--input_type","photometric",
                 "--StereoFusion.max_image_size","1152","--StereoFusion.min_num_pixels","3","--output_path",str(fused)],900)
        if not fused.is_file() or point_count(fused)<100:
            raise RuntimeError("Dense fusion did not recover a usable cloud. Improve overlap and lighting.")
        publish(fused,"dense.ply")
        command("meshing","Building a surface from the fused dense cloud",
                ["poisson_mesher","--input_path",str(fused),"--output_path",str(mesh),"--PoissonMeshing.depth","9"],600)
    else:
        command("meshing","Building a surface from sparse camera tracks (no dense cloud)",
                ["delaunay_mesher","--input_path",str(model),"--input_type","sparse","--output_path",str(mesh)],600)

    if not mesh.is_file():
        raise RuntimeError("COLMAP did not produce a surface mesh")
    with mesh.open("rb") as f:
        n=next((n for name,n,_ in ply_header(f) if name=="face"),0)
    cap=160_000 if quality in ("textured","mesh_textured") else TRI_LIMIT
    if n>cap:
        simple=root/"simplified.ply"
        command("meshing","Reducing the triangle count for portable export",
                ["mesh_simplifier","--input_path",str(mesh),"--output_path",str(simple),
                 "--MeshSimplification.target_face_ratio",str(.85*cap/n)],600)
        mesh=simple
    out=root/"exports"
    out.mkdir()
    names,triangles=export_mesh(mesh,out)
    publish(mesh,"mesh.ply")
    for name in names:
        publish(out/name,name)
    textured=False
    if quality in ("textured","mesh_textured"):
        atlas_dir=root/"textured"
        atlas_dir.mkdir()
        command("texturing","Mapping registered camera images onto the mesh",
                ["mesh_texturer","--workspace_path",str(dense),"--input_path",str(mesh),"--output_path",str(atlas_dir),
                 "--MeshTextureMapping.texture_scale_factor","0.65","--MeshTextureMapping.num_threads","4"],900)
        mesh_with_uv,atlas=atlas_dir/"mesh.ply",atlas_dir/"texture.png"
        if not mesh_with_uv.is_file() or not atlas.is_file():
            raise RuntimeError("COLMAP did not produce a mesh with a texture atlas")
        names,triangles=export_mesh(mesh_with_uv,out,atlas)
        for name in names:
            publish(out/name,name)
        textured=True
    return triangles,textured
