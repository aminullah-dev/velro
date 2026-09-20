import type {FC} from 'react';
import {z} from 'zod';
import {
  AbsoluteFill,
  Audio,
  Easing,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {VELRO, vazirmatn} from '../brand';

// The Ghorband riverside drive, rebuilt inside Remotion — a car moving along a
// road beside the river, mountains behind, "به‌زودی" over it. The whole scene is
// a pure function of the current frame (SVG built from a 1/z projection), so
// you can scrub the timeline and it renders identically every time.
//
// Text is prop-driven: swap `headline` to "ډېر ژر" for the Pashto version.
export const ghorbandDriveSchema = z.object({
  headline: z.string(),
  corridor: z.string(),
});

export const GhorbandDrive: FC<z.infer<typeof ghorbandDriveSchema>> = ({headline, corridor}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, width: W, height: H} = useVideoConfig();

  // ── projection (a flat-ground racer: screen Y = horizon + k/z) ──
  const HZ = Math.round(H * 0.46);
  const VPX = W * 0.5;
  const Znear = 4;
  const Zfar = 64;
  const rangeZ = Zfar - Znear;
  const XK = 116;
  const RW = 2.4;
  const dashGap = 2.4;
  const dashLen = 1.15;
  const dashHalf = 0.15;
  const riverW = 3.6;
  const riverGap = 0.7;
  const LOOP = 32;
  const carZ = 7;
  const carW = 2.2;

  const SPEED = 5.3; // world units per second — the sense of pace
  const travel = (frame / fps) * SPEED;
  const bendFreq = (2 * Math.PI) / LOOP;

  const projY = (z: number) => HZ + (H - HZ) * (Znear / z);
  const projS = (z: number) => Znear / z;
  const sx = (x: number, z: number) => VPX + x * projS(z) * XK;
  const roadC = (z: number) => 1.7 * Math.sin((z + travel) * bendFreq);
  const riverC = (z: number) => roadC(z) - (RW + riverGap + riverW / 2);
  const wrap = (v: number, m: number) => ((v % m) + m) % m;

  // ── build the ground bands as point strings ──
  const band = (xL: (z: number) => number, xR: (z: number) => number) => {
    const p: string[] = [];
    for (let z = Zfar; z >= Znear; z -= 0.6) p.push(`${sx(xL(z), z)},${projY(z)}`);
    for (let z = Znear; z <= Zfar; z += 0.6) p.push(`${sx(xR(z), z)},${projY(z)}`);
    return p.join(' ');
  };
  const edgeLine = (x: (z: number) => number) => {
    const p: string[] = [];
    for (let z = Zfar; z >= Znear; z -= 0.6) p.push(`${sx(x(z), z)},${projY(z)}`);
    return p.join(' ');
  };

  // dashes on the centre line
  const dashes: string[] = [];
  for (let k = 0; k < rangeZ / dashGap + 2; k++) {
    const z = Znear + wrap(k * dashGap - travel, rangeZ);
    if (z + dashLen > Zfar) continue;
    dashes.push(
      [
        `${sx(roadC(z + dashLen) - dashHalf, z + dashLen)},${projY(z + dashLen)}`,
        `${sx(roadC(z + dashLen) + dashHalf, z + dashLen)},${projY(z + dashLen)}`,
        `${sx(roadC(z) + dashHalf, z)},${projY(z)}`,
        `${sx(roadC(z) - dashHalf, z)},${projY(z)}`,
      ].join(' '),
    );
  }

  // ridge silhouettes
  const ridge = (yBase: number, amp: number, f1: number, ph: number) => {
    const p: string[] = [`0,${HZ + 2}`];
    for (let x = 0; x <= W; x += 14) {
      const y = yBase - amp * (0.6 * Math.sin(x * f1 + ph) + 0.4 * Math.sin(x * f1 * 2.7 + 1.3));
      p.push(`${x},${y}`);
    }
    p.push(`${W},${HZ + 2}`);
    return p.join(' ');
  };
  const sway = 10 * Math.sin((frame / fps) * 0.4);

  // ── the car, at a fixed depth (camera follows it) ──
  const s = projS(carZ) * XK;
  const cx = sx(roadC(carZ), carZ);
  const cy = projY(carZ) + Math.sin((frame / fps) * Math.PI * 2 * 1.5) * 4;
  const bw = carW * s;
  const bh = bw * 0.72;

  // ── overlay enter / exit ──
  const topIn = spring({frame, fps, config: {damping: 200}});
  const botIn = spring({frame: frame - Math.round(fps * 0.2), fps, config: {damping: 200}});
  const out = interpolate(
    frame,
    [durationInFrames - Math.round(fps * 0.5), durationInFrames],
    [1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.in(Easing.cubic)},
  );

  return (
    <AbsoluteFill style={{backgroundColor: '#E7F0EA'}}>
      {/* Driving ambience (engine + wind). A synthesized 6s bed in public/audio.
          Swap it for your own file, and offset the start with a <Sequence>. */}
      <Audio src={staticFile('audio/drive-ambience.mp3')} volume={0.8} />

      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height="100%">
        {/* sky */}
        <rect x={0} y={0} width={W} height={HZ + 2} fill="#E7F0EA" />
        <rect x={0} y={HZ - 130} width={W} height={132} fill="#F3EAD6" />
        <circle cx={W * 0.5} cy={HZ - 150} r={96} fill="#FBF3DE" />
        {/* mountains */}
        <polygon points={ridge(HZ - 40, 118, 0.0034, 1.1 + sway * 0.002)} fill="#AEC4BA" />
        <polygon points={ridge(HZ + 6, 78, 0.0046, 3.4 - sway * 0.002)} fill="#8AAA9A" />
        {/* ground */}
        <rect x={0} y={HZ} width={W} height={H - HZ} fill="#316049" />
        {/* river */}
        <polygon points={band((z) => riverC(z) - riverW / 2, (z) => riverC(z) + riverW / 2)} fill="#4894A1" />
        <polyline points={edgeLine((z) => riverC(z) + riverW / 2)} fill="none" stroke="rgba(226,244,247,.5)" strokeWidth={4} />
        {/* road */}
        <polygon points={band((z) => roadC(z) - RW, (z) => roadC(z) + RW)} fill="#262B31" />
        <polyline points={edgeLine((z) => roadC(z) - (RW - 0.07))} fill="none" stroke="rgba(240,240,236,.28)" strokeWidth={5} />
        <polyline points={edgeLine((z) => roadC(z) + (RW - 0.07))} fill="none" stroke="rgba(240,240,236,.28)" strokeWidth={5} />
        {dashes.map((pts, i) => (
          <polygon key={i} points={pts} fill="#F1F1EC" />
        ))}
        {/* car (from behind) */}
        <g transform={`translate(${cx} ${cy})`}>
          <ellipse cx={0} cy={bh * 0.06} rx={bw * 0.6} ry={bh * 0.15} fill="rgba(0,0,0,.22)" />
          <rect x={-bw * 0.5} y={-bh * 0.02} width={bw * 0.15} height={bh * 0.28} fill="#15181C" />
          <rect x={bw * 0.35} y={-bh * 0.02} width={bw * 0.15} height={bh * 0.28} fill="#15181C" />
          <rect x={-bw * 0.5} y={-bh * 0.62} width={bw} height={bh * 0.72} rx={bw * 0.12} fill="#ECE7D8" />
          <rect x={-bw * 0.33} y={-bh * 1.0} width={bw * 0.66} height={bh * 0.5} rx={bw * 0.11} fill="#E4DDCB" />
          <rect x={-bw * 0.27} y={-bh * 0.9} width={bw * 0.54} height={bh * 0.32} rx={bw * 0.06} fill="#1B3A42" />
          <rect x={-bw * 0.45} y={-bh * 0.32} width={bw * 0.15} height={bh * 0.15} rx={bw * 0.03} fill="#E24A3B" />
          <rect x={bw * 0.3} y={-bh * 0.32} width={bw * 0.15} height={bh * 0.15} rx={bw * 0.03} fill="#E24A3B" />
        </g>
      </svg>

      {/* overlay — brand wordmark up top, headline + corridor at the bottom */}
      <AbsoluteFill>
        {/* top: mark + VELRO in brand green on the pale sky */}
        <div
          style={{
            position: 'absolute',
            top: Math.round(H * 0.06),
            width: '100%',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            gap: 18,
            opacity: topIn * out,
            transform: `translateY(${interpolate(topIn, [0, 1], [-20, 0])}px)`,
          }}
        >
          <svg width={Math.round(H * 0.035)} height={Math.round(H * 0.035)} viewBox="0 0 108 108">
            <path d="M54 78 L36 30 L45 30 L54 58 L63 30 L72 30 Z" fill={VELRO.green700} />
            <path d="M53 70 h2 v-6 h-2 Z" fill={VELRO.green500} />
            <path d="M53 60 h2 v-5 h-2 Z" fill={VELRO.green500} />
            <path d="M53 51 h2 v-4 h-2 Z" fill={VELRO.green500} />
          </svg>
          <span
            style={{
              fontFamily: '"Helvetica Neue", Arial, sans-serif',
              fontWeight: 800,
              fontSize: Math.round(H * 0.03),
              letterSpacing: 4,
              color: VELRO.green700,
            }}
          >
            VELRO
          </span>
        </div>

        {/* bottom: scrim + headline + corridor */}
        <div
          style={{
            position: 'absolute',
            bottom: 0,
            width: '100%',
            height: Math.round(H * 0.25),
            background: 'linear-gradient(to bottom, rgba(9,36,24,0), rgba(9,36,24,.55) 50%, rgba(9,36,24,.9))',
          }}
        />
        <div
          dir="rtl"
          style={{
            position: 'absolute',
            bottom: Math.round(H * 0.11),
            width: '100%',
            textAlign: 'center',
            fontFamily: vazirmatn,
            fontWeight: 900,
            fontSize: Math.round(H * 0.055),
            color: VELRO.white,
            opacity: botIn * out,
            transform: `translateY(${interpolate(botIn, [0, 1], [26, 0])}px)`,
          }}
        >
          {headline}
        </div>
        <div
          dir="rtl"
          style={{
            position: 'absolute',
            bottom: Math.round(H * 0.075),
            width: '100%',
            textAlign: 'center',
            fontFamily: vazirmatn,
            fontWeight: 500,
            fontSize: Math.round(H * 0.026),
            color: VELRO.green50,
            opacity: botIn * out,
          }}
        >
          {corridor}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
