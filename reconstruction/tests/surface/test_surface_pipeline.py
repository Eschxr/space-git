import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from surface_pipeline import Settings, process_view, read_cloud


def sphere(count):
    index = np.arange(count)
    y = 1 - 2*(index+.5)/count
    radius = np.sqrt(1-y*y)
    angle = index*np.pi*(3-np.sqrt(5))
    return np.column_stack((radius*np.cos(angle), y, radius*np.sin(angle)))


class SurfacePipelineTest(unittest.TestCase):
    def run_case(self, coordinates, *, rgb=True, ascii=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root/'input.ply', root/'result'
            cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(coordinates))
            if rgb:
                colors = np.column_stack((np.full(len(coordinates), .8), np.full(len(coordinates), .15),
                                          np.full(len(coordinates), .40)))
                cloud.colors = o3d.utility.Vector3dVector(colors)
            self.assertTrue(o3d.io.write_point_cloud(str(source), cloud, write_ascii=ascii))
            original = source.read_bytes()
            stages = []
            report = process_view(source, output, Settings(depth=7), stages.append)
            self.assertEqual(source.read_bytes(), original)
            self.assertGreaterEqual(len(stages), 5)
            restored = read_cloud(output/'cleaned_pointcloud.ply')
            self.assertEqual(restored.has_colors(), rgb)
            self.assertLess(cKDTree(coordinates).query(np.asarray(restored.points))[0].max(), 1e-6)
            mesh = o3d.io.read_triangle_mesh(str(output/'reconstructed_mesh.ply'))
            self.assertTrue(mesh.has_triangles() and mesh.has_vertex_normals())
            self.assertEqual(mesh.has_vertex_colors(), rgb)
            if rgb:
                np.testing.assert_allclose(np.asarray(mesh.vertex_colors)[0], [.8,.15,.4], atol=.006)
            self.assertEqual(report, json.loads((output/'reconstruction_report.json').read_text()))
            self.assertGreaterEqual(report['mesh']['supported_fraction'], .98)
            return report, mesh

    def test_clean_colored_ascii_scan(self):
        points = sphere(1800)
        report, mesh = self.run_case(points, ascii=True)
        self.assertEqual(report['input']['points'], len(points))
        np.testing.assert_allclose(np.ptp(np.asarray(mesh.vertices), axis=0), np.ptp(points, axis=0), atol=.13)

    def test_noisy_scan_drops_isolated_samples(self):
        outliers = np.random.default_rng(14).uniform(5, 15, (22,3))
        report, _ = self.run_case(np.vstack((sphere(1600), outliers)))
        self.assertLessEqual(report['cleaned_points'], 1605)
        self.assertGreater(report['input']['isolated'], 0)

    def test_sparse_scan(self):
        self.run_case(sphere(180))

    def test_scan_with_missing_observations(self):
        points = sphere(1800)
        _, mesh = self.run_case(points[points[:,1]<.55])
        self.assertLess(np.asarray(mesh.vertices)[:,1].max(), .95)

    def test_disconnected_objects_are_not_bridged(self):
        points = sphere(1200)
        report, mesh = self.run_case(np.vstack((points-[2,0,0], points+[2,0,0])))
        self.assertGreaterEqual(report['mesh']['components'], 2)
        self.assertFalse((np.abs(np.asarray(mesh.vertices)[:,0])<.6).any())

    def test_uncoloured_scan(self):
        self.run_case(sphere(1400), rgb=False)

    def test_invalid_vertices(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'invalid.ply'
            path.write_text('ply\nformat ascii 1.0\nelement vertex 24\nproperty float x\n'
                            'property float y\nproperty float z\nend_header\n'+'nan 0 0\n'*24)
            with self.assertRaisesRegex(ValueError, 'non-finite'):
                read_cloud(path)
