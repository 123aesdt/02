# AMap published-route design QA

## Comparison inputs

- Source problem-state screenshot: `C:\Users\24090\AppData\Local\Temp\codex-clipboard-09f70c7b-bcfc-45cf-b159-6cc93f2953bd.png`
- Implemented success-state screenshot: `docs/verification/screenshots/amap-published-driver-route.png`
- Tested URL: `http://localhost:5173`
- Tested flow: employee login → road-block scenario `ROAD_BLOCKED_E04` → submit → asynchronous dispatch → automatic publication → employee route detail.

The source is a failure-state reference rather than a pixel-perfect target. QA therefore compares retained information architecture, visual hierarchy, and the requested transition from rejected virtual routing to an executable published real-road view.

## Mandatory comparison passes

- Fonts and typography: the implemented page preserves the compact operations-console hierarchy. The large page title, section headings, evidence labels, route facts, and map annotation remain readable without clipped or cramped primary content.
- Spacing and layout: the previous large empty failure area is replaced by a clear decision summary followed immediately by the published map. Evidence cards remain grouped below the executable route, so operational information leads and audit detail follows.
- Viewport resilience: the Playwright acceptance covers 1440×1000 and 390×844. Desktop columns do not obstruct the route card, and the mobile pass reports horizontal overflow less than or equal to one pixel.
- Colors and tokens: navy surfaces, cyan/green route emphasis, red blocked-road evidence, and green published/success status consistently communicate failure, avoidance, and safe execution.
- Image quality and asset fidelity: the primary map is the real AMap JS API dark-blue basemap with its road-matched polyline, labels, attribution, and controls. It is not replaced by CSS art or a fabricated SVG; the local route diagram appears only as a failure fallback.
- Copy and content: the employee sees that the route is published, the assigned recipient, estimated distance and time, client/server road-validation state, publication time, and an explicit driving instruction.
- Icons: Lucide route, navigation, time, location, validation, and success icons share a consistent stroke style and alignment.
- States and interactions: loading, ready, and fallback states are implemented. The accepted run reached `READY`, reported “高德道路已匹配”, exposed a focusable AMap surface, accepted wheel interaction, and retained `READY` afterward. Grab/grabbing cursors now expose drag affordance.
- AI shortcut artifacts: no decorative placeholder or fake avatar is introduced. The visual focus is the live provider map and persisted calculation evidence.

## Accessibility

- The route section has a labelled heading; the map has an accessible label; all submission controls retain associated labels.
- Status is expressed by text as well as color.
- The AMap canvas is keyboard focusable through its generated `tabindex`.
- The mobile layout stacks facts and keeps the route instruction visible without horizontal clipping.
- Existing application focus and reduced-motion conventions remain unchanged.

## Findings

No blocking visual or interaction defect remains in the tested published-route flow. The full task page is intentionally evidence-dense, but the executable map is placed above the detailed algorithm/audit evidence and is visually dominant.

final result: passed
