import type {FC} from 'react';
import {z} from 'zod';
import {zColor} from '@remotion/zod-types';
import {
  AbsoluteFill,
  Easing,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {fontFamily} from '../fonts';

export const lowerThirdSchema = z.object({
  name: z.string(),
  role: z.string(),
  accentColor: zColor(),
});

// A name/role plate that slides in from the left and out again. Sits on a
// neutral backdrop here so you can see it; in real use you'd render it
// transparent (see TransparentOverlay) and lay it over footage.
export const LowerThird: FC<z.infer<typeof lowerThirdSchema>> = ({name, role, accentColor}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, width, height} = useVideoConfig();

  // ENTER — spring in from the left.
  const inP = spring({frame, fps, config: {damping: 200, mass: 0.7}});
  const x = interpolate(inP, [0, 1], [-width * 0.35, 0]);

  // EXIT — slide back out over the last half second.
  const outP = interpolate(
    frame,
    [durationInFrames - Math.round(fps * 0.5), durationInFrames],
    [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.in(Easing.cubic)},
  );
  const outX = interpolate(outP, [0, 1], [0, -width * 0.35]);
  const opacity = interpolate(outP, [0, 1], [1, 0]) * inP;

  const pad = Math.round(height * 0.08);

  return (
    <AbsoluteFill style={{backgroundColor: '#1A1B1E', fontFamily}}>
      <div
        style={{
          position: 'absolute',
          left: pad,
          bottom: pad,
          transform: `translateX(${x + outX}px)`,
          opacity,
          display: 'flex',
          alignItems: 'stretch',
        }}
      >
        {/* accent bar */}
        <div style={{width: Math.round(height * 0.012), backgroundColor: accentColor, borderRadius: 4}} />
        {/* plate */}
        <div
          style={{
            backgroundColor: 'rgba(0,0,0,0.55)',
            padding: `${Math.round(height * 0.028)}px ${Math.round(height * 0.05)}px`,
            marginLeft: Math.round(height * 0.02),
            borderRadius: 8,
          }}
        >
          <div style={{color: '#FFFFFF', fontSize: Math.round(height * 0.05), fontWeight: 700, lineHeight: 1.1}}>
            {name}
          </div>
          <div style={{color: '#B9BCC2', fontSize: Math.round(height * 0.028), fontWeight: 400, marginTop: 6}}>
            {role}
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
