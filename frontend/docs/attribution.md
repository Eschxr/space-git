# Dependencies and assets

SpaceGit code and the original gallery, SVGs, marker generator and synthetic render generator are MIT licensed. No third-party scene models, photos, footage or splats are bundled. OpenCV generates ArUco markers from its built-in dictionaries. The supplied product spec is reference material and is not redistributed with the public site.

| Direct dependency | License |
| --- | --- |
| Next.js, React, React DOM, Three.js, React Three Fiber, ESLint, FastAPI, Pydantic, pytest | MIT |
| TypeScript, Playwright, OpenCV 4.x, python-multipart | Apache-2.0 |
| Uvicorn, HTTPX, COLMAP | BSD-3-Clause |
| NumPy wheel | BSD-3-Clause, 0BSD, MIT, Zlib, CC0-1.0 |
| Pillow 12.1.1 | MIT-CMU |
| Inter via Fontsource | SIL Open Font License 1.1 (font) |
| SQLite | Public domain |

See the pnpm lockfile and Python requirements for versions; packages have their own notices and may include transitive dependencies. COLMAP is optional and not redistributed by SpaceGit.

Local reconstruction verification used ten photos from the [Single Tree Photogrammetry Dataset](https://github.com/Matt1Up/tree-photogrammetry-dataset), Matthew Guertin (2020), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The smoke test resized the photos and reconstructed a new sparse cloud, surface and texture atlas. The Phase 2 mesh screenshot shows that derivative in the local viewer. The source photos and downloadable reconstruction assets are not bundled with the repository or public demo.
