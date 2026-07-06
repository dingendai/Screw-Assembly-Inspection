"""Web UI sub-system for the screw assembly inspection app.

This package provides a FastAPI-based browser UI that reuses the existing
``valve_gui`` core logic (models, config, storage, inference, camera). The
original PyQt6 desktop GUI is left completely untouched; the two front-ends
share the same ``inspection_data/`` config and CSV files via ``valve_gui.paths``.

Launch with ``python web_main.py`` from the project root.
"""
