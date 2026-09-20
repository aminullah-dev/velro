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

export const transparentOverlaySchema = z.object({
  label: z.string(),
  accentColor: zColor(),
});

// A badge on a TRANSPARENT background — nothing paints the AbsoluteFill, so the
// alpha channel stays empty everywhere except the badge. In the Studio you'll
// see a checkerboard behind it. Render it with the .mov / PNG commands in the
// README to keep real transparency, then drop it over anything in your editor.
export const TransparentOverlay: FC<z.infer<typeof transparentOverlaySchema>> = ({
  label,
  accentColor,
}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, height} = useVideoConfig();

  // ENTER — pop in with a spring.
  const inP = spring({frame, fps, config: {damping: 14, mass: 0.6}});
  const scale = interpolate(inP, [0, 1], [0.8, 1]);

  // EXIT — fade + shrink slightly over the last half second.
  const outP = interpolate(
    frame,
    [durationInFrames - Math.round(fps * 0.5), durationInFrames],
    [1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.in(Easing.cubic)},
  );

  // A gentle breathing dot, so the badge feels alive while it sits there.
  const pulse = 0.55 + 0.45 * (0.5 + 0.5 * Math.sin((frame / fps) * Math.PI * 2));

  const margin = Math.round(height * 0.06);
  const fs = Math.round(height * 0.03);

  return (
    <AbsoluteFill>
      <div
        style={{
          position: 'absolute',
          top: margin,
          left: margin,
          transformOrigin: 'top left',
          transform: `scale(${scale * interpolate(outP, [0, 1], [0.98, 1])})`,
          opacity: inP * outP,
          display: 'flex',
          alignItems: 'center',
          gap: fs * 0.6,
          backgroundColor: 'rgba(17,18,20,0.9)',
          padding: `${fs * 0.55}px ${fs}px`,
          borderRadius: 999,
          fontFamily,
        }}
      >
        <div
          style={{
            width: fs * 0.55,
            height: fs * 0.55,
            borderRadius: '50%',
            backgroundColor: accentColor,
            opacity: pulse,
          }}
        />
        <span style={{color: '#FFFFFF', fontSize: fs, fontWeight: 600, letterSpacing: 2}}>
          {label}
        </span>
      </div>
    </AbsoluteFill>
  );
};
