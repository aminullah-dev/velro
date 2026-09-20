// VELRO brand tokens + the Persian font, in one place. Used by the
// VelroStory composition; reuse them for any other branded graphic.
import {loadFont} from '@remotion/google-fonts/Vazirmatn';

// Vazirmatn covers Persian/Dari (and Pashto letters). Arabic subset only.
export const {fontFamily: vazirmatn} = loadFont('normal', {
  weights: ['500', '700', '900'],
  subsets: ['arabic'],
});

export const VELRO = {
  green900: '#06301F',
  green700: '#0E6042', // the brand green (app icon / avatar background)
  green500: '#189669',
  green50: '#EAF7F1',
  mint: '#8FD9BC',
  amber: '#F59E0B',
  white: '#FFFFFF',
} as const;
