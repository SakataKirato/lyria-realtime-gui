import { useEffect, useRef } from 'react';

interface WaveformVisualizerProps {
  isPlaying: boolean;
}

export function WaveformVisualizer({ isPlaying }: WaveformVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number>();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;

    let phase = 0;

    const draw = () => {
      ctx.fillStyle = 'rgba(0, 0, 0, 0.1)';
      ctx.fillRect(0, 0, width, height);

      if (isPlaying) {
        const barCount = 64;
        const barWidth = width / barCount;

        for (let i = 0; i < barCount; i++) {
          const frequency = (i / barCount) * Math.PI * 2;
          const amplitude = Math.sin(frequency * 2 + phase) * 0.3 + 0.7;
          const noise = Math.random() * 0.2;
          const barHeight = (amplitude + noise) * height * 0.4;

          const hue = 280 + (i / barCount) * 60;
          ctx.fillStyle = `hsla(${hue}, 70%, 60%, 0.8)`;

          const x = i * barWidth;
          const y = (height - barHeight) / 2;

          ctx.fillRect(x, y, barWidth - 2, barHeight);
        }

        phase += 0.05;
      } else {
        ctx.strokeStyle = 'rgba(168, 85, 247, 0.3)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(0, height / 2);
        ctx.lineTo(width, height / 2);
        ctx.stroke();
      }

      animationRef.current = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [isPlaying]);

  return (
    <canvas
      ref={canvasRef}
      width={300}
      height={200}
      className="w-full rounded-lg bg-black/20"
    />
  );
}
