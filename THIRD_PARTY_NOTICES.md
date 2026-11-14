# Third-party model and infrastructure notices

The optional real vision path uses [Ultralytics YOLOE](https://github.com/ultralytics/ultralytics/tree/v8.4.0),
Ultralytics 8.4.0, and `yoloe-11s-seg-pf.pt`. Upstream provides
[AGPL-3.0 terms](https://github.com/ultralytics/ultralytics/blob/v8.4.0/LICENSE)
and a [commercial licensing option](https://www.ultralytics.com/license).
Preserve upstream copyright/license notices and satisfy applicable source availability
and distribution obligations when conveying or operating a covered combined work.
Making a repository public alone does not settle these obligations. This notice
records dependency terms; it does not grant a commercial exception or relicense
pre-existing repository contributions. No model weights or upstream source trees
are redistributed in this repository.

DINOv2 code and the standard ViT-S/14 pretrained checkpoint use
[Apache-2.0](https://github.com/facebookresearch/dinov2/blob/7764ea0f912e53c92e82eb78a2a1631e92725fc8/LICENSE).
See its [model card](https://github.com/facebookresearch/dinov2/blob/7764ea0f912e53c92e82eb78a2a1631e92725fc8/MODEL_CARD.md).
Torch, TorchVision and other installed packages retain their individual notices
within their distributions; `backend/uv.lock` records exact resolved packages.

Local S3 infrastructure uses PGSTY Silo under AGPL-3.0-or-later; source/license and
pinned image provenance are linked in [the storage decision](docs/adr/0002-silo-object-storage.md).
Grounding DINO, SAM and BERT are retired; historical provenance remains in Git/status
records. PointDiT/DINOv3 licensing and access must be checked separately at future P9.
