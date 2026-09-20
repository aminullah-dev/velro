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

// Editable in the Studio's right-hand panel (schema + defaultProps).
export const titleCardSchema = z.object({
  title: z.string(),
  subtitle: z.string(),
  backgroundColor: zColor(),
  textColor: zColor(),
});

export const TitleCard: FC<z.infer<typeof titleCardSchema>> = ({
  title,
  subtitle,
  backgroundColor,
  textColor,
}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, height} = useVideoConfig();

  // ENTER — the title springs up, the subtitle follows a beat later.
  const titleIn = spring({frame, fps, config: {damping: 200}});
  const subIn = spring({frame: frame - Math.round(fps * 0.15), fps, config: {damping: 200}});

  // EXIT — fade + a touch of scale-down over the last half second, so the
  // card resolves cleanly instead of cutting.
  const out = interpolate(
    frame,
    [durationInFrames - Math.round(fps * 0.5), durationInFrames],
    [1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.in(Easing.cubic)},
  );
  const scale = interpolate(out, [0, 1], [0.98, 1]);

  return (
    <AbsoluteFill
      style={{
        backgroundColor,
        fontFamily,
        justifyContent: 'center',
        alignItems: 'center',
        transform: `scale(${scale})`,
      }}
    >
      <div style={{width: '80%', textAlign: 'center'}}>
        <div
          style={{
            opacity: titleIn * out,
            transform: `translateY(${interpolate(titleIn, [0, 1], [40, 0])}px)`,
            color: textColor,
            fontSize: Math.round(height * 0.095),
            fontWeight: 700,
            letterSpacing: -2,
            lineHeight: 1.05,
          }}
        >
          {title}
        </div>
        <div
          style={{
            opacity: subIn * out * 0.75,
            transform: `translateY(${interpolate(subIn, [0, 1], [24, 0])}px)`,
            color: textColor,
            fontSize: Math.round(height * 0.036),
            fontWeight: 400,
            marginTop: Math.round(height * 0.03),
          }}
        >
          {subtitle}
        </div>
      </div>
    </AbsoluteFill>
  );
};
