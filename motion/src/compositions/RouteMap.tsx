import type {FC} from 'react';
import {z} from 'zod';
import {
  AbsoluteFill,
  Audio,
  Easing,
  interpolate,
  Sequence,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {VELRO, vazirmatn} from '../brand';

// An animated route map of the corridor: three town pins appear in turn while a
// car travels Kabul → Charikar → Ghorband, drawing the road behind it. Ends on
// the brand. Prop-driven (Dari + Pashto presets in Root.tsx).
export const routeMapSchema = z.object({
  title: z.string(),
  kabul: z.string(),
  charikar: z.string(),
  ghorband: z.string(),
  tagline: z.string(),
});

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

export const RouteMap: FC<z.infer<typeof routeMapSchema>> = ({title, kabul, charikar, ghorband, tagline}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, width: W, height: H} = useVideoConfig();

  // town positions (Kabul lower-right → Ghorband upper-left)
  const K = {x: W * 0.72, y: H * 0.72};
  const C = {x: W * 0.52, y: H * 0.47};
  const G = {x: W * 0.28, y: H * 0.25};
  const L0 = Math.hypot(C.x - K.x, C.y - K.y);
  const L1 = Math.hypot(G.x - C.x, G.y - C.y);
  const L = L0 + L1;

  const START = 15;
  const END = Math.round(fps * 4.4);
  const carP = interpolate(frame, [START, END], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.inOut(Easing.ease),
  });

  // car position + heading along the polyline
  const d = carP * L;
  let car = K;
  let angle = 0;
  if (d <= L0) {
    const t = L0 === 0 ? 0 : d / L0;
    car = {x: lerp(K.x, C.x, t), y: lerp(K.y, C.y, t)};
    angle = Math.atan2(C.y - K.y, C.x - K.x);
  } else {
    const t = L1 === 0 ? 0 : (d - L0) / L1;
    car = {x: lerp(C.x, G.x, t), y: lerp(C.y, G.y, t)};
    angle = Math.atan2(G.y - C.y, G.x - C.x);
  }

  // traveled route = polyline from Kabul through reached waypoints to the car
  const traveled = [K];
  if (d > L0) traveled.push(C);
  traveled.push(car);
  const traveledPts = traveled.map((p) => `${p.x},${p.y}`).join(' ');

  // pin pop timings
  const reachC = START + (L0 / L) * (END - START);
  const kIn = spring({frame: frame - START, fps, config: {damping: 200}});
  const cIn = spring({frame: frame - reachC, fps, config: {damping: 200}});
  const gIn = spring({frame: frame - END, fps, config: {damping: 200}});

  const brandIn = spring({frame: frame - (END + 8), fps, config: {damping: 200}});
  const titleIn = spring({frame: frame - START, fps, config: {damping: 200}});
  const out = interpolate(frame, [durationInFrames - 16, durationInFrames], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.in(Easing.cubic),
  });

  const Pin: FC<{p: {x: number; y: number}; color: string; label: string; pop: number}> = ({p, color, label, pop}) => (
    <g opacity={pop} transform={`translate(${p.x} ${p.y}) scale(${interpolate(pop, [0, 1], [0.4, 1])})`} style={{transformOrigin: `${p.x}px ${p.y}px`}}>
      <circle r={34} fill={color} opacity={0.18} />
      <circle r={16} fill="#fff" stroke={color} strokeWidth={7} />
      <g transform={`translate(0 -84)`}>
        <rect x={-labelW(label) / 2} y={-30} width={labelW(label)} height={56} rx={28} fill="rgba(6,48,31,0.9)" />
        <text x={0} y={8} textAnchor="middle" fill="#fff" fontSize={34} fontWeight={700} fontFamily={vazirmatn}>
          {label}
        </text>
      </g>
    </g>
  );

  return (
    <AbsoluteFill style={{backgroundColor: VELRO.green900, fontFamily: vazirmatn, overflow: 'hidden'}}>
      {/* driving bed while the car travels, a ding on arrival */}
      <Sequence from={START}>
        <Audio src={staticFile('audio/drive-ambience.mp3')} volume={0.55} />
      </Sequence>
      <Sequence from={END}>
        <Audio src={staticFile('audio/notify.mp3')} volume={0.7} />
      </Sequence>

      {/* soft glow */}
      <div style={{position: 'absolute', inset: 0, background: `radial-gradient(50% 34% at 45% 42%, ${VELRO.green500}44, transparent 72%)`}} />

      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height="100%" style={{position: 'absolute', inset: 0}}>
        {/* faint map dot-grid */}
        <defs>
          <pattern id="dots" width="46" height="46" patternUnits="userSpaceOnUse">
            <circle cx="3" cy="3" r="2.4" fill="rgba(143,217,188,0.10)" />
          </pattern>
        </defs>
        <rect x={0} y={0} width={W} height={H} fill="url(#dots)" opacity={out} />
        {/* faint contour curves for terrain */}
        <path d={`M 0 ${H * 0.58} C ${W * 0.3} ${H * 0.5}, ${W * 0.7} ${H * 0.66}, ${W} ${H * 0.55}`} fill="none" stroke="rgba(143,217,188,0.08)" strokeWidth={4} />
        <path d={`M 0 ${H * 0.34} C ${W * 0.35} ${H * 0.28}, ${W * 0.65} ${H * 0.4}, ${W} ${H * 0.3}`} fill="none" stroke="rgba(143,217,188,0.08)" strokeWidth={4} />

        {/* full route (faint, dashed) */}
        <polyline points={`${K.x},${K.y} ${C.x},${C.y} ${G.x},${G.y}`} fill="none" stroke="rgba(255,255,255,0.18)" strokeWidth={6} strokeDasharray="4 20" strokeLinecap="round" opacity={out} />
        {/* traveled route (bright) */}
        <polyline points={traveledPts} fill="none" stroke={VELRO.mint} strokeWidth={11} strokeLinecap="round" strokeLinejoin="round" opacity={out} />

        {/* pins */}
        <g opacity={out}>
          <Pin p={K} color={VELRO.green500} label={kabul} pop={kIn} />
          <Pin p={C} color={VELRO.mint} label={charikar} pop={cIn} />
          <Pin p={G} color={VELRO.amber} label={ghorband} pop={gIn} />
        </g>

        {/* the car (top-down), hidden once parked at the end */}
        <g transform={`translate(${car.x} ${car.y}) rotate(${(angle * 180) / Math.PI})`} opacity={out * interpolate(frame, [END + 6, END + 18], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}>
          <ellipse cx={0} cy={0} rx={40} ry={40} fill={VELRO.mint} opacity={0.18} />
          <rect x={-30} y={-17} width={60} height={34} rx={12} fill="#ECE7D8" />
          <rect x={6} y={-13} width={16} height={26} rx={6} fill="#1B3A42" />
        </g>
      </svg>

      {/* title, top */}
      <div
        style={{
          position: 'absolute',
          top: H * 0.08,
          width: '100%',
          textAlign: 'center',
          color: '#fff',
          fontSize: Math.round(H * 0.04),
          fontWeight: 700,
          opacity: titleIn * out,
          transform: `translateY(${interpolate(titleIn, [0, 1], [-18, 0])}px)`,
        }}
      >
        {title}
      </div>

      {/* brand, bottom */}
      <div
        style={{
          position: 'absolute',
          bottom: H * 0.07,
          width: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 14,
          opacity: brandIn * out,
          transform: `translateY(${interpolate(brandIn, [0, 1], [24, 0])}px)`,
        }}
      >
        <div style={{display: 'flex', alignItems: 'center', gap: 16, direction: 'ltr'}}>
          <svg width={52} height={52} viewBox="0 0 108 108">
            <rect x="0" y="0" width="108" height="108" rx="26" fill={VELRO.green900} />
            <path d="M54 78 L36 30 L45 30 L54 58 L63 30 L72 30 Z" fill="#fff" />
            <path d="M53 70 h2 v-6 h-2 Z" fill={VELRO.mint} />
            <path d="M53 60 h2 v-5 h-2 Z" fill={VELRO.mint} />
            <path d="M53 51 h2 v-4 h-2 Z" fill={VELRO.mint} />
          </svg>
          <span style={{color: '#fff', fontWeight: 800, fontSize: Math.round(H * 0.032), letterSpacing: 4, fontFamily: '"Helvetica Neue", Arial, sans-serif'}}>VELRO</span>
        </div>
        <div style={{color: VELRO.green50, fontSize: Math.round(H * 0.03), fontWeight: 600}}>{tagline}</div>
      </div>
    </AbsoluteFill>
  );
};

// rough pill width from label length (SVG text can't auto-size a bg)
function labelW(label: string): number {
  return Math.max(120, label.length * 34 + 56);
}
