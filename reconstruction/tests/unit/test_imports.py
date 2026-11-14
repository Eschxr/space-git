from reconstruction_worker.contracts import ReconstructionJob


def test_contract_import():
    job: ReconstructionJob = {"schema_version": 1, "reconstruction_id": "example"}
    assert job["schema_version"] == 1
