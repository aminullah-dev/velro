import type {FC} from 'react';
import {z} from 'zod';
import {
  AbsoluteFill,
  Easing,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {VELRO, vazirmatn} from '../brand';
import {toFa} from '../util';

// Three value props that count up. "۳ محور • ۱ اپ • ۰ دلال."
export const statsCounterSchema = z.object({
  title: z.string(),
  stats: z.array(z.object({value: z.number(), label: z.string()})),
  tagline: z.string(),
});

export const StatsCounter: FC<z.infer<typeof statsCounterSchema>> = ({title, stats, tagline}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, height: H} = useVideoConfig();

  const titleIn = spring({frame, fps, config: {damping: 200}});
  const firstAt = Math.round(fps * 0.5);
  const gap = Math.round(fps * 0.55);
  const out = interpolate(frame, [durationInFrames - 16, durationInFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.in(Easing.cubic)});

  const tagIn = spring({frame: frame - (firstAt + stats.length * gap), fps, config: {damping: 200}});

  return (
    <AbsoluteFill style={{backgroundColor: VELRO.green700, fontFamily: vazirmatn, justifyContent: 'center', alignItems: 'center', overflow: 'hidden'}}>
      <div style={{position: 'absolute', inset: 0, background: `radial-gradient(48% 30% at 50% 40%, ${VELRO.green500}44, transparent 72%)`}} />

      <div style={{position: 'absolute', top: H * 0.1, width: '100%', textAlign: 'center', color: '#fff', fontSize: Math.round(H * 0.045), fontWeight: 900, opacity: titleIn * out}}>
        {title}
      </div>

      <div style={{display: 'flex', flexDirection: 'column', gap: Math.round(H * 0.02), width: '78%'}}>
        {stats.map((s, i) => {
          const at = firstAt + i * gap;
          const pop = spring({frame: frame - at, fps, config: {damping: 200, mass: 0.7}});
          const count = Math.round(interpolate(frame, [at, at + Math.round(fps * 0.7)], [0, s.value], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}));
          return (
            <div
              key={i}
              style={{
                backgroundColor: 'rgba(255,255,255,0.08)',
                borderRadius: 28,
                padding: `${Math.round(H * 0.022)}px ${Math.round(H * 0.03)}px`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                direction: 'rtl',
                opacity: pop * out,
                transform: `translateY(${interpolate(pop, [0, 1], [30, 0])}px)`,
              }}
            >
              <span style={{color: VELRO.green50, fontSize: Math.round(H * 0.038), fontWeight: 600}}>{s.label}</span>
              <span style={{color: VELRO.mint, fontSize: Math.round(H * 0.09), fontWeight: 900, minWidth: '1.4em', textAlign: 'center'}}>{toFa(count)}</span>
            </div>
          );
        })}
      </div>

      <div style={{position: 'absolute', bottom: H * 0.09, width: '100%', textAlign: 'center', color: VELRO.green50, fontSize: Math.round(H * 0.028), fontWeight: 500, opacity: tagIn * out}}>
        {tagline}
      </div>
    </AbsoluteFill>
  );
};
