#!/usr/bin/env python3
import asyncio
import base64
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, simpledialog
from typing import Optional

from google import genai
from google.genai import errors, types


MODEL = "models/lyria-realtime-exp"
SAMPLE_RATE = 48000
CHANNELS = 2
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


class LyriaEngine:
    def __init__(self, log_fn):
        self.log = log_fn
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

        self.client = None
        self.connect_ctx = None
        self.session = None
        self.recv_task = None
        self.running = False
        self.first_chunk_event: Optional[asyncio.Event] = None

        self.np = None
        self.stream = None

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def call(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    async def start(
        self,
        primary_prompt: str,
        secondary_prompt: str,
        bpm: int,
        temperature: float,
        brightness: float,
        density: float,
        key_name: str,
        output_device=None,
    ):
        if self.running:
            raise RuntimeError("already running")

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")

        if self.client is None:
            self.client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})

        try:
            import numpy as np  # type: ignore
            import sounddevice as sd  # type: ignore

            self.np = np
            self.stream = sd.OutputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=0,
                device=output_device,
            )
            self.stream.start()
        except Exception as e:
            raise RuntimeError(f"audio output init failed: {e}")

        self.connect_ctx = self.client.aio.live.music.connect(model=MODEL)
        self.session = await self.connect_ctx.__aenter__()
        self.log("session connected")
        self.first_chunk_event = asyncio.Event()

        async def receive_audio():
            chunk_count = 0
            try:
                self.log("receive loop started")
                async for message in self.session.receive():
                    sc = getattr(message, "server_content", None)
                    audio_chunks = getattr(sc, "audio_chunks", None) if sc else None
                    if not audio_chunks:
                        continue
                    for chunk in audio_chunks:
                        data = chunk.data
                        audio = base64.b64decode(data) if isinstance(data, str) else data
                        frames = self.np.frombuffer(audio, dtype=self.np.int16)
                        if len(frames) % CHANNELS != 0:
                            usable = len(frames) - (len(frames) % CHANNELS)
                            frames = frames[:usable]
                        if len(frames) > 0 and self.stream is not None:
                            self.stream.write(frames.reshape(-1, CHANNELS))
                            chunk_count += 1
                            if self.first_chunk_event and not self.first_chunk_event.is_set():
                                self.first_chunk_event.set()
                            if chunk_count % 20 == 1:
                                self.log(f"audio chunks: {chunk_count}")
            except errors.APIError as e:
                if getattr(e, "status_code", None) != 1000 and getattr(e, "code", None) != 1000:
                    self.log(f"receive error: {e}")
            except Exception as e:
                self.log(f"receive loop error: {e}")

        self.recv_task = asyncio.create_task(receive_audio())

        prompts = [types.WeightedPrompt(text=primary_prompt, weight=1.0)]
        if secondary_prompt.strip():
            prompts.append(types.WeightedPrompt(text=secondary_prompt.strip(), weight=0.6))

        await self.session.set_weighted_prompts(prompts=prompts)
        cfg = types.LiveMusicGenerationConfig(
            bpm=bpm,
            temperature=temperature,
            brightness=brightness,
            density=density,
            scale=getattr(types.Scale, KEY_MAP[key_name]),
        )
        await self.session.set_music_generation_config(config=cfg)
        await self.session.play()
        self.running = True

    async def update_prompt(self, primary_prompt: str, secondary_prompt: str):
        if not self.running or self.session is None:
            raise RuntimeError("session not running")
        prompts = [types.WeightedPrompt(text=primary_prompt, weight=1.0)]
        if secondary_prompt.strip():
            prompts.append(types.WeightedPrompt(text=secondary_prompt.strip(), weight=0.6))
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
                    if self.connect_ctx is not None:
                        await self.connect_ctx.__aexit__(None, None, None)
                except Exception:
                    pass
                self.connect_ctx = None
        finally:
            if self.recv_task:
                self.recv_task.cancel()
                self.recv_task = None
            if self.stream is not None:
                try:
                    self.stream.stop()
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None
            self.session = None
            self.running = False
            self.first_chunk_event = None


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Lyria RealTime")
        self.root.geometry("1040x720")
        self.log_queue = queue.Queue()
        self.engine = LyriaEngine(self._log_from_thread)

        self.presets = [
            {"name": "Ambient Chill", "p1": "Calm ambient electronic music", "p2": "", "tempo": 80, "brightness": 30, "density": 40, "key": "C"},
            {"name": "Energetic Pop", "p1": "Upbeat pop music with drums", "p2": "", "tempo": 128, "brightness": 70, "density": 65, "key": "G"},
            {"name": "Jazz Fusion", "p1": "Smooth jazz with piano and saxophone", "p2": "", "tempo": 110, "brightness": 55, "density": 50, "key": "D"},
        ]

        self._setup_style()
        self._build_ui()
        self.refresh_devices()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._pump_logs()

    def _setup_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Root.TFrame", background="#0f1029")
        style.configure("Card.TFrame", background="#181a3b")
        style.configure("TLabel", background="#181a3b", foreground="#e7e8ff", font=("Helvetica", 11))
        style.configure("Title.TLabel", background="#0f1029", foreground="#ffffff", font=("Helvetica", 24, "bold"))
        style.configure("Sub.TLabel", background="#0f1029", foreground="#b8b7ff", font=("Helvetica", 12))
        style.configure("TEntry", fieldbackground="#24274c", foreground="#f3f4ff", padding=8)
        style.configure("TCombobox", fieldbackground="#24274c", foreground="#f3f4ff", padding=6)
        style.configure("Accent.TButton", background="#7c4dff", foreground="#ffffff", padding=8, font=("Helvetica", 11, "bold"))
        style.map("Accent.TButton", background=[("active", "#6a3fff")])

    def _build_ui(self):
        rootf = ttk.Frame(self.root, style="Root.TFrame", padding=16)
        rootf.pack(fill="both", expand=True)

        ttk.Label(rootf, text="Lyria RealTime", style="Title.TLabel").pack(anchor="center")
        ttk.Label(rootf, text="Interactive AI Music Generation", style="Sub.TLabel").pack(anchor="center", pady=(0, 14))

        body = ttk.Frame(rootf, style="Root.TFrame")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body, style="Card.TFrame", padding=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right = ttk.Frame(body, style="Card.TFrame", padding=12)
        right.grid(row=0, column=1, sticky="nsew")

        ttk.Label(left, text="Primary Prompt").grid(row=0, column=0, sticky="w")
        self.p1 = tk.StringVar(value="lofi hip hop")
        ttk.Entry(left, textvariable=self.p1).grid(row=1, column=0, sticky="ew", pady=(2, 8))

        ttk.Label(left, text="Secondary Prompt (Blend)").grid(row=2, column=0, sticky="w")
        self.p2 = tk.StringVar(value="")
        ttk.Entry(left, textvariable=self.p2).grid(row=3, column=0, sticky="ew", pady=(2, 12))

        params = ttk.Frame(left, style="Card.TFrame")
        params.grid(row=4, column=0, sticky="ew")
        params.columnconfigure(0, weight=1)

        self.tempo = tk.IntVar(value=120)
        self.brightness = tk.IntVar(value=50)
        self.density = tk.IntVar(value=50)

        self._add_slider(params, "Tempo", self.tempo, 60, 180, " BPM", 0)
        self._add_slider(params, "Brightness", self.brightness, 0, 100, "%", 1)
        self._add_slider(params, "Density", self.density, 0, 100, "%", 2)

        ctl = ttk.Frame(left, style="Card.TFrame")
        ctl.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        ttk.Button(ctl, text="Generate & Play", style="Accent.TButton", command=self.on_start).pack(side="left", padx=(0, 8))
        ttk.Button(ctl, text="Pause/Stop", command=self.on_stop).pack(side="left", padx=(0, 8))
        ttk.Button(ctl, text="Reset", command=self.on_reset).pack(side="left", padx=(0, 8))
        ttk.Button(ctl, text="Save Preset", command=self.on_save_preset).pack(side="left")

        live = ttk.Frame(left, style="Card.TFrame")
        live.grid(row=6, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(live, text="Send Live Prompt", style="Accent.TButton", command=self.on_send_prompt).pack(side="right")

        ttk.Label(right, text="Output Device").pack(anchor="w")
        device_row = ttk.Frame(right, style="Card.TFrame")
        device_row.pack(fill="x", pady=(2, 10))
        self.device_var = tk.StringVar(value="")
        self.device_combo = ttk.Combobox(device_row, textvariable=self.device_var, state="readonly")
        self.device_combo.pack(side="left", fill="x", expand=True)
        ttk.Button(device_row, text="Refresh", command=self.refresh_devices).pack(side="left", padx=(6, 0))

        ttk.Label(right, text="Key Signature").pack(anchor="w")
        self.key = tk.StringVar(value="C")
        key_frame = ttk.Frame(right, style="Card.TFrame")
        key_frame.pack(fill="x", pady=(2, 10))
        ttk.Combobox(key_frame, textvariable=self.key, values=list(KEY_MAP.keys()), state="readonly").pack(fill="x")

        ttk.Label(right, text="Presets").pack(anchor="w")
        self.preset_list = tk.Listbox(right, height=6, bg="#24274c", fg="#ececff", relief="flat")
        self.preset_list.pack(fill="x", pady=(2, 8))
        self.preset_list.bind("<<ListboxSelect>>", self.on_load_preset)
        self._refresh_presets()

        ttk.Label(right, text="Status").pack(anchor="w")
        self.status_lbl = ttk.Label(right, text="idle", background="#181a3b", foreground="#b8b7ff")
        self.status_lbl.pack(anchor="w", pady=(2, 10))

        ttk.Label(right, text="Session Log").pack(anchor="w")
        self.log = tk.Text(right, height=16, bg="#121430", fg="#d9dbff", relief="flat", padx=8, pady=8)
        self.log.pack(fill="both", expand=True)

        left.columnconfigure(0, weight=1)

    def _add_slider(self, parent, label, var, mn, mx, suffix, row):
        frame = ttk.Frame(parent, style="Card.TFrame")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        frame.columnconfigure(0, weight=1)

        text = ttk.Label(frame, text=f"{label}: {var.get()}{suffix}")
        text.grid(row=0, column=0, sticky="w")

        scale = tk.Scale(
            frame,
            from_=mn,
            to=mx,
            orient="horizontal",
            variable=var,
            showvalue=False,
            resolution=1,
            bg="#181a3b",
            fg="#dfe1ff",
            troughcolor="#2e315f",
            highlightthickness=0,
            activebackground="#9e7bff",
        )
        scale.grid(row=1, column=0, sticky="ew")

        def on_move(_):
            text.config(text=f"{label}: {var.get()}{suffix}")

        scale.configure(command=on_move)

    def _refresh_presets(self):
        self.preset_list.delete(0, tk.END)
        for p in self.presets:
            self.preset_list.insert(tk.END, p["name"])

    def on_load_preset(self, _evt):
        sel = self.preset_list.curselection()
        if not sel:
            return
        p = self.presets[sel[0]]
        self.p1.set(p["p1"])
        self.p2.set(p["p2"])
        self.tempo.set(p["tempo"])
        self.brightness.set(p["brightness"])
        self.density.set(p["density"])
        self.key.set(p["key"])
        self._log_from_thread(f"preset loaded: {p['name']}")

    def on_save_preset(self):
        name = simpledialog.askstring("Save Preset", "Preset name:", parent=self.root)
        if not name:
            return
        self.presets.append(
            {
                "name": name,
                "p1": self.p1.get().strip(),
                "p2": self.p2.get().strip(),
                "tempo": int(self.tempo.get()),
                "brightness": int(self.brightness.get()),
                "density": int(self.density.get()),
                "key": self.key.get(),
            }
        )
        self._refresh_presets()
        self._log_from_thread(f"preset saved: {name}")

    def on_reset(self):
        self.p1.set("")
        self.p2.set("")
        self.tempo.set(120)
        self.brightness.set(50)
        self.density.set(50)
        self.key.set("C")
        self._log_from_thread("reset")

    def _log_from_thread(self, msg: str):
        self.log_queue.put(msg)

    def _append_log(self, msg: str):
        self.log.insert("end", msg + "\n")
        self.log.see("end")

    def _pump_logs(self):
        while True:
            try:
                msg = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(msg)
        self.root.after(100, self._pump_logs)

    def set_status(self, text: str):
        self.status_lbl.configure(text=text)

    def on_start(self):
        device_idx = self.device_map.get(self.device_var.get(), None)
        p1 = self.p1.get().strip()
        if not p1:
            self._log_from_thread("primary prompt required")
            return

        self.set_status("connecting...")
        fut = self.engine.call(
            self.engine.start(
                primary_prompt=p1,
                secondary_prompt=self.p2.get().strip(),
                bpm=int(self.tempo.get()),
                temperature=1.0,
                brightness=float(self.brightness.get()) / 100.0,
                density=float(self.density.get()) / 100.0,
                key_name=self.key.get(),
                output_device=device_idx,
            )
        )

        def done(_):
            try:
                fut.result()
                self._log_from_thread("started")
                self.root.after(0, lambda: self.set_status("streaming"))
            except Exception as e:
                self._log_from_thread(f"start failed: {e}")
                self.root.after(0, lambda: self.set_status("error"))

        fut.add_done_callback(done)

    def on_send_prompt(self):
        fut = self.engine.call(self.engine.update_prompt(self.p1.get().strip(), self.p2.get().strip()))

        def done(_):
            try:
                fut.result()
                self._log_from_thread("prompt updated")
            except Exception as e:
                self._log_from_thread(f"prompt update failed: {e}")

        fut.add_done_callback(done)

    def on_stop(self):
        fut = self.engine.call(self.engine.stop())

        def done(_):
            try:
                fut.result()
                self._log_from_thread("stopped")
                self.root.after(0, lambda: self.set_status("idle"))
            except Exception as e:
                self._log_from_thread(f"stop error: {e}")

        fut.add_done_callback(done)

    def refresh_devices(self):
        try:
            import sounddevice as sd  # type: ignore

            devices = sd.query_devices()
            self.device_map = {}
            names = []
            for idx, dev in enumerate(devices):
                if int(dev.get("max_output_channels", 0)) > 0:
                    label = f"{idx}: {dev.get('name', 'unknown')}"
                    names.append(label)
                    self.device_map[label] = idx
            self.device_combo["values"] = names
            if names and not self.device_var.get():
                self.device_var.set(names[0])
            self._log_from_thread(f"output devices: {len(names)}")
        except Exception as e:
            self._log_from_thread(f"device list failed: {e}")

    def on_close(self):
        fut = self.engine.call(self.engine.stop())
        try:
            fut.result(timeout=3)
        except Exception:
            pass
        self.engine.loop.call_soon_threadsafe(self.engine.loop.stop)
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
