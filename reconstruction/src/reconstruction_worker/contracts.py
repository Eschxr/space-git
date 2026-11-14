"""JSON-compatible transport types, independent of backend and GPU packages.

Detailed validated job/artifact schemas are introduced in Phase 9.
"""

from typing import TypedDict


class ReconstructionJob(TypedDict):
    schema_version: int
    reconstruction_id: str
