import {Config} from '@remotion/cli/config';

// CLI / render defaults. The *visual* settings (size, fps) live in
// src/config.ts and in each composition — keep this file for render behaviour.
//
// Note on transparency: the default image format below is 'jpeg', which is
// fine for opaque MP4s and stills. Transparent renders (the .mov / PNG-sequence
// commands in the README) pass `--image-format=png` on the command line, which
// overrides this and preserves the alpha channel. You could also flip the
// default to 'png' here if most of your work is transparent.
Config.setVideoImageFormat('jpeg');

// Overwrite the output file if it already exists, so re-renders are painless.
Config.setOverwriteOutput(true);
