import type {FC} from 'react';
import {z} from 'zod';
import {
  AbsoluteFill,
  Easing,
  interpolate,
  interpolateColors,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {VELRO, vazirmatn} from '../brand';

// The corridor from day to night — VELRO keeps running. Sky, sun and moon cycle
// while a car drives across with its headlights coming on after dark.
export const dayToNightSchema = z.object({
  headline: z.string(),
  tagline: z.string(),
});

export const DayToNight: FC<z.infer<typeof dayToNightSchema>> = ({headline, tagline}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, width: W, height: H} = useVideoConfig();

  const HZ = Math.round(H * 0.52);
  // time of day 0 (dawn) → 0.5 (sunset) → 1 (night)
  const t = interpolate(frame, [10, durationInFrames - 24], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.ease)});
  const stops = [0, 0.5, 1];

  const skyTop = interpolateColors(t, stops, ['#6FB7D8', '#EF9E57', '#0B1030']);
  const skyBot = interpolateColors(t, stops, ['#DCEFF3', '#F7D79B', '#1A2550']);
  const hillBack = interpolateColors(t, stops, ['#8FB0A6', '#C08A66', '#22324C']);
  const hillFront = interpolateColors(t, stops, ['#5E8B77', '#8A5E52', '#15203A']);
  const riverCol = interpolateColors(t, stops, ['#8FD0DC', '#F2C889', '#243662']);
  const groundCol = interpolateColors(t, stops, ['#3C6B50', '#6A4A44', '#0E1626']);

  const sunX = interpolate(t, [0, 1], [W * 0.24, W * 0.8]);
  const sunY = interpolate(t, [0, 0.5, 0.72, 1], [H * 0.24, HZ - 30, H * 0.6, H * 0.72]);
  const sunOp = interpolate(t, [0.52, 0.64], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const moonX = interpolate(t, [0.5, 1], [W * 0.32, W * 0.68]);
  const moonY = interpolate(t, [0.5, 1], [H * 0.34, H * 0.16]);
  const nightOp = interpolate(t, [0.55, 0.8], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  const ridge = (yBase: number, amp: number, f1: number, ph: number) => {
    const p: string[] = [`0,${H}`, `0,${yBase}`];
    for (let x = 0; x <= W; x += 16) p.push(`${x},${yBase - amp * (0.6 * Math.sin(x * f1 + ph) + 0.4 * Math.sin(x * f1 * 2.6 + 1.2))}`);
    p.push(`${W},${H}`);
    return p.join(' ');
  };

  const stars = Array.from({length: 30}, (_, i) => ({
    x: (i * 137.5) % W,
    y: ((i * 89.3) % (HZ * 0.8)) + 20,
    r: 1.5 + (i % 3),
    tw: 0.5 + 0.5 * Math.sin((frame / fps) * 3 + i),
  }));

  // car driving across, headlights on at night
  const loop = W + 240;
  const carX = -120 + ((frame * 6) % loop);
  const carY = H * 0.83;
  const cw = 150;
  const ch = 66;

  const titleIn = spring({frame, fps, config: {damping: 200}});
  const out = interpolate(frame, [durationInFrames - 16, durationInFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.in(Easing.cubic)});

  return (
    <AbsoluteFill style={{fontFamily: vazirmatn, overflow: 'hidden'}}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height="100%">
        <defs>
          <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={skyTop} />
            <stop offset="1" stopColor={skyBot} />
          </linearGradient>
        </defs>
        <rect x={0} y={0} width={W} height={HZ + 4} fill="url(#sky)" />

        {/* stars */}
        <g opacity={nightOp}>
          {stars.map((s, i) => (
            <circle key={i} cx={s.x} cy={s.y} r={s.r} fill="#FFFFFF" opacity={0.5 + 0.5 * s.tw} />
          ))}
        </g>

        {/* sun */}
        <circle cx={sunX} cy={sunY} r={70} fill="#FFF3D6" opacity={sunOp} />
        {/* moon */}
        <g opacity={nightOp}>
          <circle cx={moonX} cy={moonY} r={52} fill="#EAF2FF" />
          <circle cx={moonX + 18} cy={moonY - 10} r={52} fill={skyTop} />
        </g>

        {/* hills */}
        <polygon points={ridge(HZ - 30, 120, 0.0032, 1.1)} fill={hillBack} />
        <polygon points={ridge(HZ + 10, 80, 0.0045, 3.3)} fill={hillFront} />

        {/* river + ground */}
        <rect x={0} y={HZ} width={W} height={H - HZ} fill={groundCol} />
        <rect x={0} y={HZ} width={W} height={70} fill={riverCol} />

        {/* road */}
        <rect x={0} y={carY + ch * 0.5} width={W} height={10} fill="rgba(0,0,0,0.25)" />

        {/* car (side view) */}
        <g transform={`translate(${carX} ${carY})`}>
          <ellipse cx={cw / 2} cy={ch * 0.52} rx={cw * 0.5} ry={12} fill="rgba(0,0,0,0.25)" />
          <rect x={0} y={ch * 0.28} width={cw} height={ch * 0.38} rx={14} fill="#ECE7D8" />
          <path d={`M ${cw * 0.22} ${ch * 0.3} Q ${cw * 0.34} ${-ch * 0.02} ${cw * 0.56} ${ch * 0.02} L ${cw * 0.74} ${ch * 0.3} Z`} fill="#ECE7D8" />
          <path d={`M ${cw * 0.3} ${ch * 0.28} Q ${cw * 0.38} ${ch * 0.06} ${cw * 0.53} ${ch * 0.09} L ${cw * 0.62} ${ch * 0.28} Z`} fill="#1B3A42" />
          <circle cx={cw * 0.26} cy={ch * 0.66} r={16} fill="#15181C" />
          <circle cx={cw * 0.74} cy={ch * 0.66} r={16} fill="#15181C" />
          {/* headlight (front = right) at night */}
          <circle cx={cw - 4} cy={ch * 0.44} r={7} fill="#FFE9A8" opacity={nightOp} />
          <polygon points={`${cw},${ch * 0.44} ${cw + 150},${ch * 0.2} ${cw + 150},${ch * 0.7}`} fill="#FFE9A8" opacity={nightOp * 0.25} />
        </g>
      </svg>

      {/* headline */}
      <div style={{position: 'absolute', top: H * 0.09, width: '100%', textAlign: 'center', color: '#fff', fontSize: Math.round(H * 0.05), fontWeight: 900, textShadow: '0 2px 20px rgba(0,0,0,0.35)', opacity: titleIn * out}}>
        {headline}
      </div>

      {/* brand bottom */}
      <div style={{position: 'absolute', bottom: H * 0.06, width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, opacity: titleIn * out}}>
        <div style={{display: 'flex', alignItems: 'center', gap: 14, direction: 'ltr'}}>
          <svg width={46} height={46} viewBox="0 0 108 108">
            <rect x="0" y="0" width="108" height="108" rx="24" fill={VELRO.green900} />
            <path d="M54 78 L36 30 L45 30 L54 58 L63 30 L72 30 Z" fill="#fff" />
            <path d="M53 70 h2 v-6 h-2 Z" fill={VELRO.mint} />
            <path d="M53 60 h2 v-5 h-2 Z" fill={VELRO.mint} />
            <path d="M53 51 h2 v-4 h-2 Z" fill={VELRO.mint} />
          </svg>
          <span style={{color: '#fff', fontWeight: 800, fontSize: Math.round(H * 0.03), letterSpacing: 4, fontFamily: '"Helvetica Neue", Arial, sans-serif', textShadow: '0 2px 16px rgba(0,0,0,0.4)'}}>VELRO</span>
        </div>
        <div style={{color: '#fff', fontSize: Math.round(H * 0.026), fontWeight: 600, textShadow: '0 2px 16px rgba(0,0,0,0.5)'}}>{tagline}</div>
      </div>
    </AbsoluteFill>
  );
};
