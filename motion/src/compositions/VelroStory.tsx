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

// A VELRO-branded VERTICAL story (1080×1920). Shows two things at once:
//  • a composition with its own size, overriding the shared 16:9 canvas
//    (see how it's registered in Root.tsx with width=1080 height=1920);
//  • brand colors, the real road-V mark, RTL Persian text in Vazirmatn.
// Everything still has a clean enter and exit. Edit the text/color live.
export const velroStorySchema = z.object({
  headline: z.string(),
  corridor: z.string(),
});

// The VELRO mark: a road narrowing to a V (white road, mint dashes), same
// geometry as the app icon.
const VelroMark: FC<{size: number}> = ({size}) => (
  <svg width={size} height={size} viewBox="0 0 108 108">
    <path d="M54 78 L36 30 L45 30 L54 58 L63 30 L72 30 Z" fill={VELRO.white} />
    <path d="M53 70 h2 v-6 h-2 Z" fill={VELRO.mint} />
    <path d="M53 60 h2 v-5 h-2 Z" fill={VELRO.mint} />
    <path d="M53 51 h2 v-4 h-2 Z" fill={VELRO.mint} />
  </svg>
);

export const VelroStory: FC<z.infer<typeof velroStorySchema>> = ({headline, corridor}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, height} = useVideoConfig();

  // ENTER — mark pops, headline and corridor follow on their own delays.
  const markIn = spring({frame, fps, config: {damping: 14, mass: 0.7}});
  const headIn = spring({frame: frame - Math.round(fps * 0.25), fps, config: {damping: 200}});
  const corrIn = spring({frame: frame - Math.round(fps * 0.45), fps, config: {damping: 200}});

  // EXIT — fade the whole thing over the last half second.
  const out = interpolate(
    frame,
    [durationInFrames - Math.round(fps * 0.5), durationInFrames],
    [1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.in(Easing.cubic)},
  );

  const chip = Math.round(height * 0.11);

  return (
    <AbsoluteFill
      style={{
        backgroundColor: VELRO.green700,
        fontFamily: vazirmatn,
        justifyContent: 'center',
        alignItems: 'center',
      }}
    >
      {/* two quiet washes for depth */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: `radial-gradient(60% 40% at 18% 22%, ${VELRO.green500}55, transparent 70%),
                       radial-gradient(60% 40% at 85% 88%, ${VELRO.green900}99, transparent 70%)`,
        }}
      />

      <div style={{position: 'relative', textAlign: 'center'}}>
        {/* mark in a rounded chip */}
        <div
          style={{
            width: chip,
            height: chip,
            margin: '0 auto',
            borderRadius: chip * 0.28,
            backgroundColor: VELRO.green900,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            opacity: markIn * out,
            transform: `scale(${interpolate(markIn, [0, 1], [0.7, 1])})`,
            boxShadow: '0 12px 34px rgba(0,0,0,0.28)',
          }}
        >
          <VelroMark size={chip * 0.66} />
        </div>

        {/* headline */}
        <div
          dir="rtl"
          style={{
            color: VELRO.white,
            fontSize: Math.round(height * 0.075),
            fontWeight: 900,
            marginTop: Math.round(height * 0.045),
            opacity: headIn * out,
            transform: `translateY(${interpolate(headIn, [0, 1], [40, 0])}px)`,
          }}
        >
          {headline}
        </div>

        {/* amber spark */}
        <div
          style={{
            width: Math.round(height * 0.06),
            height: 9,
            borderRadius: 999,
            backgroundColor: VELRO.amber,
            margin: `${Math.round(height * 0.022)}px auto 0`,
            opacity: headIn * out,
          }}
        />

        {/* corridor */}
        <div
          dir="rtl"
          style={{
            color: VELRO.green50,
            fontSize: Math.round(height * 0.028),
            fontWeight: 500,
            marginTop: Math.round(height * 0.03),
            opacity: corrIn * out,
            transform: `translateY(${interpolate(corrIn, [0, 1], [24, 0])}px)`,
          }}
        >
          {corridor}
        </div>
      </div>
    </AbsoluteFill>
  );
};
