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

// The passenger side: a rider sets a trip, taps Request, we search, a driver is
// found. Light theme (the passenger app), to contrast the dark driver app in
// AcceptRide. Prop-driven; comes in Dari + Pashto presets (see Root.tsx).
export const requestRideSchema = z.object({
  appLabel: z.string(),
  tripLabel: z.string(),
  from: z.string(),
  to: z.string(),
  fare: z.string(),
  seats: z.string(),
  requestLabel: z.string(),
  searchingLabel: z.string(),
  foundLabel: z.string(),
  driverName: z.string(),
  eta: z.string(),
});

export const RequestRide: FC<z.infer<typeof requestRideSchema>> = ({
  appLabel,
  tripLabel,
  from,
  to,
  fare,
  seats,
  requestLabel,
  searchingLabel,
  foundLabel,
  driverName,
  eta,
}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, width: W, height: H} = useVideoConfig();

  const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

  // ── beats ──
  const CARD = Math.round(fps * 0.4);
  const TAP = Math.round(fps * 2.4);
  const SEARCH = Math.round(fps * 2.7);
  const FOUND = Math.round(fps * 4.3);

  const barIn = spring({frame, fps, config: {damping: 200}});
  const cardIn = spring({frame: frame - CARD, fps, config: {damping: 200, mass: 0.9}});
  const press = interpolate(frame, [TAP - 3, TAP + 1, TAP + 9], [1, 0.96, 1], clamp);
  const tapT = interpolate(frame, [TAP - 14, TAP + 9], [0, 1], clamp);

  const reqOpacity = interpolate(frame, [SEARCH - 6, SEARCH + 6], [1, 0], clamp);
  const searchOpacity = interpolate(frame, [SEARCH - 6, SEARCH + 6, FOUND - 6, FOUND + 6], [0, 1, 1, 0], clamp);
  const foundOpacity = interpolate(frame, [FOUND - 6, FOUND + 6], [0, 1], clamp);
  const foundIn = spring({frame: frame - FOUND, fps, config: {damping: 200}});
  const out = interpolate(frame, [durationInFrames - 15, durationInFrames], [1, 0], {
    ...clamp,
    easing: Easing.in(Easing.cubic),
  });

  // ── geometry ──
  const P = 48;
  const cardW = W - 120;
  const cardH = 760;
  const cardX = 60;
  const cardTop = H - 90 - cardH;
  const cardSlide = (1 - cardIn) * (cardH + 160);
  const BH = 118;
  const buttonCX = cardX + cardW / 2;
  const buttonCY = cardTop + cardSlide + cardH - P - BH / 2;

  const ink = '#16181D';
  const muted = '#6B7280';

  // radar rings (searching)
  const rings = [0, 1, 2].map((i) => {
    const t = ((frame / fps) * 0.9 + i / 3) % 1;
    return {scale: interpolate(t, [0, 1], [0.3, 1.5]), opacity: interpolate(t, [0, 1], [0.45, 0])};
  });
  // animated "…" dots
  const dotOn = (i: number) => (Math.floor((frame / fps) * 3) % 3 >= i ? 1 : 0.25);

  return (
    <AbsoluteFill style={{backgroundColor: '#EDF3EF', fontFamily: vazirmatn, overflow: 'hidden'}}>
      <Sequence from={TAP}>
        <Audio src={staticFile('audio/swoosh.mp3')} />
      </Sequence>
      <Sequence from={FOUND}>
        <Audio src={staticFile('audio/notify.mp3')} volume={0.7} />
      </Sequence>

      {/* faint map route */}
      <div style={{position: 'absolute', inset: 0, background: `radial-gradient(55% 28% at 50% 20%, ${VELRO.green500}22, transparent 70%)`}} />
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height="100%" style={{position: 'absolute', inset: 0}}>
        <path
          d={`M ${W * 0.14} ${H * 0.3} C ${W * 0.36} ${H * 0.18}, ${W * 0.62} ${H * 0.4}, ${W * 0.88} ${H * 0.24}`}
          fill="none"
          stroke="rgba(14,96,66,0.18)"
          strokeWidth={6}
          strokeDasharray="2 22"
          strokeLinecap="round"
        />
      </svg>

      {/* top bar */}
      <div style={{position: 'absolute', top: 70, left: 60, right: 60, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 16, direction: 'rtl', opacity: barIn * out}}>
        <svg width={50} height={50} viewBox="0 0 108 108">
          <path d="M54 78 L36 30 L45 30 L54 58 L63 30 L72 30 Z" fill={VELRO.green700} />
          <path d="M53 70 h2 v-6 h-2 Z" fill={VELRO.green500} />
          <path d="M53 60 h2 v-5 h-2 Z" fill={VELRO.green500} />
          <path d="M53 51 h2 v-4 h-2 Z" fill={VELRO.green500} />
        </svg>
        <span style={{color: VELRO.green700, fontSize: 40, fontWeight: 800, letterSpacing: 1}}>{appLabel}</span>
      </div>

      {/* card */}
      <div
        style={{
          position: 'absolute',
          left: cardX,
          top: cardTop,
          width: cardW,
          height: cardH,
          transform: `translateY(${cardSlide}px)`,
          opacity: out,
          backgroundColor: '#FFFFFF',
          borderRadius: 40,
          boxShadow: '0 30px 80px rgba(20,40,30,0.18)',
          overflow: 'hidden',
        }}
      >
        {/* ── request state ── */}
        <div style={{position: 'absolute', inset: 0, padding: P, opacity: reqOpacity}}>
          <div style={{color: muted, fontSize: 30, fontWeight: 600, textAlign: 'right', direction: 'rtl'}}>{tripLabel}</div>
          <div style={{marginTop: 34, direction: 'rtl'}}>
            <div style={{display: 'flex', alignItems: 'center', gap: 20}}>
              <span style={{width: 26, height: 26, borderRadius: '50%', backgroundColor: VELRO.green500, flexShrink: 0}} />
              <span style={{color: ink, fontSize: 44, fontWeight: 700}}>{from}</span>
            </div>
            <div style={{width: 4, height: 52, backgroundColor: '#D1D5DB', margin: '8px 11px', borderRadius: 2}} />
            <div style={{display: 'flex', alignItems: 'center', gap: 20}}>
              <span style={{width: 26, height: 26, borderRadius: '50%', backgroundColor: VELRO.amber, flexShrink: 0}} />
              <span style={{color: ink, fontSize: 44, fontWeight: 700}}>{to}</span>
            </div>
          </div>
          <div style={{display: 'flex', gap: 20, marginTop: 40, direction: 'rtl'}}>
            {[fare, seats].map((v, i) => (
              <div key={i} style={{flex: 1, backgroundColor: '#F1F4F8', borderRadius: 20, padding: '24px 28px', textAlign: 'center'}}>
                <span style={{color: ink, fontSize: 38, fontWeight: 700}}>{v}</span>
              </div>
            ))}
          </div>
          <div
            style={{
              position: 'absolute',
              left: P,
              right: P,
              bottom: P,
              height: BH,
              backgroundColor: VELRO.green700,
              borderRadius: 24,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transform: `scale(${press})`,
            }}
          >
            <span style={{color: '#fff', fontSize: 46, fontWeight: 700}}>{requestLabel}</span>
          </div>
        </div>

        {/* ── searching state ── */}
        <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', opacity: searchOpacity}}>
          <div style={{position: 'relative', width: 260, height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
            {rings.map((r, i) => (
              <span key={i} style={{position: 'absolute', width: 200, height: 200, borderRadius: '50%', border: `4px solid ${VELRO.green500}`, transform: `scale(${r.scale})`, opacity: r.opacity}} />
            ))}
            <span style={{width: 96, height: 96, borderRadius: '50%', backgroundColor: '#101828', display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
              <svg width={58} height={58} viewBox="0 0 108 108">
                <path d="M54 78 L36 30 L45 30 L54 58 L63 30 L72 30 Z" fill={VELRO.mint} />
              </svg>
            </span>
          </div>
          <div style={{display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 40, direction: 'rtl'}}>
            <span style={{color: ink, fontSize: 40, fontWeight: 700}}>{searchingLabel}</span>
            {[0, 1, 2].map((i) => (
              <span key={i} style={{color: ink, fontSize: 40, fontWeight: 700, opacity: dotOn(i)}}>
                .
              </span>
            ))}
          </div>
        </div>

        {/* ── found state ── */}
        <div style={{position: 'absolute', inset: 0, padding: P, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', opacity: foundOpacity}}>
          <div style={{color: VELRO.green500, fontSize: 34, fontWeight: 700, marginBottom: 34}}>{foundLabel}</div>
          <div
            style={{
              width: '100%',
              backgroundColor: '#F1F4F8',
              borderRadius: 28,
              padding: 34,
              display: 'flex',
              alignItems: 'center',
              gap: 26,
              direction: 'rtl',
              transform: `translateY(${interpolate(foundIn, [0, 1], [26, 0])}px)`,
            }}
          >
            <span style={{width: 96, height: 96, borderRadius: '50%', backgroundColor: '#101828', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0}}>
              <svg width={54} height={54} viewBox="0 0 108 108">
                <path d="M54 78 L36 30 L45 30 L54 58 L63 30 L72 30 Z" fill={VELRO.mint} />
              </svg>
            </span>
            <div style={{textAlign: 'right'}}>
              <div style={{color: ink, fontSize: 44, fontWeight: 700}}>{driverName}</div>
              <div style={{color: muted, fontSize: 30, fontWeight: 500, marginTop: 6}}>{eta}</div>
            </div>
          </div>
        </div>
      </div>

      {/* tap ripple over the request button */}
      {tapT > 0 && tapT < 1 && (
        <div
          style={{
            position: 'absolute',
            left: buttonCX,
            top: buttonCY,
            width: 160,
            height: 160,
            marginLeft: -80,
            marginTop: -80,
            borderRadius: '50%',
            border: '6px solid rgba(255,255,255,0.9)',
            transform: `scale(${interpolate(tapT, [0, 1], [0.3, 1.6])})`,
            opacity: interpolate(tapT, [0, 1], [0.6, 0]),
          }}
        />
      )}
    </AbsoluteFill>
  );
};
