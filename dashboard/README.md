# dashboard/

Web UI (index.html) that connects directly to a webcam/camera and calls the
API in api/app.py. Served automatically together with the API — just run:

    uvicorn api.app:app --reload --port 8000

then open your browser at http://127.0.0.1:8000/ui/

Do not open index.html directly (double-click) — some browsers won't grant
proper API access that way. Always go through the /ui/ address above.
