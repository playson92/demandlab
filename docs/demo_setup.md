# Local demo setup

Follow the [README](../README.md) download instructions before running commands.
Run installation from the extracted project root. Git is optional for the demo.
Python must be 3.12; use uv 0.13.0 for the documented installation. Alternatively,
use Docker with Compose v2. Download/build/install needs internet once. The app
uses local files and has no cloud, external font or author-folder dependency.

The base environment installs NumPy, pandas, PyArrow, Streamlit and Plotly.
`research` adds DuckDB, scikit-learn, MLflow, Excel ingestion and measurement
tools. `dev` adds pytest, Ruff and Playwright. Browser binaries are a separate
developer download: `uv run --no-sync playwright install chromium`. None of
these development tools is needed to run the recruiter demo.

Windows helpers resolve paths relative to their own location and support
PowerShell 5.1. They create a local `.venv` without activation or persistent
global configuration. For development use
`powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1 -Research -Dev`.
For ordinary demo installation omit both switches. Running `run_app.ps1` or
`run_demo.py` never invokes uv or pip.

If a system Python is unavailable on PATH, directly invoke the installed project
interpreter: `.venv\Scripts\python.exe scripts\run_demo.py` on Windows, or
`.venv/bin/python scripts/run_demo.py` on macOS/Linux. The Python launcher accepts
`--port 8517`; Compose uses `DEMANDLAB_PORT`. Loopback is the default. Links with
view/SKU/method parameters are local view addresses, not public hosting links.

If bundled files are missing or corrupt, restore `data/demo/` and `reports/` from
the same complete branch download. Do not generate a replacement demo, train a
model or invoke the research CLI. An incomplete ZIP extraction cannot reproduce
the frozen study. Keep filenames and directories intact.

If the port is busy, select another one. Stop native startup with Ctrl+C. Stop
only this Compose project's service with `docker compose down` from its folder.
The installed native environment and Docker image continue working offline;
repeat synchronization/build only when intentionally installing another version.
