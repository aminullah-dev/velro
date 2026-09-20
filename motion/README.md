# Motion — a Remotion starter

Programmatic motion graphics in React. This is a **clean, neutral base** on
purpose — four minimal example graphics, a single place for canvas settings,
and the render commands you need. Design your own look on top of it; nothing
here is meant to be a finished style.

Built with [Remotion](https://remotion.dev) 4 + TypeScript. Render to MP4,
transparent ProRes, or a PNG sequence, then drop the result into any editor.

> **Licensing heads-up.** Remotion is free for individuals and small teams, but
> **companies need a paid license** (the free tier covers organisations up to a
> small headcount — check the current terms at remotion.dev/license). Since this
> lives in a company repo, confirm you're within the free tier or hold a license
> before shipping commercial work with it.

---

## Preview (live editor)

```bash
npm run studio
```

Opens **Remotion Studio** at <http://localhost:3000>: pick a composition on the
left, scrub the timeline, and edit its props live on the right (those fields
come from each composition's zod schema).

First run downloads a small headless-browser build that Remotion uses for
rendering — that's a one-time thing.

---

## Project structure

```
motion/
├─ src/
│  ├─ index.ts            # entry point — registers the root (don't edit)
│  ├─ Root.tsx            # ← registers every composition (id, size, fps, schema, defaults)
│  ├─ config.ts           # ← the shared canvas: WIDTH, HEIGHT, FPS
│  ├─ fonts.ts            # Google font (Inter) loaded the Remotion way
│  └─ compositions/       # one file per graphic
│     ├─ TitleCard.tsx
│     ├─ LowerThird.tsx
│     ├─ KineticText.tsx
│     └─ TransparentOverlay.tsx
├─ public/                # static assets you reference with staticFile()
│  ├─ fonts/  images/  audio/
├─ out/                   # renders land here (git-ignored)
└─ remotion.config.ts     # CLI/render defaults
```

## The canvas (change once, everywhere)

All size/fps settings live in [`src/config.ts`](src/config.ts):

```ts
export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;
```

Switch to **4K** → `WIDTH = 3840, HEIGHT = 2160`. Switch to **60fps** → `FPS = 60`.
Every composition reads these, and text is sized relative to the canvas height,
so proportions hold when you change resolution.

## The four starters

| id | what it is | notable prop(s) |
|----|-----------|-----------------|
| `TitleCard` | centered title + subtitle | `title`, `subtitle`, colors |
| `LowerThird` | name/role plate, slides in from the left | `name`, `role`, `accentColor` |
| `KineticText` | words snap in one by one | `words` (array) |
| `TransparentOverlay` | a badge on a **transparent** background | `label`, `accentColor` |
| `VelroStory` | branded, **vertical 1080×1920** example (road-V mark, RTL Vazirmatn) | `headline`, `corridor` |
| `GhorbandDrive` | animated scene: a car driving beside the Ghorband river, vertical | `headline`, `corridor` |
| `GhorbandDrive-Pashto` | same scene, Pashto preset (`ډېر ژر`) | `headline`, `corridor` |

`GhorbandDrive` is a full animated scene built from an SVG projection driven by
`useCurrentFrame` — the car, road dashes, river and bend all move as a function
of the frame, so it scrubs on the timeline. The two language versions are the
same component with different props (swap `headline` to translate it).

`VelroStory` also shows two extra patterns: a composition with **its own size**
(portrait, overriding the shared 16:9 canvas — see its `width`/`height` in
`Root.tsx`), and brand tokens + a Persian Google font pulled from
[`src/brand.ts`](src/brand.ts). Copy that file's approach for any branded graphic.

Each one has a **full enter *and* exit** (nothing pops on or cuts off), driven
by `useCurrentFrame`, `interpolate`, `spring` and `Easing`. Each also has a zod
schema + `defaultProps`, so you can edit every field live in the Studio.

---

## Add a new graphic

1. **Make the component** in `src/compositions/MyGraphic.tsx`. Export a zod
   schema and a component typed from it:

   ```tsx
   import type {FC} from 'react';
   import {z} from 'zod';
   import {AbsoluteFill, useCurrentFrame, useVideoConfig, spring, interpolate, Easing} from 'remotion';

   export const myGraphicSchema = z.object({ text: z.string() });

   export const MyGraphic: FC<z.infer<typeof myGraphicSchema>> = ({text}) => {
     const frame = useCurrentFrame();
     const {fps, durationInFrames} = useVideoConfig();
     const enter = spring({frame, fps, config: {damping: 200}});
     const exit = interpolate(frame, [durationInFrames - fps * 0.5, durationInFrames], [1, 0], {
       extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.in(Easing.cubic),
     });
     return <AbsoluteFill style={{opacity: enter * exit}}>{text}</AbsoluteFill>;
   };
   ```

2. **Register it** in [`src/Root.tsx`](src/Root.tsx) — a unique `id`, the shared
   size/fps, its schema and defaults:

   ```tsx
   <Composition
     id="MyGraphic"
     component={MyGraphic}
     durationInFrames={seconds(4)}
     fps={FPS}
     width={WIDTH}
     height={HEIGHT}
     schema={myGraphicSchema}
     defaultProps={{ text: 'Hello' }}
   />
   ```

   It shows up in the Studio sidebar immediately. `seconds(n)` (from `config.ts`)
   turns seconds into frames at the current FPS.

---

## Render

Renders go to `out/`. Replace `<id>` with a composition id (e.g. `TitleCard`).

**Opaque MP4** (H.264 — the everyday format; note: MP4/H.264 has **no**
transparency):

```bash
npx remotion render <id> out/<id>.mp4 --codec=h264 --crf=18
```

**Transparent** (ProRes 4444 `.mov` with a real alpha channel — for overlays you
composite over other footage):

```bash
npx remotion render <id> out/<id>.mov --codec=prores \
  --prores-profile=4444 --pixel-format=yuva444p10le --image-format=png
```

**PNG sequence** (every frame as a file, alpha preserved):

```bash
npx remotion render <id> out/<id>/frame-%04d.png --image-format=png
```

### About transparency
An overlay only exports with alpha if its composition **paints no background** —
see `TransparentOverlay.tsx`, whose `<AbsoluteFill>` has no `backgroundColor`.
The `.mov`/PNG commands above keep that alpha; the MP4 command flattens it. In
the Studio, a transparent composition shows a checkerboard behind it.

Handy extras: `--frames=0-59` renders a range; `npx remotion still <id> out/x.png
--frame=30` grabs a single frame.

---

## Fonts

[`src/fonts.ts`](src/fonts.ts) loads **Inter** via `@remotion/google-fonts`;
Remotion waits for it before drawing a frame, so text never flashes unstyled:

```ts
import {loadFont} from '@remotion/google-fonts/Inter';
export const {fontFamily} = loadFont('normal', {weights: ['400', '600', '700'], subsets: ['latin']});
```

Swap the family by changing the import (e.g. `.../Roboto`). For a local/custom
font instead, drop it in `public/fonts/` and load it with `@remotion/fonts`.

## Sound effects

A ready example is already wired up: `GhorbandDrive` plays a synthesized driving
bed from `public/audio/drive-ambience.mp3` via `<Audio>`. To add your own, put
the file in `public/audio/`, then play it with `<Audio>` — inside a `<Sequence>`
if it should start on a chosen frame:

```tsx
import {AbsoluteFill, Audio, Sequence, staticFile} from 'remotion';

// inside a composition — the whoosh starts at frame 30:
<Sequence from={30}>
  <Audio src={staticFile('audio/whoosh.mp3')} />
</Sequence>
```

`staticFile()` resolves paths inside `public/`. Trim `volume`, or a slice with
`startFrom` / `endAt`, as needed.

---

## Tips

- **Title-safe area.** Keep important text within the centre ~90% — leave a
  margin so nothing clips on TVs or gets covered by a platform's UI.
- **Always animate in *and* out.** Give every element a clear enter and a clear
  exit (the starters fade/slide out over the last ~0.5s) so nothing pops on
  screen or cuts mid-motion.
- **Trim leading silence on sound effects.** A file with 200ms of silence at the
  front will feel late. Trim it, or offset the `<Sequence from={...}>` so the
  hit lands on the exact frame.
- **Time things in frames, not guesses.** `spring({fps, ...})` and
  `interpolate(frame, ...)` stay in sync with FPS; use `seconds()` for durations.

## Scripts

| command | does |
|---------|------|
| `npm run studio` | live preview editor |
| `npm run render` | `remotion render …` (see above) |
| `npm run still` | render a single frame |
| `npm run compositions` | list every registered composition |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run upgrade` | bump Remotion to the latest version |
