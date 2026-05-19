#!/usr/bin/env python3
import asyncio
import base64
import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import errors, types
from pydantic import BaseModel

MODEL = "models/lyria-realtime-exp"
CHANNELS = 2
SAMPLE_RATE = 48000
KEY_MAP = {
    "C": "C_MAJOR_A_MINOR",
    "C#": "D_FLAT_MAJOR_B_FLAT_MINOR",
    "D": "D_MAJOR_B_MINOR",
    "D#": "E_FLAT_MAJOR_C_MINOR",
    "E": "E_MAJOR_D_FLAT_MINOR",
    "F": "F_MAJOR_D_MINOR",
    "F#": "G_FLAT_MAJOR_E_FLAT_MINOR",
    "G": "G_MAJOR_E_MINOR",
    "G#": "A_FLAT_MAJOR_F_MINOR",
    "A": "A_MAJOR_G_FLAT_MINOR",
    "A#": "B_FLAT_MAJOR_G_MINOR",
    "B": "B_MAJOR_A_FLAT_MINOR",
}


class StartBody(BaseModel):
    prompt: str
    secondary_prompt: str = ""
    bpm: int = 120
    brightness: float = 0.5
    density: float = 0.5
    key: str = "C"
    temperature: float = 1.0


class PromptBody(BaseModel):
    prompt: str
    secondary_prompt: str = ""


class Engine:
    def __init__(self):
        self.client = None
        self.ctx = None
        self.session = None
        self.recv_task: Optional[asyncio.Task] = None
        self.stream = None
        self.np = None
        self.running = False
        self.chunk_count = 0
        self.last_error = ""

    async def start(self, body: StartBody):
        if self.running:
            raise HTTPException(status_code=400, detail="already running")
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not set")
        if self.client is None:
            self.client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})

        try:
            import numpy as np  # type: ignore
            import sounddevice as sd  # type: ignore

            self.np = np
            self.stream = sd.OutputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16", blocksize=0)
            self.stream.start()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"audio init failed: {e}")

        self.ctx = self.client.aio.live.music.connect(model=MODEL)
        self.session = await self.ctx.__aenter__()
        self.chunk_count = 0
        self.last_error = ""

        async def recv_loop():
            try:
                async for message in self.session.receive():
                    sc = getattr(message, "server_content", None)
                    chunks = getattr(sc, "audio_chunks", None) if sc else None
                    if not chunks:
                        continue
                    for chunk in chunks:
                        data = chunk.data
                        audio = base64.b64decode(data) if isinstance(data, str) else data
                        frames = self.np.frombuffer(audio, dtype=self.np.int16)
                        if len(frames) % CHANNELS != 0:
                            frames = frames[: len(frames) - (len(frames) % CHANNELS)]
                        if len(frames) > 0 and self.stream is not None:
                            self.stream.write(frames.reshape(-1, CHANNELS))
                            self.chunk_count += 1
            except errors.APIError as e:
                if getattr(e, "status_code", None) != 1000 and getattr(e, "code", None) != 1000:
                    self.last_error = str(e)
            except Exception as e:
                self.last_error = str(e)

        self.recv_task = asyncio.create_task(recv_loop())

        prompts = [types.WeightedPrompt(text=body.prompt, weight=1.0)]
        if body.secondary_prompt.strip():
            prompts.append(types.WeightedPrompt(text=body.secondary_prompt.strip(), weight=0.6))

        await self.session.set_weighted_prompts(prompts=prompts)
        cfg = types.LiveMusicGenerationConfig(
            bpm=body.bpm,
            brightness=body.brightness,
            density=body.density,
            temperature=body.temperature,
            scale=getattr(types.Scale, KEY_MAP.get(body.key, "C_MAJOR_A_MINOR")),
        )
        await self.session.set_music_generation_config(config=cfg)
        await self.session.play()
        self.running = True

    async def update_prompt(self, body: PromptBody):
        if not self.running or self.session is None:
            raise HTTPException(status_code=400, detail="not running")
        prompts = [types.WeightedPrompt(text=body.prompt, weight=1.0)]
        if body.secondary_prompt.strip():
            prompts.append(types.WeightedPrompt(text=body.secondary_prompt.strip(), weight=0.6))
        await self.session.set_weighted_prompts(prompts=prompts)

    async def stop(self):
        if not self.running:
            return
        try:
            if self.session is not None:
                try:
                    await self.session.stop()
                except Exception:
                    pass
                try:
                    if self.ctx is not None:
                        await self.ctx.__aexit__(None, None, None)
                except Exception:
                    pass
        finally:
            if self.recv_task:
                self.recv_task.cancel()
                self.recv_task = None
            if self.stream:
                try:
                    self.stream.stop()
                    self.stream.close()
                except Exception:
                    pass
            self.stream = None
            self.session = None
            self.ctx = None
            self.running = False


engine = Engine()
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/start")
async def start(body: StartBody):
    await engine.start(body)
    return {"ok": True}


@app.post("/api/prompt")
async def prompt(body: PromptBody):
    await engine.update_prompt(body)
    return {"ok": True}


@app.post("/api/stop")
async def stop():
    await engine.stop()
    return {"ok": True}


@app.get("/api/status")
async def status():
    return {"running": engine.running, "chunks": engine.chunk_count, "last_error": engine.last_error}
