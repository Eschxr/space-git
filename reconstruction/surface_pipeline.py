"""Conservative surface reconstruction in the input PLY coordinate system."""

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree


THREADS = 4
MAX_POINTS = 3_000_000


@dataclass(frozen=True)
class Settings:
    outliers: bool = True
    outlier_strength: float = 2.5
    voxel: float = 0
    depth: int = 9
    density_percent: float = 2
    support: float = 4
    smoothing: int = 3
    smoothing_intensity: float = .45


def read_cloud(path: Path):
    lines = []
    with path.open('rb') as stream:
        size = 0
        while size<65536:
            line = stream.readline(4096)
            if not line or not line.endswith(b'\n'):
                raise ValueError('Incomplete PLY header.')
            size += len(line)
            decoded = line.decode('ascii').strip()
            if decoded=='end_header':
                break
            lines.append(decoded)
        else:
            raise ValueError('The PLY header exceeds 64 KiB.')
    if len(lines)<2 or lines[0] != 'ply' or lines[1] not in (
        'format ascii 1.0', 'format binary_little_endian 1.0', 'format binary_big_endian 1.0'
    ):
        raise ValueError('Expected an ASCII or binary PLY 1.0 file.')
    elements = [line.split() for line in lines if line.startswith('element ')]
    count = next((int(e[2]) for e in elements if len(e)==3 and e[1]=='vertex'), 0)
    if not 24 <= count <= MAX_POINTS:
        raise ValueError(f'Expected 24 to {MAX_POINTS:,} vertices in the point cloud.')
    if any(e[1]=='face' and int(e[2]) for e in elements if len(e)==3):
        raise ValueError('This PLY already contains faces. Select a point-cloud PLY.')
    vertex_start = next(i for i,line in enumerate(lines) if line.startswith('element vertex '))
    vertex_end = next((i for i in range(vertex_start+1,len(lines)) if lines[i].startswith('element ')), len(lines))
    attributes = {line.split()[-1] for line in lines[vertex_start+1:vertex_end] if line.startswith('property ')}
    if not {'x','y','z'}.issubset(attributes):
        raise ValueError('The PLY vertex element must have X, Y and Z coordinates.')
    cloud = o3d.io.read_point_cloud(str(path), remove_nan_points=False, remove_infinite_points=False)
    xyz = np.asarray(cloud.points)
    if len(xyz) != count or not np.isfinite(xyz).all():
        raise ValueError('The PLY contains incomplete or non-finite vertex coordinates.')
    if cloud.has_colors() and not np.isfinite(np.asarray(cloud.colors)).all():
        raise ValueError('The PLY contains non-finite vertex colours.')
    return cloud


def neighbours(tree, query, k):
    return tree.query(query, k=k, workers=THREADS)


def analyse(cloud):
    xyz = np.asarray(cloud.points)
    tree = cKDTree(xyz)
    distance, _ = neighbours(tree, xyz, 2)
    distance = distance[:, 1]
    positive = distance[distance>0]
    if len(positive)<16:
        # Identical samples can dominate a depth projection. Measure the spacing of unique coordinates.
        unique = np.unique(xyz, axis=0)
        if len(unique)<24:
            raise ValueError('The PLY has too few unique coordinates for a surface.')
        positive = neighbours(cKDTree(unique), unique, 2)[0][:, 1]
    p10, spacing, p90 = np.percentile(positive, (10, 50, 90))
    bounds = np.ptp(xyz, axis=0)
    if not np.isfinite(bounds).all() or np.count_nonzero(bounds>spacing*.2)<2:
        raise ValueError('A surface needs points spread across at least two dimensions.')
    stats = dict(points=len(xyz), color=cloud.has_colors(), min=xyz.min(axis=0).tolist(),
                 max=xyz.max(axis=0).tolist(), dimensions=bounds.tolist(), units='unknown (input units retained)',
                 spacing=float(spacing), mean_spacing=float(distance.mean()), spacing_p10=float(p10),
                 spacing_p90=float(p90), isolated=int((distance>max(4*spacing, 2*p90)).sum()))
    return stats, tree, np.clip(distance, spacing*.6, spacing*3)


def clean(cloud, settings, stats, warnings):
    working = o3d.geometry.PointCloud(cloud)
    working.remove_duplicated_points()
    if settings.outliers:
        filtered, _ = working.remove_statistical_outlier(min(20, len(working.points)-1), settings.outlier_strength)
        if len(filtered.points)>=max(24, .90*len(working.points)):
            working = filtered
        else:
            warnings.append('Outlier removal would discard over 10% of unique points and was skipped.')
    if settings.voxel:
        working = working.voxel_down_sample(stats['spacing']*settings.voxel)
    if len(working.points)<24:
        raise ValueError('Too few points remain. Reduce downsampling or outlier removal.')
    return working


def orient(cloud, spacing, p90, camera_origin, warnings):
    radius = min(spacing*6, max(spacing*3.5, p90*2))
    cloud.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=radius, max_nn=40),
                           fast_normal_computation=False)
    if camera_origin:
        cloud.orient_normals_towards_camera_location(np.zeros(3))
    else:
        try:
            cloud.orient_normals_consistent_tangent_plane(min(20, len(cloud.points)-1))
        except RuntimeError:
            # Tangent-plane orientation requires a volumetric triangulation. Planar scans can use a common direction.
            xyz = np.asarray(cloud.points)
            _, vectors = np.linalg.eigh(np.cov(xyz, rowvar=False))
            cloud.orient_normals_to_align_with_direction(vectors[:, 0])
            warnings.append('Neighbourhood orientation failed. Normals were aligned using the scan plane.')
    normals = np.asarray(cloud.normals)
    if not np.isfinite(normals).all() or (np.linalg.norm(normals, axis=1)<.5).any():
        raise ValueError('Normal estimation failed. Try a denser scan or less downsampling.')
    return radius


def support_mask(query, tree, local, settings, *, bounds=None):
    distance, indices = neighbours(tree, query, 1)
    permitted = local[indices]*settings.support
    keep = distance<=permitted
    if bounds is not None:
        lower, upper = bounds
        keep &= ((query>=lower-permitted[:, None]) & (query<=upper+permitted[:, None])).all(axis=1)
    return keep


def trim(mesh, densities, tree, local, bounds, settings):
    vertices = np.asarray(mesh.vertices)
    if not len(vertices):
        raise ValueError('Poisson reconstruction did not produce a surface.')
    keep = support_mask(vertices, tree, local, settings, bounds=bounds)
    unsupported = int((~keep).sum())
    if settings.density_percent:
        keep &= densities>=np.percentile(densities, settings.density_percent)
    discarded = int((~keep).sum())
    mesh.remove_vertices_by_mask(~keep)
    vertices, faces = np.asarray(mesh.vertices), np.asarray(mesh.triangles)
    # Check the interior of each triangle too. Nearby endpoints alone can allow bridges.
    face_keep = np.ones(len(faces), dtype=bool)
    for start in range(0, len(faces), 100_000):
        batch = vertices[faces[start:start+100_000]]
        samples = (batch.mean(axis=1), (batch[:, 0]+batch[:, 1])/2,
                   (batch[:, 1]+batch[:, 2])/2, (batch[:, 2]+batch[:, 0])/2)
        for sample in samples:
            face_keep[start:start+len(batch)] &= support_mask(sample, tree, local, settings)
    mesh.remove_triangles_by_mask(~face_keep)
    mesh.remove_duplicated_vertices().remove_duplicated_triangles().remove_degenerate_triangles()
    if not mesh.has_triangles():
        raise ValueError('Confidence filtering removed the entire surface. Try higher gap support or a denser scan.')
    labels, counts, _ = mesh.cluster_connected_triangles()
    tiny = np.asarray(counts)[np.asarray(labels)]<4
    mesh.remove_triangles_by_mask(tiny)
    mesh.remove_unreferenced_vertices()
    return dict(unsupported_vertices=unsupported, trimmed_vertices=discarded, bridge_triangles=int((~face_keep).sum()),
                tiny_triangles=int(tiny.sum()))


def transfer_colors(mesh, cloud, tree, local, settings):
    if not cloud.has_colors():
        mesh.vertex_colors = o3d.utility.Vector3dVector()
        return
    xyz, rgb = np.asarray(mesh.vertices), np.asarray(cloud.colors)
    colors = np.empty((len(xyz), 3))
    for start in range(0, len(xyz), 100_000):
        distance, indices = neighbours(tree, xyz[start:start+100_000], 4)
        radius = local[indices[:, 0], None]*settings.support
        weights = np.where(distance<=radius, 1/np.maximum(distance, radius*.04)**2, 0)
        # Confidence filtering keeps vertices near the scan. Smooth previews can move a fraction of a spacing.
        weights[:, 0] = np.maximum(weights[:, 0], np.finfo(float).tiny)
        colors[start:start+len(distance)] = np.einsum('ij,ijk->ik', weights, rgb[indices])/weights.sum(axis=1)[:, None]
    mesh.vertex_colors = o3d.utility.Vector3dVector(colors.clip(0, 1))


def smooth(mesh, settings, spacing, warnings):
    if not settings.smoothing:
        return mesh
    after = mesh.filter_smooth_taubin(settings.smoothing, settings.smoothing_intensity,
                                      -settings.smoothing_intensity-.02, o3d.geometry.FilterScope.Vertex)
    original = np.asarray(mesh.vertices)
    delta = np.asarray(after.vertices)-original
    faces = np.asarray(mesh.triangles)
    edges = np.sort(np.concatenate((faces[:, [0,1]], faces[:, [1,2]], faces[:, [2,0]])), axis=1)
    unique, counts = np.unique(edges, axis=0, return_counts=True)
    max_move = np.full(len(original), spacing*.85)
    max_move[unique[counts!=2].ravel()] = spacing*.20
    delta *= np.minimum(1, max_move/np.maximum(np.linalg.norm(delta, axis=1), np.finfo(float).tiny))[:, None]
    result = original+delta
    for i in range(0, len(faces), 100_000):
        indices = faces[i:i+100_000]
        before, next_ = original[indices], result[indices]
        normals = np.cross(before[:, 1]-before[:, 0], before[:, 2]-before[:, 0])
        updated = np.cross(next_[:, 1]-next_[:, 0], next_[:, 2]-next_[:, 0])
        flipped = np.einsum('ij,ij->i', normals, updated)<=0
        result[indices[flipped].ravel()] = original[indices[flipped].ravel()]
    changed = np.abs(np.ptp(result, axis=0)-np.ptp(original, axis=0))
    if (changed>np.maximum(spacing, np.ptp(original, axis=0)*.025)).any():
        warnings.append('Smoothing changed the dimensions beyond the detail-preservation limit and was skipped.')
        return mesh
    after.vertices = o3d.utility.Vector3dVector(result)
    return after


def validate(mesh, stats, tree, local, settings):
    mesh.remove_degenerate_triangles().remove_unreferenced_vertices()
    vertices, faces = np.asarray(mesh.vertices), np.asarray(mesh.triangles)
    if not mesh.has_triangles() or not np.isfinite(vertices).all():
        raise ValueError('The reconstructed mesh is empty or has invalid coordinates.')
    area_floor = (stats['spacing']*1e-5)**2
    remove = np.zeros(len(faces), dtype=bool)
    for i in range(0, len(faces), 100_000):
        batch = vertices[faces[i:i+100_000]]
        area = np.linalg.norm(np.cross(batch[:, 1]-batch[:, 0], batch[:, 2]-batch[:, 0]), axis=1)
        remove[i:i+len(batch)] = ~np.isfinite(area) | (area<=area_floor)
    mesh.remove_triangles_by_mask(remove)
    mesh.remove_unreferenced_vertices()
    if not mesh.has_triangles():
        raise ValueError('All reconstructed faces were degenerate.')
    mesh.compute_vertex_normals()
    if not np.isfinite(np.asarray(mesh.vertex_normals)).all():
        raise ValueError('The reconstructed surface has invalid normals.')
    xyz = np.asarray(mesh.vertices)
    supported = support_mask(xyz, tree, local, settings)
    fraction = float(supported.mean())
    if fraction<.98:
        raise ValueError('The final surface diverges from the source points. Reduce smoothing or change support settings.')
    _, components, _ = mesh.cluster_connected_triangles()
    return dict(vertices=len(xyz), triangles=len(mesh.triangles), dimensions=np.ptp(xyz, axis=0).tolist(),
                components=len(components), largest_component=int(max(components)),
                supported_fraction=fraction, degenerate_removed=int(remove.sum()))


def process_view(source, output, settings, stage, *, camera_origin=False, base=None, analysis_only=False):
    start = time.monotonic()
    stage('Analysing sampling and colours')
    cloud = read_cloud(source)
    stats, tree, local = analyse(cloud)
    report = dict(input=stats, settings=asdict(settings), warnings=[], recommended_depth=8 if stats['points']<12000 else 9)
    if analysis_only:
        return report
    output.mkdir(parents=True, exist_ok=True)
    warnings = report['warnings']
    if base:
        stage('Loading the supported surface for a smoothing preview')
        mesh = o3d.io.read_triangle_mesh(str(base/'supported_mesh.ply'))
        prior = json.loads((base/'reconstruction_report.json').read_text(encoding='utf-8'))
        report.update({key:prior[key] for key in ('cleaned_points', 'normal_radius', 'confidence')})
        warnings.extend(prior['warnings'])
    else:
        stage('Cleaning the scan and orienting normals')
        cleaned = clean(cloud, settings, stats, warnings)
        if not o3d.io.write_point_cloud(str(output/'cleaned_pointcloud.ply'), cleaned):
            raise ValueError('Could not export the cleaned PLY.')
        clean_stats, clean_tree, clean_local = analyse(cleaned)
        report['cleaned_points'] = len(cleaned.points)
        report['normal_radius'] = orient(cleaned, clean_stats['spacing'], clean_stats['spacing_p90'], camera_origin, warnings)
        stage('Running screened Poisson reconstruction')
        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            cleaned, depth=settings.depth, scale=1.1, linear_fit=False, n_threads=THREADS)
        # Poisson colors are extrapolated; only the later transfer from the scan is used.
        mesh.vertex_colors = o3d.utility.Vector3dVector()
        stage('Trimming weak surfaces and unsupported bridges')
        report['confidence'] = trim(mesh, np.asarray(densities), clean_tree, clean_local,
                                    (np.asarray(clean_stats['min']), np.asarray(clean_stats['max'])), settings)
        validate(mesh, stats, tree, local, settings)
        if not o3d.io.write_triangle_mesh(str(output/'supported_mesh.ply'), mesh):
            raise ValueError('Could not cache the supported surface.')
    stage('Smoothing, transferring colours, and validating triangles')
    mesh = smooth(mesh, settings, stats['spacing'], warnings)
    transfer_colors(mesh, cloud, tree, local, settings)
    report['mesh'] = validate(mesh, stats, tree, local, settings)
    report['seconds'] = round(time.monotonic()-start, 2)
    if not o3d.io.write_triangle_mesh(str(output/'reconstructed_mesh.ply'), mesh):
        raise ValueError('Could not export the reconstructed mesh.')
    (output/'reconstruction_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report
