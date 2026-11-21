# nAI Web UI
Static HTML/JS for nAI. nai-core serves it at `/`, so normally there is nothing to run separately:
start the backend and open http://localhost:8000.

## Developing the UI on its own
```bash
python -m http.server 5173
# open http://localhost:5173 (talks to the backend on http://localhost:8000 by default;
# change it under Settings)
```
