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
import {toFa} from '../util';

// Seats fill one by one — VELRO's shared-taxi model: you see the fare and the
// seats before it moves. Top-down car, 4 seats, a counter, then "full".
export const seatFillSchema = z.object({
  title: z.string(),
  fullLabel: z.string(),
  fare: z.string(),
  tagline: z.string(),
});

export const SeatFill: FC<z.infer<typeof seatFillSchema>> = ({title, fullLabel, fare, tagline}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, height: H} = useVideoConfig();

  const SEATS = 4;
  const firstAt = Math.round(fps * 0.6);
  const gap = Math.round(fps * 0.5);
  const seatIn = (i: number) => spring({frame: frame - (firstAt + i * gap), fps, config: {damping: 200, mass: 0.6}});
  const filled = Array.from({length: SEATS}, (_, i) => (seatIn(i) > 0.5 ? 1 : 0)).reduce<number>((a, b) => a + b, 0);
  const fullAt = firstAt + (SEATS - 1) * gap + Math.round(fps * 0.4);
  const fullIn = spring({frame: frame - fullAt, fps, config: {damping: 200}});
  const titleIn = spring({frame, fps, config: {damping: 200}});
  const out = interpolate(frame, [durationInFrames - 16, durationInFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.in(Easing.cubic)});

  const carW = 440;
  const carH = 640;
  const seatSize = 150;
  const seatGap = 40;
  const gridW = seatSize * 2 + seatGap;
  const seatX = (i: number) => (i % 2) * (seatSize + seatGap) - gridW / 2 + seatSize / 2;
  const seatY = (i: number) => Math.floor(i / 2) * (seatSize + seatGap) - (seatSize + seatGap / 2) / 1 + 70;

  const Person: FC<{o: number}> = ({o}) => (
    <g opacity={o} transform={`scale(${interpolate(o, [0, 1], [0.5, 1])})`} style={{transformOrigin: 'center'}}>
      <circle cx={0} cy={-24} r={20} fill="#fff" />
      <path d="M-32 34 A32 32 0 0 1 32 34 Z" fill="#fff" />
    </g>
  );

  return (
    <AbsoluteFill style={{backgroundColor: VELRO.green700, fontFamily: vazirmatn, justifyContent: 'center', alignItems: 'center', overflow: 'hidden'}}>
      <Sequence from={firstAt}>
        <Audio src={staticFile('audio/notify.mp3')} volume={0.4} />
      </Sequence>
      <Sequence from={firstAt + gap}>
        <Audio src={staticFile('audio/notify.mp3')} volume={0.4} />
      </Sequence>
      <Sequence from={firstAt + 2 * gap}>
        <Audio src={staticFile('audio/notify.mp3')} volume={0.4} />
      </Sequence>
      <Sequence from={fullAt}>
        <Audio src={staticFile('audio/notify.mp3')} volume={0.7} />
      </Sequence>

      <div style={{position: 'absolute', inset: 0, background: `radial-gradient(50% 32% at 50% 40%, ${VELRO.green500}44, transparent 72%)`}} />

      {/* title */}
      <div style={{position: 'absolute', top: H * 0.09, width: '100%', textAlign: 'center', color: '#fff', fontSize: Math.round(H * 0.04), fontWeight: 800, opacity: titleIn * out}}>
        {title}
      </div>

      {/* counter */}
      <div style={{position: 'absolute', top: H * 0.16, width: '100%', textAlign: 'center', color: VELRO.mint, fontSize: Math.round(H * 0.03), fontWeight: 700, opacity: titleIn * out}}>
        {toFa(filled)} / {toFa(SEATS)}
      </div>

      {/* top-down car */}
      <svg width={carW} height={carH} viewBox={`${-carW / 2} ${-carH / 2} ${carW} ${carH}`} style={{opacity: out}}>
        <rect x={-carW / 2 + 20} y={-carH / 2 + 20} width={carW - 40} height={carH - 40} rx={90} fill="#101828" />
        <rect x={-carW / 2 + 44} y={-carH / 2 + 44} width={carW - 88} height={150} rx={50} fill="#1B2436" />
        {/* driver seat (always occupied) */}
        <g transform={`translate(${-gridW / 2 + seatSize / 2 + 0} ${-carH / 2 + 250})`}>
          <rect x={-seatSize / 2} y={-seatSize / 2} width={seatSize} height={seatSize} rx={34} fill={VELRO.green900} />
          <g transform="scale(0.8)"><Person o={1} /></g>
        </g>
        {/* passenger seats */}
        {Array.from({length: SEATS}).map((_, i) => {
          const o = seatIn(i);
          return (
            <g key={i} transform={`translate(${seatX(i)} ${seatY(i) + 60})`}>
              <rect x={-seatSize / 2} y={-seatSize / 2} width={seatSize} height={seatSize} rx={34} fill={o > 0.5 ? VELRO.green500 : '#E7ECF3'} />
              <Person o={o} />
            </g>
          );
        })}
      </svg>

      {/* fare + full */}
      <div style={{position: 'absolute', bottom: H * 0.16, width: '100%', textAlign: 'center', opacity: fullIn * out, transform: `translateY(${interpolate(fullIn, [0, 1], [20, 0])}px)`}}>
        <div style={{color: '#fff', fontSize: Math.round(H * 0.05), fontWeight: 900}}>{fullLabel}</div>
        <div style={{color: VELRO.mint, fontSize: Math.round(H * 0.032), fontWeight: 700, marginTop: 10}}>{fare}</div>
      </div>

      {/* tagline */}
      <div style={{position: 'absolute', bottom: H * 0.07, width: '100%', textAlign: 'center', color: VELRO.green50, fontSize: Math.round(H * 0.026), fontWeight: 500, opacity: titleIn * out}}>
        {tagline}
      </div>
    </AbsoluteFill>
  );
};
