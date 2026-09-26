---
name: machine-design
description: Machine design system, a dark blueprint-monitor look (deep navy, electric-blue grid borders, cyan mono readouts, coral stamps). Use for any UI work in this repo, including the Jekyll site in docs/.
---

# Machine design system

Based on the Machine design skill from TypeUI (https://www.typeui.sh/design-skills/machine).
Interfaces should feel like a technical shell: deep navy screens, electric-blue
grid borders, cyan terminal readouts, coral danger stamps, dashed connector
paths, scanlines, and mono-forward UI chrome. It is built for high-information
products where the interface should feel like a console, schematic, or
operating panel.

Always dark. There is no light mode. Cream blueprint-paper cards may appear
rarely for contrast, but the monitor stays dominant.

## Tokens

| Token | Value | Use |
| --- | --- | --- |
| Surface | `#0E1530` | Primary monitor screen background |
| Panel | `#0B1022` | Cards, panels, schematic regions, nav tabs |
| Brand | `#4E7BF2` | Selection, active navigation, borders, links |
| Brand Strong | `#6E97FF` | Strong electric-blue highlights and focus states |
| Console | `#52DCFF` | Terminal readouts, status text, system labels |
| Danger | `#FF5A52` | Error stamps, warnings, destructive states |

Supporting values used in this repo: body text `#C9D3F5`, strong text
`#F2F5FF`, muted text `#8A98C4`, cream card `#F1E9D6` with navy `#0E1530` ink.

## Typography

Three voices:

- **Display**: Space Grotesk, tight tracking, for headings.
- **Body**: Manrope, for longer copy.
- **Mono** (dominant in the chrome): Share Tech Mono (VT323 is an alternative),
  for navigation, list items, buttons, labels, section codes and status lines.
  Mono labels are uppercase with wide letter spacing, for example `SYS // LAUNCH`.

## Layout and shape

- Viewport-filling monitor shell: top bar, squared nav tabs, a working area,
  and a console-style footer. Framed, technical and schematic, never a long
  marketing page.
- Faint blueprint grid on the surface. Faint scanlines over the screen.
- Panels: dark panel fill, luminous electric-blue border with a soft glow,
  rounded corners (about 14px), cyan corner brackets like a viewfinder.
- The top bar is a capsule with a glowing border. Buttons are pills with mono
  uppercase text: filled electric blue for primary, outlined for secondary.
- Dashed connector paths with small square nodes link related items
  (timelines, lists, section dividers).

## Components

- **Labels and readouts**: cyan mono, uppercase, letter-spaced. Secondary
  readout lines in muted mono separated by `·`.
- **Tabs**: squared, mono, with a small numeric code (`01`, `02`). The active tab
  gets a brand tint and border.
- **Stamps**: coral outlined box, mono uppercase, slightly rotated. Use them for
  warnings or priority markers, sparingly.
- **Cream cards**: blueprint paper with a navy grid and navy text, plus a coral
  stamp. One per page at most.
- **Console footer**: mono status line with a `>` prompt and a blinking block
  cursor.

## Accessibility

- Body text on navy must meet WCAG AA. Use Brand Strong or Console for link and
  label text, not Brand, at small sizes.
- Filled buttons use dark navy text on Brand Strong.
- Keep scanlines faint. Stop blinking and pulsing under
  `prefers-reduced-motion`.
- Visible focus rings in Console cyan.

## In this repo

- Stylesheet and tokens: `docs/assets/css/machine.css`
- Layouts: `docs/_layouts/`, shared brief markup: `docs/_includes/brief.html`
- Fonts are self-hosted in `docs/assets/fonts/` (SIL Open Font License).
