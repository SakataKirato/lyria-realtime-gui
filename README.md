# Lyria Realtime

## CSS UI (Figma) + Local Audio Engine

Web UI is in `figma/` (React + CSS). Audio playback runs locally in Python for stability.

### 1) Python backend (local playback)

```bash
python3 -m pip install fastapi uvicorn google-genai sounddevice numpy
export GEMINI_API_KEY="your-api-key"
uvicorn local_control_server:app --host 127.0.0.1 --port 8001
```

### 2) Figma UI frontend

```bash
cd figma
npm install
npm run dev
```

Open: `http://127.0.0.1:5173`

- `Generate & Play` starts Lyria stream
- `Send Live` updates prompt while playing
- Audio is played by Python process on local speakers

## Notes

- This setup is local-only.
- `` also exists as pure desktop fallback.
# lyria-realtime-gui
