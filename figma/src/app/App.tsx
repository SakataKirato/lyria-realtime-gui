import { useEffect, useState } from 'react';
import { Play, Pause, RotateCcw, Save, Music } from 'lucide-react';
import * as Slider from '@radix-ui/react-slider';
import { Button } from './components/Button';
import { Input } from './components/Input';
import { Card } from './components/Card';
import { WaveformVisualizer } from './components/WaveformVisualizer';

const API_BASE = 'http://127.0.0.1:8001';

export default function App() {
  const [isPlaying, setIsPlaying] = useState(false);
  const [prompt, setPrompt] = useState('lofi hip hop');
  const [secondaryPrompt, setSecondaryPrompt] = useState('');
  const [tempo, setTempo] = useState([120]);
  const [brightness, setBrightness] = useState([50]);
  const [density, setDensity] = useState([50]);
  const [keySignature, setKeySignature] = useState(['C']);
  const [status, setStatus] = useState('idle');
  const [chunks, setChunks] = useState(0);
  const [error, setError] = useState('');

  const [presets, setPresets] = useState([
    { name: 'Ambient Chill', prompt: 'Calm ambient electronic music', tempo: 80, brightness: 30, density: 40, key: 'C' },
    { name: 'Energetic Pop', prompt: 'Upbeat pop music with drums', tempo: 128, brightness: 70, density: 65, key: 'G' },
    { name: 'Jazz Fusion', prompt: 'Smooth jazz with piano and saxophone', tempo: 110, brightness: 55, density: 50, key: 'D' },
  ]);

  const keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];

  const pollStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/status`);
      const data = await res.json();
      setChunks(data.chunks ?? 0);
      setError(data.last_error ?? '');
      setStatus(data.running ? 'streaming' : 'idle');
      setIsPlaying(!!data.running);
    } catch {
      setStatus('server offline');
    }
  };

  useEffect(() => {
    void pollStatus();
    const id = setInterval(() => void pollStatus(), 1000);
    return () => clearInterval(id);
  }, []);

  const handlePlayPause = async () => {
    if (isPlaying) {
      await fetch(`${API_BASE}/api/stop`, { method: 'POST' });
      setIsPlaying(false);
      setStatus('idle');
      return;
    }

    setError('');
    const res = await fetch(`${API_BASE}/api/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt,
        secondary_prompt: secondaryPrompt,
        bpm: tempo[0],
        brightness: brightness[0] / 100,
        density: density[0] / 100,
        key: keySignature[0],
        temperature: 1.0,
      }),
    });

    if (!res.ok) {
      setError(await res.text());
      setStatus('error');
      return;
    }

    setIsPlaying(true);
    setStatus('streaming');
  };

  const handleReset = () => {
    setPrompt('');
    setSecondaryPrompt('');
    setTempo([120]);
    setBrightness([50]);
    setDensity([50]);
    setKeySignature(['C']);
  };

  const loadPreset = (preset: (typeof presets)[0]) => {
    setPrompt(preset.prompt);
    setTempo([preset.tempo]);
    setBrightness([preset.brightness]);
    setDensity([preset.density]);
    setKeySignature([preset.key]);
  };

  const savePreset = () => {
    const name = window.prompt('Enter preset name:');
    if (name) {
      setPresets([...presets, { name, prompt, tempo: tempo[0], brightness: brightness[0], density: density[0], key: keySignature[0] }]);
    }
  };

  const sendLivePrompt = async () => {
    const res = await fetch(`${API_BASE}/api/prompt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, secondary_prompt: secondaryPrompt }),
    });
    if (!res.ok) setError(await res.text());
  };

  return (
    <div className="size-full bg-gradient-to-br from-purple-900 via-indigo-900 to-blue-900 text-white p-6 overflow-auto">
      <div className="max-w-7xl mx-auto space-y-6">
        <div className="text-center space-y-2">
          <div className="flex items-center justify-center gap-3">
            <Music className="w-10 h-10" />
            <h1 className="text-4xl font-bold">Lyria RealTime</h1>
          </div>
          <p className="text-purple-200">Interactive AI Music Generation</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <Card>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Primary Prompt</label>
                  <Input value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Describe the music style, genre, instruments..." className="w-full" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Secondary Prompt (Blend)</label>
                  <Input value={secondaryPrompt} onChange={(e) => setSecondaryPrompt(e.target.value)} placeholder="Add another style to blend..." className="w-full" />
                </div>
              </div>
            </Card>

            <Card>
              <h3 className="text-lg font-semibold mb-4">Music Parameters</h3>
              <div className="space-y-6">
                <div>
                  <div className="flex justify-between mb-2"><label className="text-sm font-medium">Tempo</label><span className="text-sm text-purple-300">{tempo[0]} BPM</span></div>
                  <Slider.Root value={tempo} onValueChange={setTempo} min={60} max={180} step={1} className="relative flex items-center select-none touch-none w-full h-5">
                    <Slider.Track className="relative grow rounded-full h-1 bg-purple-300/30"><Slider.Range className="absolute rounded-full h-full bg-gradient-to-r from-purple-500 to-pink-500" /></Slider.Track>
                    <Slider.Thumb className="block w-5 h-5 bg-white rounded-full shadow-lg" />
                  </Slider.Root>
                </div>
                <div>
                  <div className="flex justify-between mb-2"><label className="text-sm font-medium">Brightness</label><span className="text-sm text-purple-300">{brightness[0]}%</span></div>
                  <Slider.Root value={brightness} onValueChange={setBrightness} min={0} max={100} step={1} className="relative flex items-center select-none touch-none w-full h-5">
                    <Slider.Track className="relative grow rounded-full h-1 bg-purple-300/30"><Slider.Range className="absolute rounded-full h-full bg-gradient-to-r from-yellow-500 to-orange-500" /></Slider.Track>
                    <Slider.Thumb className="block w-5 h-5 bg-white rounded-full shadow-lg" />
                  </Slider.Root>
                </div>
                <div>
                  <div className="flex justify-between mb-2"><label className="text-sm font-medium">Density</label><span className="text-sm text-purple-300">{density[0]}%</span></div>
                  <Slider.Root value={density} onValueChange={setDensity} min={0} max={100} step={1} className="relative flex items-center select-none touch-none w-full h-5">
                    <Slider.Track className="relative grow rounded-full h-1 bg-purple-300/30"><Slider.Range className="absolute rounded-full h-full bg-gradient-to-r from-blue-500 to-cyan-500" /></Slider.Track>
                    <Slider.Thumb className="block w-5 h-5 bg-white rounded-full shadow-lg" />
                  </Slider.Root>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Key Signature</label>
                  <div className="grid grid-cols-12 gap-2">
                    {keys.map((key) => (
                      <button key={key} onClick={() => setKeySignature([key])} className={`p-2 rounded text-sm font-medium transition-colors ${keySignature[0] === key ? 'bg-purple-500 text-white' : 'bg-white/10 hover:bg-white/20'}`}>
                        {key}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </Card>

            <Card>
              <div className="flex items-center justify-center gap-4">
                <Button onClick={handlePlayPause} className="px-8 py-4 text-lg font-semibold bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600">
                  {isPlaying ? <><Pause className="w-6 h-6 mr-2" />Pause</> : <><Play className="w-6 h-6 mr-2" />Generate & Play</>}
                </Button>
                <Button onClick={sendLivePrompt} variant="outline" className="px-4 py-4">Send Live</Button>
                <Button onClick={handleReset} variant="outline" className="px-4 py-4"><RotateCcw className="w-5 h-5" /></Button>
                <Button onClick={savePreset} variant="outline" className="px-4 py-4"><Save className="w-5 h-5" /></Button>
              </div>
            </Card>
          </div>

          <div className="space-y-6">
            <Card>
              <h3 className="text-lg font-semibold mb-4">Waveform</h3>
              <WaveformVisualizer isPlaying={isPlaying} />
            </Card>

            <Card>
              <h3 className="text-lg font-semibold mb-4">Presets</h3>
              <div className="space-y-2">
                {presets.map((preset, index) => (
                  <button key={index} onClick={() => loadPreset(preset)} className="w-full p-3 rounded-lg bg-white/5 hover:bg-white/10 transition-colors text-left">
                    <div className="font-medium">{preset.name}</div>
                    <div className="text-xs text-purple-300 mt-1 truncate">{preset.prompt}</div>
                  </button>
                ))}
              </div>
            </Card>

            <Card>
              <h3 className="text-lg font-semibold mb-4">Status</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-purple-300">Audio Quality</span><span className="font-medium">48kHz Stereo</span></div>
                <div className="flex justify-between"><span className="text-purple-300">Status</span><span className="font-medium">{status}</span></div>
                <div className="flex justify-between"><span className="text-purple-300">Audio Chunks</span><span className="font-medium">{chunks}</span></div>
                {!!error && <div className="text-red-300 break-all">{error}</div>}
              </div>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
