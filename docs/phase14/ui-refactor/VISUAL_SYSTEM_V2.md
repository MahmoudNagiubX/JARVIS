# JARVIS Phase 14 visual system V2

## Direction

The interface is a local operating console: quiet near-black plum, controlled
crimson energy, navy/steel depth, and the existing JARVIS electric cyan as the
interaction and intelligence accent. The supplied owner wallpaper appears only
on Home as a blended hero anchor; other routes inherit its palette and depth,
not the literal image.

## Tokens

```css
--bg-0: #0C060E;
--bg-1: #1E0C1D;
--bg-2: #101421;
--surface-0: rgba(18, 13, 23, .92);
--surface-1: rgba(25, 18, 30, .84);
--surface-cool: rgba(21, 37, 78, .30);
--energy-primary: #55D9FF;
--energy-soft: #96D8EE;
--energy-red: #C40B2E;
--energy-red-hot: #EA2F42;
--energy-ember: #DA4F2E;
--text-primary: #E6F4FB;
--text-secondary: #A8B6C4;
--text-muted: #718294;
--line-neutral: rgba(150, 216, 238, .13);
--line-active: rgba(85, 217, 255, .48);
--line-red-energy: rgba(196, 11, 46, .38);
```

The old `--jarvis-*` names remain as compatibility aliases so existing
behavioral components do not fork the token source.

## Composition rules

- Home uses the wallpaper hero, a significant layered orb/reactor, KPI trace,
  owner queue, live capability spine, mission preview, and bounded activity.
- Chat uses a conversation rail, rich messages, active-run inbox, and the
  existing composer/run endpoints.
- Missions use pipeline stages, plan rows, and reported progress.
- Research uses evidence-first citation rows; Engineering uses safe code and
  stats surfaces; Skills uses a capability table; Devices use tactical radar
  and compass primitives.
- HUD frame accents are selective. Every panel is not wrapped in identical
  cyan chrome.
- Recoverable session/offline notices are neutral/amber and human-readable;
  strong crimson is reserved for destructive or genuinely critical state.
- Green is not an identity color. Healthy state uses cyan/ice/neutral; green
  remains available only as a small semantic success signal.

## Motion and accessibility

Motion is limited to ring breathing, scan traces, and state transitions. The
`prefers-reduced-motion: reduce` rule disables nonessential ring animation and
transitions. All state labels have text equivalents, all controls use semantic
buttons/links, and dense tables remain horizontally scrollable on narrow
layouts.

## Local asset

`ui/src/assets/hero/ironman-owner-wallpaper.jpg` is the exact owner-supplied
3840×2163 image. It is blended with plum overlays and a vignette on Home only;
no external image, font CDN, icon CDN, remote CSS, or remote JavaScript is used.
