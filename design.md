# SplitBind design system

This file is the durable visual contract for the multi-page web application. The implementation source of truth is `apps/web/tokens.css`.

## Direction

- Genre: modern-minimal.
- Macrostructure: Split Studio — product context and task surface share the viewport without a dashboard-card wall.
- Theme: Security Operations Workspace — off-white paper, near-black ink, restrained indigo accent.
- Navigation: compact edge-aligned top application bar (N9), replacing the former vertical rail.
- Typography: Manrope for display hierarchy, Inter for body copy, system monospace for identifiers and evidence.
- Shape: 10px controls and 14px major surfaces; pills are reserved for genuine status semantics.
- Imagery: none. The product is evidence-led and does not need decorative illustration.
- Motion: GSAP route entrance only, using opacity and at most 10px vertical translation. Reduced-motion users receive a short opacity change without translation.

## Page contracts

- Login: two equal desktop panels, one short product sentence, and a compact authentication form.
- Issue and verify: large task heading, explanatory copy, then a two-column work surface with a deliberate upload dropzone.
- Job and result detail: a primary status surface followed by a plain-language conclusion; secondary technical evidence stays collapsed until requested.
- Desktop-only: the application targets laptop and desktop viewports from 1024 CSS pixels; no mobile layout is provided.

## Interaction and accessibility

- Every interactive control has a visible `:focus-visible` outline.
- Icons supplement text and retain an accessible text label.
- Hover styles are restricted to hover-capable pointers.
- Error, success, and processing state are never communicated by color alone.
- Layout must remain usable from 1024 through 1920 CSS pixels without horizontal scrolling.

## Exports

### CSS source of truth

Use `apps/web/tokens.css`. Application CSS imports it before all rules.

### Tailwind CSS v4

```css
@theme {
  --color-paper: oklch(98.2% 0.006 275);
  --color-paper-2: oklch(95.8% 0.012 275);
  --color-paper-3: oklch(92.5% 0.018 275);
  --color-ink: oklch(18% 0.025 275);
  --color-ink-2: oklch(29% 0.027 275);
  --color-muted: oklch(49% 0.025 275);
  --color-rule: oklch(84% 0.018 275);
  --color-rule-2: oklch(72% 0.025 275);
  --color-accent: oklch(52% 0.22 278);
  --color-focus: oklch(58% 0.2 278);
  --font-display: "Manrope Variable", "Manrope", ui-sans-serif, system-ui, sans-serif;
  --font-body: "Inter Variable", "Inter", ui-sans-serif, system-ui, sans-serif;
  --font-outlier: "Cascadia Mono", ui-monospace, monospace;
  --spacing-3xs: 0.25rem;
  --spacing-2xs: 0.5rem;
  --spacing-xs: 0.75rem;
  --spacing-sm: 1rem;
  --spacing-md: 1.5rem;
  --spacing-lg: 2rem;
  --spacing-xl: 3rem;
  --spacing-2xl: 4.5rem;
  --text-xs: 0.75rem;
  --text-sm: 0.875rem;
  --text-md: 1.125rem;
  --text-lg: 1.375rem;
  --text-xl: 1.75rem;
  --text-2xl: 2.25rem;
  --radius-card: 0.875rem;
  --radius-pill: 999px;
  --radius-input: 0.625rem;
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-in: cubic-bezier(0.7, 0, 0.84, 0);
  --ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);
}
```

### DTCG tokens

```json
{
  "$schema": "https://design-tokens.github.io/community-group/format/",
  "color": {
    "paper": { "$value": "oklch(98.2% 0.006 275)", "$type": "color" },
    "paper-2": { "$value": "oklch(95.8% 0.012 275)", "$type": "color" },
    "paper-3": { "$value": "oklch(92.5% 0.018 275)", "$type": "color" },
    "ink": { "$value": "oklch(18% 0.025 275)", "$type": "color" },
    "ink-2": { "$value": "oklch(29% 0.027 275)", "$type": "color" },
    "muted": { "$value": "oklch(49% 0.025 275)", "$type": "color" },
    "rule": { "$value": "oklch(84% 0.018 275)", "$type": "color" },
    "accent": { "$value": "oklch(52% 0.22 278)", "$type": "color" },
    "focus": { "$value": "oklch(58% 0.2 278)", "$type": "color" }
  },
  "font": {
    "display": { "$value": "Manrope Variable, Manrope, ui-sans-serif, system-ui, sans-serif", "$type": "fontFamily" },
    "body": { "$value": "Inter Variable, Inter, ui-sans-serif, system-ui, sans-serif", "$type": "fontFamily" },
    "outlier": { "$value": "Cascadia Mono, ui-monospace, monospace", "$type": "fontFamily" }
  },
  "space": {
    "3xs": { "$value": "0.25rem", "$type": "dimension" },
    "2xs": { "$value": "0.5rem", "$type": "dimension" },
    "xs": { "$value": "0.75rem", "$type": "dimension" },
    "sm": { "$value": "1rem", "$type": "dimension" },
    "md": { "$value": "1.5rem", "$type": "dimension" },
    "lg": { "$value": "2rem", "$type": "dimension" },
    "xl": { "$value": "3rem", "$type": "dimension" },
    "2xl": { "$value": "4.5rem", "$type": "dimension" }
  },
  "duration": {
    "micro": { "$value": "120ms", "$type": "duration" },
    "short": { "$value": "220ms", "$type": "duration" },
    "long": { "$value": "420ms", "$type": "duration" }
  }
}
```

### shadcn/ui variables

```css
:root {
  --background: 98.2% 0.006 275;
  --foreground: 18% 0.025 275;
  --card: 99.6% 0.002 275;
  --card-foreground: 18% 0.025 275;
  --popover: 99.6% 0.002 275;
  --popover-foreground: 18% 0.025 275;
  --primary: 52% 0.22 278;
  --primary-foreground: 99% 0.004 275;
  --secondary: 92.5% 0.018 275;
  --secondary-foreground: 29% 0.027 275;
  --muted: 95.8% 0.012 275;
  --muted-foreground: 49% 0.025 275;
  --accent: 52% 0.22 278;
  --accent-foreground: 99% 0.004 275;
  --destructive: 47% 0.18 25;
  --destructive-foreground: 99% 0.004 275;
  --border: 84% 0.018 275;
  --input: 84% 0.018 275;
  --ring: 58% 0.2 278;
  --radius: 0.875rem;
}
```
