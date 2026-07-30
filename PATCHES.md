# PATCHES — ROMChat's divergences from upstream LibreChat

This file is the **complete inventory of every deliberate change this fork makes to upstream
LibreChat source.** It is the checklist we walk during an upstream merge.

**Why this exists.** Our upgrade path is `git merge upstream` (see §Upstream merge below). The cost
of that merge is proportional to how far we've diverged — so we keep the patch set **small,
justified, and documented**. When a merge conflicts in a file, whoever resolves it is usually not
whoever wrote the patch; without an entry here, the "safe" resolution is to keep ours forever, and
dead patches accumulate. Every entry answers: *what were we trying to achieve, and does upstream's
new code already achieve it?*

**Rules:**

1. **Every source change to upstream files gets an entry here, in the same PR.** No exceptions —
   a patch that isn't listed is a patch nobody can safely resolve later.
2. **Prefer config over patching.** If `librechat.yaml` (or an env var, or the infra repo) can do it,
   do it there and *don't* touch the fork. Config changes cost nothing at merge time; patches cost
   forever. See `ChatGptForEmployees.docs/local/LibreChat_Fork_Plan.md`.
3. **Keep patches small and localized.** Prefer additive/overridable changes over rewriting an
   upstream file. The smaller the touched surface, the smaller the conflict.
4. **Consider upstreaming.** If a change is generally useful, open a PR against
   `danny-avila/LibreChat`. Merged upstream = the patch deletes itself at the next merge.

> Files that are **ours**, not upstream's, don't belong here — they can't conflict.
> Currently: `azure-pipelines.yml` (our ACR build) and this file.

### This file is NOT a deployment log

It records **code divergences**, not builds or releases. Do **not** add image digests, build numbers,
or "what's deployed" here — every build produces a new digest, so any such list is stale the moment
it's written, and it would compete with the record that actually governs deploys.

**To answer "which build is running, and since when?"** use sources that are derived, not typed:

| Question | Where to look |
|---|---|
| What digest is dev *supposed* to run? | `main.dev.bicepparam` in the infra repo — **the authoritative source; it's what deploys** |
| When did it change, and via which PR? | `git log -p --follow ChatGptForEmployees.bicep/main.dev.bicepparam` |
| What is *actually* serving right now? | `az containerapp revision list -n ca-librechat-dev -g rg-dev-shared` |
| Which fork commit is that image built from? | **Settings → About in the running app** — the image self-reports `BUILD_COMMIT` / `BUILD_BRANCH` / `BUILD_DATE` |

---

## Entry template

Copy this block for each patch. Keep entries in the order they were added.

```markdown
### <short title>

- **Work item:** <ADO WI #, or PR link>
- **Added:** <YYYY-MM-DD> by <name>
- **Files touched:** `path/one.tsx`, `path/two.ts`
- **What:** <one or two sentences — the actual change>
- **Why:** <the requirement driving it. Why config couldn't do it.>
- **How to verify:** <concrete steps in the running app that prove the patch is alive>
- **Upstream status:** <not submitted | PR #N open | merged upstream in vX.Y.Z — DROP this patch>
- **Merge notes:** <anything a future resolver needs: what upstream code it sits next to,
  what would make this patch obsolete, whether it can simply be dropped>
```

---

## Current patches

> Until 2026-07-30 this fork was at **zero source patches** — an unmodified upstream `v0.8.6`
> (fork commit `566e20b6`) plus our own `azure-pipelines.yml`. A build of exactly that tree was
> deployed to dev on 2026-07-28 and behaved identically to upstream's published image, which is how
> we proved the build/deploy path before taking on any source risk.

Keep the patch set as small as possible. Add entries below as patches land.

### ROMChat branding — static tags in `client/index.html`

- **Work item:** *Apply ROMChat Branding to the Browser Tab and Login Screen* (ADO WI # TBD)
- **Added:** 2026-07-30 by Ian Tristan
- **Files touched:** `client/index.html`
- **What:** Three static tags in the document head: `<title>` `LibreChat` → `ROMChat`,
  `<meta name="description">` rewritten to drop the LibreChat reference, and
  `<meta name="theme-color">` `#171717` → `#1F6FEB` (the approved ROMChat blue, the same blue the
  Help & FAQ page uses).
- **Why:** Config cannot reach any of these. `APP_TITLE=ROMChat` is already set in infra and drives
  the in-app title, but only *after* boot — `useAppStartup.ts` sets `document.title` from
  `startupConfig.appTitle`, which requires the `/api/config` fetch to resolve. Until then the browser
  renders the static `<title>` from this file, so an unpatched build flashes "LibreChat" on every
  cold load. It is not fixable by env var either: `client/vite.config.ts` sets
  `envPrefix: ['VITE_', 'SCRIPT_', 'DOMAIN_', 'ALLOW_']`, so `APP_TITLE` is never exposed to the
  client build, and there is no HTML-transform plugin. Same for the two `<meta>` tags — no config
  surface exists for them at all.
- **How to verify:** Hard refresh the app with cache disabled. (1) The tab title reads `ROMChat`
  from the very first paint, with no "LibreChat" flash before the app boots. (2) View source →
  `<meta name="theme-color" content="#1F6FEB">` and a `<meta name="description">` with no mention of
  LibreChat. (3) The in-app header/title is still `ROMChat` from `APP_TITLE` and is not doubled up —
  the post-boot `document.title` assignment now writes the same string the static tag already had.
- **Upstream status:** not submitted — ROMTech-specific, will never be upstreamed. This patch is
  permanent; expect to re-apply it on every merge.
- **Merge notes:** Upstream owns this file and edits the head block occasionally (icon links, PWA
  meta, the inline theme bootstrap script). Conflicts here are expected and are always resolved the
  same way: **take upstream's version of the file, then re-apply exactly these three tag values.**
  Do not keep our whole file — we'd silently drop upstream's other head changes.
  Related but deliberately *not* patched: `client/vite.config.ts` still declares the PWA manifest as
  `name: 'LibreChat'` / `theme_color: '#009688'`. Mobile/PWA home-screen icons are out of scope
  (ROMChat is a browser-at-work tool reached through Okta; nothing is meant to live on phones), so
  that is a known, accepted divergence from the branding — not an oversight.
  The favicons and `logo.svg` landed separately — see the following entries.

### ROMChat branding — favicons

- **Work item:** *Apply ROMChat Branding to the Browser Tab and Login Screen* (ADO WI # TBD)
- **Added:** 2026-07-30 by Ian Tristan
- **Files touched:** `client/public/assets/favicon-16x16.png`, `client/public/assets/favicon-32x32.png`
- **What:** Both favicons replaced with the ROMChat mark. Filenames are unchanged, so `index.html`
  needs no markup change. **The two sizes use different croppings of the same mark, deliberately:**
  - `favicon-32x32.png` — the full bubble monogram (blue field, white speech bubble with tail,
    blue "RC"), cropped to the bubble's bounding box with a small margin so it fills the canvas.
  - `favicon-16x16.png` — **RC only, white on the blue field, bubble omitted.**
- **Why:** Config cannot reach static assets at all. The split treatment is forced by geometry: in
  the source mark the "RC" glyphs are only ~22% of the canvas height, so a straight downscale to
  16px yields a **0.78px stroke** — sub-pixel, and the monogram renders as a grey smear, failing the
  "legible at 16px" acceptance criterion. Dropping the bubble at 16px and letting the glyphs fill
  80% of the canvas raises the stroke to **1.66px**, which resolves cleanly. At 32px the full bubble
  is comfortably legible, so it is kept there for fidelity to the approved artwork. Per-size
  renderings are normal favicon practice — it is why multiple sizes exist.
- **Source + how to regenerate:** derived from `ROMChat-1c-bubble-monogram-blue.png` (512x512, the
  approved mark; 77% `#1F6FEB` / 17% white). The master is **not** committed here — get it from the
  brand owner. Geometry measured from that file: bubble bbox `x 104..407, y 132..380`; RC glyph bbox
  `x 164..357, y 169..283` (the tail occupies `y 319..380` and must be excluded, or the crop picks it
  up as stray bars). 16px = glyphs at 80% width, centred on `#1F6FEB`; 32px = a square crop of 72% of
  the master's width, centred on the bubble bbox. That 72% figure was tuned by eye: a tighter crop
  (62%) reads as legible but pushes the bubble to the tile edges and no longer looks like the mark;
  no crop at all keeps fidelity but leaves the RC soft. Both sizes get rounded corners at radius 16%
  of the side, matching the master. Lanczos resampling throughout.
- **How to verify:** Hard refresh with cache disabled. The tab icon is the ROMChat mark at both 16px
  and 32px (browsers pick by DPI/zoom, so check at 100% and 200%). At 16px the "RC" must be readable
  as two distinct letters, not a smear. No 404s for `assets/favicon-*.png` in the network tab.
- **Upstream status:** not submitted — ROMTech-specific, permanent.
- **Merge notes:** Binary files, so git reports a conflict as "both modified" with no useful diff.
  Resolution is always `git checkout --ours` — upstream changing its own favicon is irrelevant to us.
  If the brand owner ever supplies a redrawn mark optimised for small sizes, the 16px special-case
  may become unnecessary; re-measure the stroke width before assuming so.

### ROMChat branding — login-screen logo

- **Work item:** *Apply ROMChat Branding to the Browser Tab and Login Screen* (ADO WI # TBD)
- **Added:** 2026-07-30 by Ian Tristan
- **Files touched:** `client/public/assets/logo.svg`
- **What:** Replaced LibreChat's logo with the ROMChat bubble monogram. Rendered on the login screen
  at `AuthLayout.tsx:65`. Upstream's file is `viewBox="0 0 512 512"`, and the ROMChat master is
  512x512, so the replacement is a drop-in with no layout change.
- **⚠️ This is a raster embedded in an SVG wrapper, not a true vector.** The approved mark was only
  ever supplied as a 512x512 PNG; no vector master exists yet. Rather than hand-trace the "RC"
  letterforms — which would approximate the brand typography and risk distorting it — the PNG is
  embedded verbatim as a base64 data URI inside an SVG with the correct viewBox. The embedded bytes
  are identical to the master (sha256-verified), so there is no recompression loss.
- **Why this is acceptable here:** `AuthLayout.tsx:65` renders the logo inside `h-10` (40px tall)
  with `object-contain`, so the displayed size is ~40px — 512px of source is ample even at 3x DPI
  (120px). The file is 30KB vs upstream's 5.8KB, loaded on the login page only.
- **When a real vector arrives, replace this file.** Nothing else needs to change: same path, same
  filename, same viewBox. That swap is the entire follow-up.
- **How to verify:** Open `/login`. The ROMChat bubble monogram appears above the login card, not
  LibreChat's logo. No 404 for `assets/logo.svg`; it serves as `image/svg+xml`.
- **Upstream status:** not submitted — ROMTech-specific, permanent.
- **Merge notes:** Upstream rarely touches this file, but if it does, resolution is
  `git checkout --ours` — their logo is never what we want. Do not "fix" the embedded data URI by
  converting it to `<path>` data unless you have the genuine vector artwork; a trace is not the mark.

### Artifacts control — developer sub-options stripped, core toggle kept (default off)

- **Added:** 2026-07-30 by Ian Tristan
- **Files touched:** `client/src/components/Chat/Input/Artifacts.tsx` (badge),
  `client/src/components/Chat/Input/ArtifactsSubMenu.tsx` (Tools-dropdown row),
  `client/src/components/Chat/Input/ToolsDropdown.tsx` (handlers + props),
  `client/src/components/Chat/Input/__tests__/Artifacts.spec.tsx` (new).
- **What:** Removed the two developer-oriented Artifacts sub-options — "Include shadcn/ui"
  (`ArtifactModes.SHADCNUI`) and "Custom Prompt Mode" (`ArtifactModes.CUSTOM`) — from both places the
  Artifacts control appears: the badge above the composer and the "Artifacts" row inside the Tools
  dropdown. Both are now a plain on/off toggle writing `ArtifactModes.DEFAULT` or `''`, unchanged.
- **Why:** Neither option means anything to an employee audience, and `CUSTOM` is an outright
  correctness trap: `generateArtifactsPrompt()` returns `null` for that mode
  (`packages/api/src/prompts/artifacts/index.ts:412-413`), so the model gets **no** artifact
  instructions while the badge still reads "on". Artifacts silently stop rendering and the user has no
  way to tell why.
- **Default off — no code change was needed.** `useToolToggle` reads
  `ephemeralAgent?.[toolKey] ?? false` (`client/src/hooks/Plugins/useToolToggle.ts:59`) and the
  `ephemeralAgentByConvoId` atom defaults to `null`, so a fresh browser profile already starts off.
  Artifacts costs roughly 1.5–2k prompt tokens per message when enabled, so it stays opt-in. Locked by
  a regression test rather than left implicit.
- **The ROMTech system prompt is untouched in both states.** It ships as `promptPrefix` inside each
  `modelSpecs` preset in the deployment's `librechat.yaml` (separate repo, not this one). Artifact
  instructions are *appended* to `agent.additional_instructions`, and only when the mode is a
  non-empty string (`packages/api/src/agents/initialize.ts:961`) — so with Artifacts off, zero
  artifact tokens are added and `instructions` is never rewritten in either state.
- **Kept deliberately:** the pin button on the Tools-dropdown row; and the `SHADCNUI`/`CUSTOM` enum
  members with their server-side prompt branches, so agents and conversations already persisted with
  those modes keep working. This patch narrows the *chat* UI only — nothing in
  `client/src/components/Artifacts/*` (the render path) was touched.
- **Known gap — deliberately out of scope:** the Agent Builder panel
  (`client/src/components/SidePanel/Agents/Artifacts.tsx:63,71`) still offers both options, including
  the `CUSTOM` trap. It is a builder-only surface today; strip it there too if agent creation is ever
  opened to general employees.
- **How to verify:** Fresh browser profile → Artifacts badge is off. Enable it, ask for a small HTML
  page, confirm the artifact panel renders. Open the Tools dropdown → the "Artifacts" row toggles on
  click with no submenu arrow and no flyout. Tab to the badge and press Space → it toggles and
  announces state via `role="checkbox"` + `aria-checked`. Existing conversations containing artifacts
  still open and render.
- **Upstream status:** not submitted — ROMTech product decision, permanent.
- **Merge notes:** Removal-only in `Artifacts.tsx` and `ToolsDropdown.tsx`, so upstream edits inside
  the deleted blocks arrive as delete/modify conflicts — keep the deletion. If upstream adds a *third*
  sub-option, delete that too rather than accepting the hunk. `ArtifactsSubMenu.tsx` is the one
  exception to `--ours`: it also lost its `Ariakit.MenuProvider`/`MenuButton` wrapper (there is no
  submenu left to anchor) and gained `role="menuitemcheckbox"` + `aria-checked` on the row, so
  conflicts there need re-applying by hand.

<!-- new entries go here -->

---

## Upstream merge procedure

When pulling a new upstream release:

```bash
git fetch upstream --tags
git checkout -b chore/merge-upstream-vX.Y.Z main
git merge vX.Y.Z              # upstream's release tag
```

Then:

1. **Walk every entry in "Current patches" above.** For each one, confirm the patch survived the
   merge (or was deliberately dropped). Conflicts are expected exactly where entries say they'd be.
2. **Delete entries whose "Upstream status" says merged upstream** — remove the patch and the entry
   together.
3. **Re-verify each surviving patch** using its "How to verify" steps, in dev, after deploying the
   new image.
4. **Update this file's entries** with anything the merge taught you (new adjacent upstream code,
   changed file paths).
5. Build → get the digest → wire it into `main.dev.bicepparam` → deploy dev → smoke test → promote.
   See `LibreChat_Fork_Runbook.md` §4 and §6.

---

## Related docs

- **[`ROMCHAT_DEV_GUIDE.md`](./ROMCHAT_DEV_GUIDE.md)** (this repo) — start here: what this fork is,
  the branch → PR → build → deploy loop, and how to verify a change actually landed.
- **`ChatGptForEmployees.docs/LibreChat_Image_Deployments.md`** (infra repo) — which build is
  deployed where, how to bump it, and the test/prod promotion guardrails.
