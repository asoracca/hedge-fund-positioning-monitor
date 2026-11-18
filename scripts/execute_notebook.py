"""Execute the research notebook using the active Python environment."""

from pathlib import Path
import sys
import tempfile
import json
import os
import nbformat
from nbclient import NotebookClient

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as kernel_dir:
    spec = Path(kernel_dir) / "kernels" / "crowding-local"
    spec.mkdir(parents=True)
    (spec / "kernel.json").write_text(
        json.dumps(
            {
                "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                "display_name": "Crowding research",
                "language": "python",
            }
        )
    )
    os.environ["JUPYTER_PATH"] = kernel_dir + os.pathsep + os.environ.get("JUPYTER_PATH", "")
    notebook = nbformat.read(root / "notebooks/01_disclosure_time_research.ipynb", as_version=4)
    NotebookClient(
        notebook, timeout=180, kernel_name="crowding-local", resources={"metadata": {"path": str(root)}}
    ).execute()
    output = root / "outputs/01_disclosure_time_research.executed.ipynb"
    output.parent.mkdir(exist_ok=True)
    nbformat.write(notebook, output)
    print(f"Executed notebook: {output}")
