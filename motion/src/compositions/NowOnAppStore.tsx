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

// "Now on the App Store" — an announcement Reel. Driver-first (the driver app
// is the one to promote until drivers are active on a corridor). Dari + Pashto.
export const nowOnAppStoreSchema = z.object({
  headline: z.string(),
  appName: z.string(),
  cta: z.string(),
  tagline: z.string(),
});

// Apple logo (simple-icons path, 24×24).
const APPLE =
  'M16.365 1.43c0 1.14-.493 2.27-1.177 3.08-.744.9-1.99 1.57-2.987 1.57-.12 0-.23-.02-.3-.03-.01-.06-.04-.22-.04-.39 0-1.15.572-2.27 1.206-2.98.804-.94 2.142-1.64 3.248-1.68.03.13.04.28.04.43zm4.565 15.71c-.03.07-.463 1.58-1.518 3.12-.945 1.34-1.94 2.71-3.43 2.71-1.517 0-1.9-.88-3.63-.88-1.698 0-2.302.91-3.67.91-1.377 0-2.332-1.26-3.428-2.8-1.287-1.82-2.323-4.63-2.323-7.28 0-4.28 2.797-6.55 5.552-6.55 1.448 0 2.675.95 3.6.95.865 0 2.222-1.01 3.902-1.01.613 0 2.886.06 4.374 2.19-.13.09-2.383 1.37-2.383 4.19 0 3.26 2.854 4.42 2.955 4.45z';

export const NowOnAppStore: FC<z.infer<typeof nowOnAppStoreSchema>> = ({headline, appName, cta, tagline}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, height: H} = useVideoConfig();

  const brandIn = spring({frame, fps, config: {damping: 200}});
  const headIn = spring({frame: frame - Math.round(fps * 0.2), fps, config: {damping: 200}});
  const badgeIn = spring({frame: frame - Math.round(fps * 0.5), fps, config: {damping: 12, mass: 0.7}});
  const ctaIn = spring({frame: frame - Math.round(fps * 0.8), fps, config: {damping: 200}});
  const out = interpolate(frame, [durationInFrames - 16, durationInFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.in(Easing.cubic)});

  const bw = Math.round(H * 0.34);
  const bh = Math.round(H * 0.105);

  return (
    <AbsoluteFill style={{backgroundColor: VELRO.green700, fontFamily: vazirmatn, justifyContent: 'center', alignItems: 'center', overflow: 'hidden'}}>
      <div style={{position: 'absolute', inset: 0, background: `radial-gradient(46% 30% at 50% 40%, ${VELRO.green500}44, transparent 72%)`}} />

      <div style={{position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', opacity: out, gap: Math.round(H * 0.02)}}>
        {/* brand */}
        <div style={{display: 'flex', alignItems: 'center', gap: 20, direction: 'ltr', opacity: brandIn, transform: `translateY(${interpolate(brandIn, [0, 1], [-16, 0])}px)`}}>
          <svg width={Math.round(H * 0.06)} height={Math.round(H * 0.06)} viewBox="0 0 108 108">
            <rect width="108" height="108" rx="26" fill={VELRO.green900} />
            <path d="M54 78 L36 30 L45 30 L54 58 L63 30 L72 30 Z" fill="#fff" />
            <path d="M53 70 h2 v-6 h-2 Z" fill={VELRO.mint} />
            <path d="M53 60 h2 v-5 h-2 Z" fill={VELRO.mint} />
            <path d="M53 51 h2 v-4 h-2 Z" fill={VELRO.mint} />
          </svg>
          <span style={{color: '#fff', fontWeight: 800, fontSize: Math.round(H * 0.036), letterSpacing: 4, fontFamily: '"Helvetica Neue", Arial, sans-serif'}}>VELRO</span>
        </div>

        {/* headline */}
        <div dir="rtl" style={{color: '#fff', fontWeight: 900, fontSize: Math.round(H * 0.06), lineHeight: 1.15, marginTop: Math.round(H * 0.02), opacity: headIn, transform: `translateY(${interpolate(headIn, [0, 1], [26, 0])}px)`}}>
          {headline}
        </div>
        <div dir="rtl" style={{color: VELRO.mint, fontWeight: 700, fontSize: Math.round(H * 0.036)}}>{appName}</div>

        {/* App Store badge */}
        <div
          style={{
            marginTop: Math.round(H * 0.03),
            width: bw,
            height: bh,
            backgroundColor: '#000',
            borderRadius: bh * 0.2,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: bh * 0.22,
            opacity: badgeIn,
            transform: `scale(${interpolate(badgeIn, [0, 1], [0.8, 1])})`,
            boxShadow: '0 14px 40px rgba(0,0,0,0.3)',
          }}
        >
          <svg width={bh * 0.5} height={bh * 0.5} viewBox="0 0 24 24">
            <path d={APPLE} fill="#fff" />
          </svg>
          <div style={{display: 'flex', flexDirection: 'column', alignItems: 'flex-start', lineHeight: 1.05, fontFamily: '"Helvetica Neue", Arial, sans-serif'}}>
            <span style={{color: '#fff', fontSize: bh * 0.2, fontWeight: 400}}>Download on the</span>
            <span style={{color: '#fff', fontSize: bh * 0.36, fontWeight: 600}}>App Store</span>
          </div>
        </div>

        {/* cta */}
        <div dir="rtl" style={{color: VELRO.green50, fontWeight: 600, fontSize: Math.round(H * 0.03), marginTop: Math.round(H * 0.02), opacity: ctaIn}}>
          {cta}
        </div>
      </div>

      {/* corridor, bottom */}
      <div dir="rtl" style={{position: 'absolute', bottom: H * 0.07, width: '100%', textAlign: 'center', color: 'rgba(233,247,241,0.8)', fontSize: Math.round(H * 0.026), fontWeight: 500, opacity: brandIn * out}}>
        {tagline}
      </div>
    </AbsoluteFill>
  );
};
