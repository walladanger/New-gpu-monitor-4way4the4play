# Design review · documentation demo

Reviewed November 12, 2026. Evidence is the six application captures in [the feature tour](FEATURE-TOUR.md), generated in this documentation run from the actual UI with synthetic readings. This is a review of those states, not a live-hardware soak test or accessibility certification.

## What is strong

| Step | State | Health and evidence |
| --- | --- | --- |
| 1 | Four-panel overview | Good measurement hierarchy: title, unit, named values, then graph. All four metrics are visible together. |
| 2 | Focus and quick menu | Good local scope: selected trace brightens and the menu says “this graph only.” Hex input and preview tiles make appearance choices concrete. |
| 3 | Detached window and pins | Strong inspection model: labels A/B connect the graph to a four-metric comparison. The detail panel can obscure data but has a move affordance. |
| 4 | Zoom | Useful fidelity controls and conditional bars. A dedicated “back to live” action would make historical panning easier to discover. |
| 5 | Narrow, upper panels | Good full-width stacking and wrapped toolbar. Some panels are below the fold, making the page scroll essential. |
| 6 | Narrow, lower panels | Temperature and power remain reachable. The fixed header consumes a noticeable share of short windows. |

## Improvements, in order

1. **Saved preferences:** prevent repeated setup of colors, history, and window geometry. See P1 in the roadmap.
2. **Discoverable window controls:** add useful accessible names, keyboard equivalents, and compact tooltips for icon-only actions. Do not add persistent clutter.
3. **Time context:** make inspecting older data distinct from following live data; add a pan-to-live action. Preserve the latest-value headers, but label their time context clearly.
4. **Pin navigation:** support keyboard selection/removal and a clear-all action. Keep each pin's time/card identity explicit.
5. **Short-window layout:** test an optional compact header after preferences exist. Preserve the four panels and readable measurement spacing.

## Accessibility risks that need testing

- Color alone should not carry GPU identity or selection. Names and dashed/hatched styles help, but screen-reader naming and keyboard focus still need verification.
- Small corner icons can be hard to discover. Their visual glyphs and clickable areas are different sizes; test target acquisition at several display scales.
- Minimum text sizes, contrast in dimmed traces, and focus indication need measurement and keyboard/screen-reader testing on Windows.
- Pointer-only pinning and wheel zoom need equivalent keyboard paths before claiming full keyboard usability.
- The background respects Windows' animation setting; other motion and the visibility of current focus should be tested separately.

## Evidence limits

These captures demonstrate rendering and state layout. They do not establish driver accuracy, long-term stability, true sensor simultaneity, assistive-technology compatibility, or behavior across every monitor/DPI configuration. A static screenshot cannot verify a blur's animation or continuous resizing. Browser-rendered GitHub layout also needs a visual check after publication.
