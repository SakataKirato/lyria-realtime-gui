#!/usr/bin/env python3
"""Quickstart script for Gemini Lyria RealTime.

References:
- https://ai.google.dev/gemini-api/docs/realtime-music-generation?hl=ja
- https://zenn.dev/kai_kou/articles/208-lyria-realtime-websocket-music-streaming-guide
"""

import argparse
import asyncio
import base64
import os
import wave
from pathlib import Path

from google import genai
from google.genai import errors
from google.genai import types


DEFAULT_MODEL = "models/lyria-realtime-exp"
DEFAULT_SAMPLE_RATE = 48000
DEFAULT_CHANNELS = 2
DEFAULT_SAMPLE_WIDTH = 2  # PCM16


def pcm_to_wav(pcm_path: Path, wav_path: Path, sample_rate: int, channels: int) -> None:
    """Wrap raw little-endian PCM16 into a WAV container."""
    raw = pcm_path.read_bytes()
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(DEFAULT_SAMPLE_WIDTH)
        wf.setframerate(sample_rate)
        wf.writeframes(raw)


async def generate_music(args: argparse.Namespace) -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    client = genai.Client(
        api_key=api_key,
        http_options={"api_version": "v1alpha"},
    )

    output_pcm = Path(args.output_pcm)
    output_pcm.parent.mkdir(parents=True, exist_ok=True)

    total_bytes = 0
    stop_event = asyncio.Event()
    stream = None
    sd = None
    np = None

    if args.playback:
        try:
            import numpy as np  # type: ignore
            import sounddevice as sd  # type: ignore

            stream = sd.OutputStream(
                samplerate=args.sample_rate,
                channels=args.channels,
                dtype="int16",
                blocksize=0,
            )
            stream.start()
            print("Local playback enabled.")
        except Exception as e:
            print(f"Playback disabled ({e}). Install with: pip install sounddevice numpy")
            stream = None

    async with client.aio.live.music.connect(model=args.model) as session:
        async def receive_audio() -> None:
            nonlocal total_bytes
            try:
                with output_pcm.open("wb") as f:
                    async for message in session.receive():
                        server_content = getattr(message, "server_content", None)
                        if not server_content or not server_content.audio_chunks:
                            continue

                        for chunk in server_content.audio_chunks:
                            data = chunk.data
                            if isinstance(data, str):
                                # Some APIs return base64 text.
                                audio = base64.b64decode(data)
                            else:
                                audio = data
                            f.write(audio)
                            total_bytes += len(audio)
                            if stream is not None and np is not None:
                                frames = np.frombuffer(audio, dtype=np.int16)
                                if len(frames) % args.channels != 0:
                                    usable = len(frames) - (len(frames) % args.channels)
                                    frames = frames[:usable]
                                if len(frames) > 0:
                                    stream.write(frames.reshape(-1, args.channels))

                        if stop_event.is_set():
                            break
            except errors.APIError as e:
                # Normal WebSocket close from the server may surface as APIError(1000).
                if getattr(e, "code", None) != 1000 and getattr(e, "status_code", None) != 1000:
                    raise

        recv_task = asyncio.create_task(receive_audio())

        await session.set_weighted_prompts(
            prompts=[types.WeightedPrompt(text=args.prompt, weight=1.0)]
        )

        await session.set_music_generation_config(
            config=types.LiveMusicGenerationConfig(
                bpm=args.bpm,
                temperature=args.temperature,
            )
        )

        await session.play()

        if args.interactive:
            print("Interactive mode: enter a new prompt to steer music. Type /quit to stop.")
            while True:
                user_input = await asyncio.to_thread(input, "> ")
                prompt = user_input.strip()
                if not prompt:
                    continue
                if prompt in {"/quit", "/exit"}:
                    break
                await session.set_weighted_prompts(
                    prompts=[types.WeightedPrompt(text=prompt, weight=1.0)]
                )
                print(f"Updated prompt: {prompt}")
        else:
            await asyncio.sleep(args.duration)

        stop_event.set()
        await session.stop()

        recv_task.cancel()
        try:
            await recv_task
        except asyncio.CancelledError:
            pass

    print(f"Saved PCM: {output_pcm} ({total_bytes} bytes)")

    if args.output_wav:
        output_wav = Path(args.output_wav)
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        pcm_to_wav(output_pcm, output_wav, args.sample_rate, args.channels)
        print(f"Saved WAV: {output_wav}")
    if stream is not None:
        stream.stop()
        stream.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Gemini Lyria RealTime and save audio")
    parser.add_argument("--prompt", default="minimal techno with deep bass", help="music prompt")
    parser.add_argument("--duration", type=int, default=20, help="generation seconds")
    parser.add_argument("--bpm", type=int, default=100, help="target bpm")
    parser.add_argument("--temperature", type=float, default=1.0, help="sampling temperature")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="model id")
    parser.add_argument("--interactive", action="store_true", help="keep streaming and update prompts interactively")
    parser.add_argument("--playback", action="store_true", help="play audio locally while streaming")
    parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE, help="sample rate")
    parser.add_argument("--channels", type=int, default=DEFAULT_CHANNELS, help="audio channels")
    parser.add_argument("--output-pcm", default="output/lyria_output.pcm", help="raw pcm output path")
    parser.add_argument("--output-wav", default="output/lyria_output.wav", help="optional wav output path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(generate_music(args))


if __name__ == "__main__":
    main()
