// A Google font, loaded the Remotion way (@remotion/google-fonts). Remotion
// waits for it before rendering a frame, so text never flashes in unstyled.
// Swap "Inter" for any family: `import {loadFont} from '@remotion/google-fonts/Roboto'`.
import {loadFont} from '@remotion/google-fonts/Inter';

// Only the weights and subset we use, so the Studio and renders stay light.
export const {fontFamily} = loadFont('normal', {
  weights: ['400', '600', '700'],
  subsets: ['latin'],
});
