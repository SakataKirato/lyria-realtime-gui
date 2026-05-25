#!/usr/bin/env python3
import asyncio
import base64
import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import errors, types
from pydantic import BaseModel

MODEL = "models/lyria-realtime-exp"
PLANNER_MODEL = os.environ.get("GEMINI_PLANNER_MODEL", "gemini-3.1-flash-lite")
PROMPT_TEMPLATE_PATH = Path("prompt_for_gemini31_flash_lite.txt")
DEFAULT_OUTPUT_DEVICE_ID = int(os.environ.get("LYRIA_OUTPUT_DEVICE_ID", "5"))
CHANNELS = 2
SAMPLE_RATE = 48000

KEY_TO_SCALE = {
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
SCALE_TO_KEY = {v: k for k, v in KEY_TO_SCALE.items()}
VALID_SCALES = set(SCALE_TO_KEY.keys())
SCALE_ALIASES = {
    "A_MINOR_C_MAJOR": "C_MAJOR_A_MINOR",
    "C#_MAJOR_A#_MINOR": "D_FLAT_MAJOR_B_FLAT_MINOR",
    "Db_MAJOR_Bb_MINOR": "D_FLAT_MAJOR_B_FLAT_MINOR",
    "Eb_MAJOR_C_MINOR": "E_FLAT_MAJOR_C_MINOR",
    "Gb_MAJOR_Eb_MINOR": "G_FLAT_MAJOR_E_FLAT_MINOR",
    "Ab_MAJOR_F_MINOR": "A_FLAT_MAJOR_F_MINOR",
    "Bb_MAJOR_G_MINOR": "B_FLAT_MAJOR_G_MINOR",
}


class WeightedPromptIn(BaseModel):
    text: str
    weight: float


class StartBody(BaseModel):
    prompt: str
    secondary_prompt: str = ""
    weighted_prompts: Optional[list[WeightedPromptIn]] = None
    bpm: int = 120
    brightness: float = 0.5
    density: float = 0.5
    key: str = "C"
    temperature: float = 1.0


class PromptBody(BaseModel):
    prompt: str
    secondary_prompt: str = ""
    weighted_prompts: Optional[list[WeightedPromptIn]] = None


class ConfigBody(BaseModel):
    bpm: Optional[int] = None
    brightness: Optional[float] = None
    density: Optional[float] = None
    key: Optional[str] = None
    temperature: Optional[float] = None


class AutoPlanBody(BaseModel):
    user_request: str
    auto_apply: bool = True


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
        self.current_bpm: Optional[int] = None
        self.current_brightness: Optional[float] = None
        self.current_density: Optional[float] = None
        self.current_key: Optional[str] = None
        self.current_temperature: Optional[float] = None
        self.planner_last_request: str = ""
        self.planner_last_prompt: str = ""
        self.planner_last_raw_response: str = ""
        self.planner_last_plan: Optional[dict] = None

    def _ensure_client(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not set")
        if self.client is None:
            self.client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})

    @staticmethod
    def _normalize_weighted_prompts(raw: list[dict]) -> list[dict]:
        items = raw[:3]
        while len(items) < 3:
            defaults = ["lo-fi", "soft piano", "focused"]
            items.append({"text": defaults[len(items)], "weight": [0.5, 0.3, 0.2][len(items)]})

        texts = [str(items[i].get("text", "")).strip() or ["lo-fi", "soft piano", "focused"][i] for i in range(3)]
        weights = []
        for i in range(3):
            try:
                w = float(items[i].get("weight", 0.0))
            except Exception:
                w = 0.0
            if w <= 0:
                w = [0.5, 0.3, 0.2][i]
            weights.append(w)

        total = sum(weights)
        if total <= 0:
            weights = [0.5, 0.3, 0.2]
            total = 1.0
        weights = [round(w / total, 3) for w in weights]
        weights[2] = round(1.0 - weights[0] - weights[1], 3)
        if weights[2] <= 0:
            weights = [0.5, 0.3, 0.2]

        return [{"text": texts[i], "weight": weights[i]} for i in range(3)]

    @staticmethod
    def _normalize_scale(scale: str) -> str:
        s = (scale or "").strip()
        if s in VALID_SCALES:
            return s
        return SCALE_ALIASES.get(s, "C_MAJOR_A_MINOR")

    @staticmethod
    def _clamp(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, v))

    @staticmethod
    def _weighted_prompts_to_sdk(weighted_prompts: list[dict]) -> list[types.WeightedPrompt]:
        return [types.WeightedPrompt(text=p["text"], weight=float(p["weight"])) for p in weighted_prompts]

    async def start(self, body: StartBody):
        if self.running:
            raise HTTPException(status_code=400, detail="already running")
        self._ensure_client()

        try:
            import numpy as np  # type: ignore
            import sounddevice as sd  # type: ignore

            self.np = np
            self.stream = sd.OutputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=0,
                device=DEFAULT_OUTPUT_DEVICE_ID,
            )
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

        if body.weighted_prompts:
            wp = self._normalize_weighted_prompts([p.model_dump() for p in body.weighted_prompts])
            prompts = self._weighted_prompts_to_sdk(wp)
        else:
            prompts = [types.WeightedPrompt(text=body.prompt, weight=1.0)]
            if body.secondary_prompt.strip():
                prompts.append(types.WeightedPrompt(text=body.secondary_prompt.strip(), weight=0.6))

        await self.session.set_weighted_prompts(prompts=prompts)
        cfg = types.LiveMusicGenerationConfig(
            bpm=int(self._clamp(body.bpm, 60, 200)),
            brightness=self._clamp(body.brightness, 0.0, 1.0),
            density=self._clamp(body.density, 0.0, 1.0),
            temperature=body.temperature,
            scale=getattr(types.Scale, KEY_TO_SCALE.get(body.key, "C_MAJOR_A_MINOR")),
        )
        await self.session.set_music_generation_config(config=cfg)
        await self.session.play()
        self.current_bpm = int(self._clamp(body.bpm, 60, 200))
        self.current_brightness = self._clamp(body.brightness, 0.0, 1.0)
        self.current_density = self._clamp(body.density, 0.0, 1.0)
        self.current_key = body.key
        self.current_temperature = body.temperature
        self.running = True

    async def update_prompt(self, body: PromptBody):
        if not self.running or self.session is None:
            raise HTTPException(status_code=400, detail="not running")
        if body.weighted_prompts:
            wp = self._normalize_weighted_prompts([p.model_dump() for p in body.weighted_prompts])
            prompts = self._weighted_prompts_to_sdk(wp)
        else:
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
            self.current_bpm = None
            self.current_brightness = None
            self.current_density = None
            self.current_key = None
            self.current_temperature = None

    async def update_config(
        self,
        bpm: Optional[int],
        brightness: Optional[float],
        density: Optional[float],
        key: Optional[str],
        temperature: Optional[float],
    ):
        if not self.running or self.session is None:
            raise HTTPException(status_code=400, detail="not running")

        next_bpm = self.current_bpm if bpm is None else int(self._clamp(bpm, 60, 200))
        next_brightness = self.current_brightness if brightness is None else self._clamp(brightness, 0.0, 1.0)
        next_density = self.current_density if density is None else self._clamp(density, 0.0, 1.0)
        next_key = self.current_key if key is None else key
        next_temperature = self.current_temperature if temperature is None else temperature

        cfg = types.LiveMusicGenerationConfig(
            bpm=next_bpm,
            brightness=next_brightness,
            density=next_density,
            temperature=next_temperature,
            scale=getattr(types.Scale, KEY_TO_SCALE.get(next_key or "C", "C_MAJOR_A_MINOR")),
        )
        await self.session.set_music_generation_config(config=cfg)

        needs_reset = False
        if bpm is not None and bpm != self.current_bpm:
            needs_reset = True
        if key is not None and key != self.current_key:
            needs_reset = True
        if needs_reset:
            await self.session.reset_context()

        self.current_bpm = next_bpm
        self.current_brightness = next_brightness
        self.current_density = next_density
        self.current_key = next_key
        self.current_temperature = next_temperature

    async def auto_plan(self, user_request: str) -> dict:
        self._ensure_client()
        if not PROMPT_TEMPLATE_PATH.exists():
            raise HTTPException(status_code=500, detail=f"missing prompt template: {PROMPT_TEMPLATE_PATH}")

        tmpl = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
        planner_prompt = tmpl.replace("{{USER_REQUEST}}", user_request)
        self.planner_last_request = user_request
        self.planner_last_prompt = planner_prompt

        try:
            resp = await asyncio.to_thread(
                self.client.models.generate_content,
                model=PLANNER_MODEL,
                contents=planner_prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"planner call failed: {e}")

        text = (resp.text or "").strip()
        self.planner_last_raw_response = text
        print("[planner] user_request:", user_request)
        print("[planner] raw_response:", text[:2000])
        if not text:
            raise HTTPException(status_code=500, detail="planner returned empty response")
        try:
            obj = json.loads(text)
        except Exception:
            raise HTTPException(status_code=500, detail=f"planner returned non-json: {text[:200]}")

        raw_wp = obj.get("weighted_prompts") or []
        wp = self._normalize_weighted_prompts(raw_wp)

        scale = self._normalize_scale(str(obj.get("scale", "C_MAJOR_A_MINOR")))
        key = SCALE_TO_KEY.get(scale, "C")

        plan = {
            "weighted_prompts": wp,
            "bpm": int(self._clamp(float(obj.get("bpm", 100)), 60, 200)),
            "scale": scale,
            "key": key,
            "mute_bass": bool(obj.get("mute_bass", False)),
            "mute_drums": bool(obj.get("mute_drums", False)),
            "only_bass_and_drums": bool(obj.get("only_bass_and_drums", False)),
            "density": round(self._clamp(float(obj.get("density", 0.5)), 0.0, 1.0), 3),
            "brightness": round(self._clamp(float(obj.get("brightness", 0.5)), 0.0, 1.0), 3),
        }

        if plan["only_bass_and_drums"]:
            plan["mute_bass"] = False
            plan["mute_drums"] = False

        self.planner_last_plan = plan
        return plan


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


@app.post("/api/config")
async def config(body: ConfigBody):
    await engine.update_config(
        bpm=body.bpm,
        brightness=body.brightness,
        density=body.density,
        key=body.key,
        temperature=body.temperature,
    )
    return {"ok": True}


@app.post("/api/auto-plan")
async def auto_plan(body: AutoPlanBody):
    plan = await engine.auto_plan(body.user_request)

    applied = False
    apply_note = ""
    if body.auto_apply and engine.running:
        await engine.update_prompt(
            PromptBody(
                prompt=plan["weighted_prompts"][0]["text"],
                secondary_prompt="",
                weighted_prompts=[WeightedPromptIn(**p) for p in plan["weighted_prompts"]],
            )
        )
        await engine.update_config(
            bpm=plan["bpm"],
            brightness=plan["brightness"],
            density=plan["density"],
            key=plan["key"],
            temperature=1.0,
        )
        applied = True
        apply_note = "Applied prompt + bpm + key + brightness + density during playback."

    return {"ok": True, "plan": plan, "applied": applied, "apply_note": apply_note, "planner_model": PLANNER_MODEL}


@app.get("/api/status")
async def status():
    return {
        "running": engine.running,
        "chunks": engine.chunk_count,
        "last_error": engine.last_error,
        "planner_model": PLANNER_MODEL,
    }


@app.get("/api/planner-log")
async def planner_log():
    return {
        "planner_model": PLANNER_MODEL,
        "last_user_request": engine.planner_last_request,
        "last_prompt": engine.planner_last_prompt,
        "last_raw_response": engine.planner_last_raw_response,
        "last_plan": engine.planner_last_plan,
    }
