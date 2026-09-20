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

// A brand sting: the road-V draws itself, fills, its dashes pop, then the
// wordmark arrives. Use it as an intro/outro on any VELRO video.
export const logoRevealSchema = z.object({
  tagline: z.string(),
});

export const LogoReveal: FC<z.infer<typeof logoRevealSchema>> = ({tagline}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, height: H} = useVideoConfig();

  const draw = interpolate(frame, [6, 40], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.ease)});
  const fill = interpolate(frame, [38, 54], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const dash = (i: number) => spring({frame: frame - (52 + i * 5), fps, config: {damping: 200, mass: 0.5}});
  const wordIn = spring({frame: frame - 62, fps, config: {damping: 200}});
  const tagIn = spring({frame: frame - 78, fps, config: {damping: 200}});
  const out = interpolate(frame, [durationInFrames - 14, durationInFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.in(Easing.cubic)});

  const S = Math.round(H * 0.22); // mark size

  return (
    <AbsoluteFill style={{backgroundColor: VELRO.green700, fontFamily: vazirmatn, justifyContent: 'center', alignItems: 'center', overflow: 'hidden'}}>
      <div style={{position: 'absolute', inset: 0, background: `radial-gradient(46% 30% at 50% 44%, ${VELRO.green500}44, transparent 72%)`}} />

      <div style={{position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', opacity: out}}>
        <svg width={S} height={S} viewBox="0 0 108 108">
          {/* the road: stroked outline draws on, then the fill fades in */}
          <path
            d="M54 78 L36 30 L45 30 L54 58 L63 30 L72 30 Z"
            fill="#FFFFFF"
            fillOpacity={fill}
            stroke="#FFFFFF"
            strokeWidth={2.5}
            strokeLinejoin="round"
            strokeLinecap="round"
            pathLength={1}
            strokeDasharray={1}
            strokeDashoffset={1 - draw}
          />
          {/* centre dashes pop in, near → far */}
          <path d="M53 70 h2 v-6 h-2 Z" fill={VELRO.mint} opacity={dash(0)} />
          <path d="M53 60 h2 v-5 h-2 Z" fill={VELRO.mint} opacity={dash(1)} />
          <path d="M53 51 h2 v-4 h-2 Z" fill={VELRO.mint} opacity={dash(2)} />
        </svg>

        <div
          style={{
            marginTop: Math.round(H * 0.03),
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 6,
            opacity: wordIn,
            transform: `translateY(${interpolate(wordIn, [0, 1], [24, 0])}px)`,
          }}
        >
          <span style={{color: '#fff', fontSize: Math.round(H * 0.06), fontWeight: 800, letterSpacing: 8, fontFamily: '"Helvetica Neue", Arial, sans-serif'}}>VELRO</span>
          <span style={{color: VELRO.mint, fontSize: Math.round(H * 0.03), fontWeight: 700}}>ویلرو</span>
        </div>

        <div style={{marginTop: Math.round(H * 0.02), color: VELRO.green50, fontSize: Math.round(H * 0.026), fontWeight: 500, opacity: tagIn}}>{tagline}</div>
      </div>
    </AbsoluteFill>
  );
};
