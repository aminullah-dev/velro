// ────────────────────────────────────────────────────────────────────────
// The shared canvas. Change these numbers and every composition follows.
// ────────────────────────────────────────────────────────────────────────

/** Frames per second for every composition. Switch to 60 for silky motion. */
export const FPS = 30;

/** Canvas width in pixels. */
export const WIDTH = 1920;

/** Canvas height in pixels. */
export const HEIGHT = 1080;

// Common presets — just copy the numbers up into WIDTH / HEIGHT / FPS:
//   1080p (default) : 1920 × 1080
//   4K UHD          : 3840 × 2160
//   Square (social) : 1080 × 1080
//   Vertical (reels): 1080 × 1920
//   Smooth motion   : FPS = 60

/** Convenience: pass straight into a <Composition width/height>. */
export const DIMENSIONS = {width: WIDTH, height: HEIGHT} as const;

/** Seconds → whole frames, at the current FPS. Use for durationInFrames. */
export const seconds = (s: number): number => Math.round(s * FPS);
