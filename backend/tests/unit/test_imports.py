import subprocess
import sys


def test_cpu_only_imports():
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import scene_tracker; import scene_tracker.api.main; "
                "assert not any(k.split('.')[0] in "
                "{'torch', 'sam2', 'dinov2', 'groundingdino', 'reconstruction_worker', "
                "'pointdit', 'numpy', 'pycocotools'} "
                "for k in sys.modules)"
            ),
        ],
        check=True,
    )
