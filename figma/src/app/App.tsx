import { useEffect, useState } from 'react';
import { Play, Pause, RotateCcw, Music } from 'lucide-react';
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
  const [autoRequest, setAutoRequest] = useState('勉強用のBGMをかけて');

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

  useEffect(() => {
    if (!isPlaying) return;
    const id = setTimeout(() => {
      void fetch(`${API_BASE}/api/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bpm: tempo[0],
          brightness: brightness[0] / 100,
          density: density[0] / 100,
          key: keySignature[0],
          temperature: 1.0,
        }),
      }).then(async (res) => {
        if (!res.ok) setError(await res.text());
      }).catch((e) => setError(String(e)));
    }, 250);
    return () => clearTimeout(id);
  }, [isPlaying, tempo, brightness, density, keySignature]);

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

  const runAutoSetup = async () => {
    setError('');
    const res = await fetch(`${API_BASE}/api/auto-plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_request: autoRequest, auto_apply: true }),
    });
    if (!res.ok) {
      setError(await res.text());
      return;
    }
    const data = await res.json();
    const plan = data?.plan;
    if (!plan) return;
    const wp = plan.weighted_prompts || [];
    if (wp[0]?.text) setPrompt(wp[0].text);
    setSecondaryPrompt([wp[1]?.text, wp[2]?.text].filter(Boolean).join(', '));
    if (typeof plan.bpm === 'number') setTempo([plan.bpm]);
    if (typeof plan.brightness === 'number') setBrightness([Math.round(plan.brightness * 100)]);
    if (typeof plan.density === 'number') setDensity([Math.round(plan.density * 100)]);
    if (typeof plan.key === 'string') setKeySignature([plan.key]);
    if (data.applied) setStatus('streaming (auto-applied)');
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
                  <label className="block text-sm font-medium mb-2">Auto Setup Request</label>
                  <div className="flex gap-2">
                    <Input value={autoRequest} onChange={(e) => setAutoRequest(e.target.value)} placeholder="例: 勉強用のBGMをかけて" className="w-full" />
                    <Button onClick={runAutoSetup} variant="outline" className="px-4 py-2 whitespace-nowrap">Auto Setup</Button>
                  </div>
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
                <Button onClick={handleReset} variant="outline" className="px-4 py-4"><RotateCcw className="w-5 h-5" /></Button>
              </div>
            </Card>
          </div>

          <div className="space-y-6">
            <Card>
              <h3 className="text-lg font-semibold mb-4">Waveform</h3>
              <WaveformVisualizer isPlaying={isPlaying} />
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
