import type {FC} from 'react';
import {Composition} from 'remotion';
import {FPS, HEIGHT, WIDTH, seconds} from './config';

import {TitleCard, titleCardSchema} from './compositions/TitleCard';
import {LowerThird, lowerThirdSchema} from './compositions/LowerThird';
import {KineticText, kineticTextSchema} from './compositions/KineticText';
import {TransparentOverlay, transparentOverlaySchema} from './compositions/TransparentOverlay';
import {VelroStory, velroStorySchema} from './compositions/VelroStory';
import {GhorbandDrive, ghorbandDriveSchema} from './compositions/GhorbandDrive';
import {AcceptRide, acceptRideSchema} from './compositions/AcceptRide';
import {RequestRide, requestRideSchema} from './compositions/RequestRide';
import {StoryFilm, storyFilmSchema, storyFilmDuration} from './compositions/StoryFilm';

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

      {/*
        A VELRO-branded example — and a VERTICAL one. A composition can set its
        own size; here 1080×1920 for stories/reels, independent of the shared
        WIDTH/HEIGHT. Copy this pattern for any portrait graphic.
      */}
      <Composition
        id="VelroStory"
        component={VelroStory}
        durationInFrames={seconds(5)}
        fps={FPS}
        width={1080}
        height={1920}
        schema={velroStorySchema}
        defaultProps={{
          headline: 'به‌زودی',
          corridor: 'کابل — چاریکار — غوربند',
        }}
      />

      {/*
        The Ghorband riverside drive, animated on the timeline — a moving car,
        river, road and mountains, all a pure function of the frame. Same
        component, two language presets: Dari and Pashto (just different props).
      */}
      <Composition
        id="GhorbandDrive"
        component={GhorbandDrive}
        durationInFrames={seconds(6)}
        fps={FPS}
        width={1080}
        height={1920}
        schema={ghorbandDriveSchema}
        defaultProps={{
          headline: 'به‌زودی',
          corridor: 'کابل — چاریکار — غوربند',
        }}
      />
      <Composition
        id="GhorbandDrive-Pashto"
        component={GhorbandDrive}
        durationInFrames={seconds(6)}
        fps={FPS}
        width={1080}
        height={1920}
        schema={ghorbandDriveSchema}
        defaultProps={{
          headline: 'ډېر ژر',
          corridor: 'کابل — چاریکار — غوربند',
        }}
      />

      {/*
        Driver accepting a ride — app-style UI animation. Same component, two
        language presets (Dari + Pashto).
      */}
      <Composition
        id="AcceptRide"
        component={AcceptRide}
        durationInFrames={seconds(6)}
        fps={FPS}
        width={1080}
        height={1920}
        schema={acceptRideSchema}
        defaultProps={{
          driverLabel: 'ویلرو راننده',
          onlineLabel: 'آنلاین',
          requestLabel: 'درخواست سواری جدید',
          from: 'کابل',
          to: 'چاریکار',
          fare: '۲۵۰ افغانی',
          seats: '۲ چوکی',
          acceptLabel: 'قبول',
          acceptedLabel: 'پذیرفته شد',
        }}
      />
      <Composition
        id="AcceptRide-Pashto"
        component={AcceptRide}
        durationInFrames={seconds(6)}
        fps={FPS}
        width={1080}
        height={1920}
        schema={acceptRideSchema}
        defaultProps={{
          driverLabel: 'ویلرو ډرایور',
          onlineLabel: 'آنلاین',
          requestLabel: 'نوې سواري غوښتنه',
          from: 'کابل',
          to: 'چاریکار',
          fare: '۲۵۰ افغانۍ',
          seats: '۲ څوکۍ',
          acceptLabel: 'منل',
          acceptedLabel: 'ومنل شوه',
        }}
      />

      {/*
        Passenger requesting a ride — the other side of AcceptRide, in the
        passenger app's light theme. Request → searching → driver found.
        Dari + Pashto presets.
      */}
      <Composition
        id="RequestRide"
        component={RequestRide}
        durationInFrames={seconds(6)}
        fps={FPS}
        width={1080}
        height={1920}
        schema={requestRideSchema}
        defaultProps={{
          appLabel: 'ویلرو',
          tripLabel: 'سفر شما',
          from: 'کابل',
          to: 'چاریکار',
          fare: '۲۵۰ افغانی',
          seats: '۲ چوکی',
          requestLabel: 'درخواست موتر',
          searchingLabel: 'در حال یافتن راننده',
          foundLabel: 'راننده پیدا شد',
          driverName: 'احمد',
          eta: '۳ دقیقه تا رسیدن',
        }}
      />
      <Composition
        id="RequestRide-Pashto"
        component={RequestRide}
        durationInFrames={seconds(6)}
        fps={FPS}
        width={1080}
        height={1920}
        schema={requestRideSchema}
        defaultProps={{
          appLabel: 'ویلرو',
          tripLabel: 'ستاسو سفر',
          from: 'کابل',
          to: 'چاریکار',
          fare: '۲۵۰ افغانۍ',
          seats: '۲ څوکۍ',
          requestLabel: 'موټر وغواړئ',
          searchingLabel: 'د ډرایور په لټه کې',
          foundLabel: 'ډرایور پیدا شو',
          driverName: 'احمد',
          eta: '۳ دقیقې پاتې',
        }}
      />

      {/*
        The whole story in one film: request → accept → drive → به‌زودی.
        Reuses the three scenes as crossfaded segments. Dari + Pashto.
      */}
      <Composition
        id="StoryFilm"
        component={StoryFilm}
        durationInFrames={storyFilmDuration}
        fps={FPS}
        width={1080}
        height={1920}
        schema={storyFilmSchema}
        defaultProps={{lang: 'fa' as const}}
      />
      <Composition
        id="StoryFilm-Pashto"
        component={StoryFilm}
        durationInFrames={storyFilmDuration}
        fps={FPS}
        width={1080}
        height={1920}
        schema={storyFilmSchema}
        defaultProps={{lang: 'ps' as const}}
      />
    </>
  );
};
