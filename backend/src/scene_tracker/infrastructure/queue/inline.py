"""Deterministic test dispatcher. Enqueue never executes work in a request handler."""


class InlineDispatcher:
    def __init__(self):
        self.pending = {}

    def enqueue_vision(self, job_id: str, run_id: str, attempt: int) -> None:
        self.pending.setdefault((job_id, run_id, attempt), None)

    def drain(self, runner):
        while self.pending:
            job_id, run_id, _ = next(iter(self.pending))
            del self.pending[(job_id, run_id, _)]
            runner(job_id, run_id)

    def enqueue_reconstruction(self, job_id: str) -> None:
        raise NotImplementedError("Reconstruction scheduling starts in Phase 9")
