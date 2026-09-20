import type {FC} from 'react';
import {z} from 'zod';
import {TransitionSeries, linearTiming} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {RequestRide} from './RequestRide';
import {AcceptRide} from './AcceptRide';
import {GhorbandDrive} from './GhorbandDrive';

// The whole story in one film: a passenger requests → a driver accepts → the
// car drives along the Ghorband river → "به‌زودی". It reuses the three scene
// components as segments, crossfaded together with @remotion/transitions.
// Two language presets (Dari + Pashto) are registered in Root.tsx.

// Segment lengths (frames) and the crossfade length. Exported so Root can set
// the composition's total duration to match.
export const REQ = 160;
export const ACC = 135;
export const DRV = 145;
export const TR = 18;
export const storyFilmDuration = REQ + ACC + DRV - 2 * TR;

export const storyFilmSchema = z.object({
  lang: z.enum(['fa', 'ps']),
});

const COPY = {
  fa: {
    request: {
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
    },
    accept: {
      driverLabel: 'ویلرو راننده',
      onlineLabel: 'آنلاین',
      requestLabel: 'درخواست سواری جدید',
      from: 'کابل',
      to: 'چاریکار',
      fare: '۲۵۰ افغانی',
      seats: '۲ چوکی',
      acceptLabel: 'قبول',
      acceptedLabel: 'پذیرفته شد',
    },
    drive: {headline: 'به‌زودی', corridor: 'کابل — چاریکار — غوربند'},
  },
  ps: {
    request: {
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
    },
    accept: {
      driverLabel: 'ویلرو ډرایور',
      onlineLabel: 'آنلاین',
      requestLabel: 'نوې سواري غوښتنه',
      from: 'کابل',
      to: 'چاریکار',
      fare: '۲۵۰ افغانۍ',
      seats: '۲ څوکۍ',
      acceptLabel: 'منل',
      acceptedLabel: 'ومنل شوه',
    },
    drive: {headline: 'ډېر ژر', corridor: 'کابل — چاریکار — غوربند'},
  },
} as const;

export const StoryFilm: FC<z.infer<typeof storyFilmSchema>> = ({lang}) => {
  const t = COPY[lang];
  return (
    <TransitionSeries>
      <TransitionSeries.Sequence durationInFrames={REQ}>
        <RequestRide {...t.request} />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition timing={linearTiming({durationInFrames: TR})} presentation={fade()} />
      <TransitionSeries.Sequence durationInFrames={ACC}>
        <AcceptRide {...t.accept} />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition timing={linearTiming({durationInFrames: TR})} presentation={fade()} />
      <TransitionSeries.Sequence durationInFrames={DRV}>
        <GhorbandDrive {...t.drive} />
      </TransitionSeries.Sequence>
    </TransitionSeries>
  );
};
