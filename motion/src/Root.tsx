import type {FC} from 'react';
import {Composition} from 'remotion';
import {FPS, HEIGHT, WIDTH, seconds} from './config';

import {TitleCard, titleCardSchema} from './compositions/TitleCard';
import {LowerThird, lowerThirdSchema} from './compositions/LowerThird';
import {KineticText, kineticTextSchema} from './compositions/KineticText';
import {TransparentOverlay, transparentOverlaySchema} from './compositions/TransparentOverlay';

// Every graphic is registered here. To add one: build a component in
// src/compositions/, then add a <Composition> below with a unique id, its
// schema, and defaultProps. It appears in the Studio sidebar immediately.
export const RemotionRoot: FC = () => {
  return (
    <>
      <Composition
        id="TitleCard"
        component={TitleCard}
        durationInFrames={seconds(5)}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        schema={titleCardSchema}
        defaultProps={{
          title: 'Motion Starter',
          subtitle: 'A clean base — take it your own way',
          backgroundColor: '#111214',
          textColor: '#FFFFFF',
        }}
      />

      <Composition
        id="LowerThird"
        component={LowerThird}
        durationInFrames={seconds(6)}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        schema={lowerThirdSchema}
        defaultProps={{
          name: 'First Last',
          role: 'Title / Role',
          accentColor: '#5B8DEF',
        }}
      />

      <Composition
        id="KineticText"
        component={KineticText}
        durationInFrames={seconds(4)}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        schema={kineticTextSchema}
        defaultProps={{
          words: ['Design', 'in', 'motion'],
          backgroundColor: '#111214',
          textColor: '#FFFFFF',
        }}
      />

      {/* Transparent by design — see TransparentOverlay.tsx and the README. */}
      <Composition
        id="TransparentOverlay"
        component={TransparentOverlay}
        durationInFrames={seconds(4)}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        schema={transparentOverlaySchema}
        defaultProps={{
          label: 'LIVE',
          accentColor: '#E5484D',
        }}
      />
    </>
  );
};
