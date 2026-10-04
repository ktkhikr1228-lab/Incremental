# Design QA — ZERO ARCHIVE / THE LAST ASCENT

- Source visual truth: `C:\Users\katao\.codex\generated_images\01a03e7f-afe9-78b2-89e5-262921fd1718\exec-9b284dd4-1087-47c1-b2ff-89594efb1da4.png`
- Implementation screenshot: `C:\Users\katao\.codex\visualizations\2026\08\26\01a03e7f-afe9-78b2-89e5-262921fd1718\zero-archive-implementation-1536x1024.png`
- Viewport/state: 1536 × 1024 CSS px, DPR 1, Wave 47 combat state, paused after load
- Source pixels: 1536 × 1024
- Implementation pixels: 1536 × 1024
- Density normalization: none required; source and implementation were compared at identical pixel dimensions

## Full-view comparison evidence

The implementation preserves the selected concept's dominant hierarchy: cropped oversized Wave number at left, black ink enemy mass in the upper center-right, narrow permanent-resource ledger at right, full-width HP/time band, oversized DPS at lower left, and a single acid-green primary action at lower right. The warm paper/black ink/acid palette, asymmetrical whitespace, rule-based grouping, and absence of rounded dashboard cards match the source direction.

## Focused-region comparison evidence

A separate crop was not required because the 1536 × 1024 comparison keeps the typography, ledger, HP gauge, DPS breakdown, CTA, and build line legible at full size. The card-selection and death/workshop states were also captured and inspected independently in the browser.

## Required fidelity surfaces

- Fonts and typography: oversized condensed numeric hierarchy, Japanese interface text, tracking, and underlines match the print-manual direction. Display font has an explicit Windows condensed fallback.
- Spacing and layout rhythm: the Wave/enemy split, center gauge, lower three-part readout, peripheral ledger, and bottom build line follow the source proportions. No persistent control is clipped at 1536 × 1024.
- Colors and visual tokens: aged paper, carbon black, and acid chartreuse are centralized as CSS tokens; no blue/purple SaaS palette or gradients remain.
- Image quality and asset fidelity: the enemy and paper texture use a dedicated generated raster asset rather than CSS art or a placeholder. Crop and contrast match the source art direction.
- Copy and content: app-specific Wave, HP, DPS, enemy, permanent-resource, card, weapon, DP, and workshop labels remain connected to the simulator state.

## Findings

No actionable P0, P1, or P2 differences remain.

## Comparison history

1. Initial capture: P1 — the display-font custom property was unresolved, collapsing the Wave and DPS hierarchy to 16px. Fixed by adding valid font-variable fallbacks. Post-fix capture shows the intended 430px Wave and 142px DPS hierarchy.
2. Second capture: P1 — the full-width Wave number overlapped the enemy title. Fixed by horizontally condensing and repositioning the Wave mark. Post-fix capture keeps the cropped number within the left visual field and leaves the enemy title readable.
3. Final capture: no P0/P1/P2 findings. Primary combat, card selection, death, and workshop layouts remain usable.

## Primary interactions tested

- Start/new run
- Pause and resume
- Speed selection
- Immediate fight resolution
- Card reroll and card selection
- DP purchase
- Retry after death
- Browser console checked: no warnings or errors in final interaction pass

## Follow-up polish

- P3: the source uses more aggressive angular ends on the HP gauge and CTA; the implementation retains simpler rectangular hit targets for clarity and reliable interaction.
- P3: the 390 × 844 card-selection state uses an inner scroll region; it is usable but could receive a mobile-specific single-choice carousel in a later pass.
- P3: the functional strategy/seed/reset strip is additional product chrome not present in the concept image, but it is intentionally quiet and isolated from the combat hierarchy.

## Final result

final result: passed

---

## THE LAST ASCENT — visual mode 03

- Source visual truth: `C:\Users\katao\.codex\generated_images\01a03e7f-afe9-78b2-89e5-262921fd1718\exec-3921e8a9-6756-4909-aed7-564cf67433d4.png`
- Implementation screenshot: `C:\Users\katao\.codex\visualizations\2026\08\26\01a03e7f-afe9-78b2-89e5-262921fd1718\last-ascent-final-1536x1024.png`
- Viewport/state: 1536 × 1024 CSS px, DPR 1, Wave 47 combat state, paused after load
- Density normalization: none; source and implementation were compared together at identical pixel dimensions

### Fidelity evidence

- Hierarchy: large left-aligned Wave and DPS, red countdown, right-side enemy identity/HP, bottom relic fan, and oversized gold-edged CTA follow the selected reference.
- Palette and typography: green-black ground, aged ivory serif display type, restrained antique gold, and a single blood-red timing accent match the source direction without cyberpunk or SaaS styling.
- Assets: the observer/astrolabe scene and tarot-card fan are dedicated generated raster assets. No placeholder illustration, handcrafted SVG, or CSS-drawn character is used.
- State integration: Wave, DPS, time, HP, attack speed, crit, weapon, cards, relic, XP, and DP data are live values from the existing simulator; calculations are unchanged.
- Responsiveness: the 390 × 844 pass retains Wave, countdown, enemy HP, DPS, and resources without horizontal overflow. Lower controls remain reachable by vertical scrolling.

### Comparison history

1. Initial pass: P1 — automated click scrolling moved the clipped combat canvas by 145px, hiding the Wave label, countdown, and enemy name. Fixed by changing the visual canvas from scrollable `overflow: hidden` behavior to `overflow: clip`.
2. Final pass: no P0/P1/P2 visual differences remain. The top utility strip is additional functional chrome, intentionally reduced to thin engraved controls.

### Interactions tested

- Switch between `02 ARCHIVE` and `03 ASCENT`
- Pause state and immediate fight resolution
- Wave 47 → Wave 48 transition in ASCENT mode
- Strategy, seed, and run-reset controls remain connected
- Existing card, weapon, death, DP, workshop, and retry flows inherit the ASCENT visual tokens

## Final result

final result: passed
