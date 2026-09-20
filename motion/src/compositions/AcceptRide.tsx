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

// A driver accepting a ride, in the app's dark theme: a request slides up, a
// countdown ticks, a tap lands on the Accept button, and it confirms. All
// prop-driven and timed off the current frame, so it scrubs cleanly and comes
// in Dari + Pashto (two presets in Root.tsx).
export const acceptRideSchema = z.object({
  driverLabel: z.string(),
  onlineLabel: z.string(),
  requestLabel: z.string(),
  from: z.string(),
  to: z.string(),
  fare: z.string(),
  seats: z.string(),
  acceptLabel: z.string(),
  acceptedLabel: z.string(),
});

export const AcceptRide: FC<z.infer<typeof acceptRideSchema>> = ({
  driverLabel,
  onlineLabel,
  requestLabel,
  from,
  to,
  fare,
  seats,
  acceptLabel,
  acceptedLabel,
}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, width: W, height: H} = useVideoConfig();

  // ── beats ──
  const CARD = Math.round(fps * 0.4);
  const TAP = Math.round(fps * 2.7);
  const ACC = Math.round(fps * 2.95);

  const barIn = spring({frame, fps, config: {damping: 200}});
  const cardIn = spring({frame: frame - CARD, fps, config: {damping: 200, mass: 0.9}});
  const ringP = interpolate(frame, [CARD, TAP], [1, 0.5], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const tapT = interpolate(frame, [TAP - 14, TAP + 9], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const press = interpolate(frame, [TAP - 3, TAP + 1, TAP + 9], [1, 0.96, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const success = spring({frame: frame - ACC, fps, config: {damping: 200}});
  const checkP = spring({frame: frame - ACC - 3, fps, config: {damping: 200}});
  const out = interpolate(frame, [durationInFrames - 15, durationInFrames], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.in(Easing.cubic),
  });

  // ── card geometry ──
  const P = 48;
  const cardW = W - 120;
  const cardH = 760;
  const cardX = 60;
  const cardTop = H - 90 - cardH;
  const cardSlide = (1 - cardIn) * (cardH + 160);
  const BH = 118; // accept button height
  const buttonCX = cardX + cardW / 2;
  const buttonCY = cardTop + cardSlide + cardH - P - BH / 2;

  const ring = 92;
  const rr = ring / 2 - 6;
  const circ = 2 * Math.PI * rr;

  const dark = '#0E1220';
  const card = '#F6F8FB';
  const ink = '#16181D';
  const muted = '#6B7280';

  return (
    <AbsoluteFill style={{backgroundColor: dark, fontFamily: vazirmatn, overflow: 'hidden'}}>
      {/* the ding lands as the request arrives */}
      <Sequence from={CARD}>
        <Audio src={staticFile('audio/notify.mp3')} volume={0.7} />
      </Sequence>

      {/* soft glow + faint route in the map area */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: `radial-gradient(60% 30% at 50% 22%, ${VELRO.green500}33, transparent 70%)`,
        }}
      />
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height="100%" style={{position: 'absolute', inset: 0}}>
        <path
          d={`M ${W * 0.15} ${H * 0.34} C ${W * 0.35} ${H * 0.2}, ${W * 0.6} ${H * 0.42}, ${W * 0.86} ${H * 0.26}`}
          fill="none"
          stroke="rgba(143,217,188,0.25)"
          strokeWidth={6}
          strokeDasharray="2 22"
          strokeLinecap="round"
        />
      </svg>

      {/* top bar */}
      <div
        style={{
          position: 'absolute',
          top: 70,
          left: 60,
          right: 60,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          opacity: barIn * out,
        }}
      >
        <div style={{display: 'flex', alignItems: 'center', gap: 16, direction: 'rtl'}}>
          <svg width={54} height={54} viewBox="0 0 108 108">
            <rect x="0" y="0" width="108" height="108" rx="26" fill="#101828" />
            <path d="M54 78 L36 30 L45 30 L54 58 L63 30 L72 30 Z" fill={VELRO.mint} />
          </svg>
          <span style={{color: '#fff', fontSize: 34, fontWeight: 700}}>{driverLabel}</span>
        </div>
        <div style={{display: 'flex', alignItems: 'center', gap: 12, direction: 'rtl'}}>
          <span style={{width: 16, height: 16, borderRadius: '50%', backgroundColor: '#22C55E', display: 'inline-block'}} />
          <span style={{color: '#9AA3B2', fontSize: 28, fontWeight: 500}}>{onlineLabel}</span>
        </div>
      </div>

      {/* request card */}
      <div
        style={{
          position: 'absolute',
          left: cardX,
          top: cardTop,
          width: cardW,
          height: cardH,
          transform: `translateY(${cardSlide}px)`,
          opacity: out,
          backgroundColor: card,
          borderRadius: 40,
          boxShadow: '0 30px 80px rgba(0,0,0,0.45)',
          overflow: 'hidden',
        }}
      >
        {/* ── request content (fades out on accept) ── */}
        <div style={{position: 'absolute', inset: 0, padding: P, opacity: 1 - success}}>
          {/* header */}
          <div style={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', direction: 'rtl'}}>
            <div>
              <div style={{color: muted, fontSize: 28, fontWeight: 500}}>{requestLabel}</div>
            </div>
            {/* countdown ring */}
            <svg width={ring} height={ring} style={{transform: 'rotate(-90deg)'}}>
              <circle cx={ring / 2} cy={ring / 2} r={rr} fill="none" stroke="#E5E8EE" strokeWidth={8} />
              <circle
                cx={ring / 2}
                cy={ring / 2}
                r={rr}
                fill="none"
                stroke={VELRO.green500}
                strokeWidth={8}
                strokeLinecap="round"
                strokeDasharray={circ}
                strokeDashoffset={circ * (1 - ringP)}
              />
            </svg>
          </div>

          {/* route */}
          <div style={{marginTop: 40, direction: 'rtl'}}>
            <div style={{display: 'flex', alignItems: 'center', gap: 20}}>
              <span style={{width: 26, height: 26, borderRadius: '50%', backgroundColor: VELRO.green500, flexShrink: 0}} />
              <span style={{color: ink, fontSize: 44, fontWeight: 700}}>{from}</span>
            </div>
            <div style={{width: 4, height: 56, backgroundColor: '#D1D5DB', margin: '8px 11px', borderRadius: 2}} />
            <div style={{display: 'flex', alignItems: 'center', gap: 20}}>
              <span style={{width: 26, height: 26, borderRadius: '50%', backgroundColor: VELRO.amber, flexShrink: 0}} />
              <span style={{color: ink, fontSize: 44, fontWeight: 700}}>{to}</span>
            </div>
          </div>

          {/* stats */}
          <div style={{display: 'flex', gap: 20, marginTop: 44, direction: 'rtl'}}>
            {[fare, seats].map((v, i) => (
              <div key={i} style={{flex: 1, backgroundColor: '#EEF1F6', borderRadius: 20, padding: '24px 28px', textAlign: 'center'}}>
                <span style={{color: ink, fontSize: 38, fontWeight: 700}}>{v}</span>
              </div>
            ))}
          </div>

          {/* accept button */}
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
            <span style={{color: '#fff', fontSize: 46, fontWeight: 700}}>{acceptLabel}</span>
          </div>
        </div>

        {/* ── success content (fades in) ── */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            opacity: success,
          }}
        >
          <svg width={200} height={200} viewBox="0 0 200 200">
            <circle cx={100} cy={100} r={90} fill={VELRO.green500} transform={`scale(${interpolate(success, [0, 1], [0.7, 1])})`} style={{transformOrigin: '100px 100px'}} />
            <path
              d="M64 104 L90 130 L138 74"
              fill="none"
              stroke="#fff"
              strokeWidth={14}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray={120}
              strokeDashoffset={120 * (1 - checkP)}
            />
          </svg>
          <div style={{color: ink, fontSize: 52, fontWeight: 900, marginTop: 30}}>{acceptedLabel}</div>
        </div>
      </div>

      {/* tap ripple over the accept button */}
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
