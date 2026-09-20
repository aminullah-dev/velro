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

export const kineticTextSchema = z.object({
  words: z.array(z.string()),
  backgroundColor: zColor(),
  textColor: zColor(),
});

// Words snap in one after another, then the whole line lifts out. Add or
// remove words in the schema panel and the timing re-flows automatically.
export const KineticText: FC<z.infer<typeof kineticTextSchema>> = ({
  words,
  backgroundColor,
  textColor,
}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, height} = useVideoConfig();

  const stagger = Math.round(fps * 0.12); // gap between words

  // EXIT — the whole group fades and drifts up over the last half second.
  const outP = interpolate(
    frame,
    [durationInFrames - Math.round(fps * 0.5), durationInFrames],
    [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.in(Easing.cubic)},
  );
  const groupY = interpolate(outP, [0, 1], [0, -height * 0.05]);
  const groupOpacity = interpolate(outP, [0, 1], [1, 0]);

  return (
    <AbsoluteFill
      style={{
        backgroundColor,
        fontFamily,
        justifyContent: 'center',
        alignItems: 'center',
      }}
    >
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          gap: `0 ${Math.round(height * 0.02)}px`,
          transform: `translateY(${groupY}px)`,
          opacity: groupOpacity,
          maxWidth: '80%',
        }}
      >
        {words.map((word, i) => {
          // ENTER — each word springs up on its own delay.
          const inP = spring({
            frame: frame - i * stagger,
            fps,
            config: {damping: 200, mass: 0.6},
          });
          return (
            <span
              key={`${word}-${i}`}
              style={{
                display: 'inline-block',
                color: textColor,
                fontSize: Math.round(height * 0.11),
                fontWeight: 700,
                letterSpacing: -2,
                opacity: inP,
                transform: `translateY(${interpolate(inP, [0, 1], [50, 0])}px)`,
              }}
            >
              {word}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
