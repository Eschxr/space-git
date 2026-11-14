# ADR 0001: Separate reconstruction environment

Status: accepted by the implementation plan.

Use independent backend Python 3.11 and reconstruction Python 3.12 uv projects.
PointDiT GPU dependencies and gated DINOv3 weights must not affect API imports or
the backend resolver. Communicate using versioned JSON, durable database records
and storage references; no shared editable package or root uv workspace.
