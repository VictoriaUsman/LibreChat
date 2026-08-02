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

- **Work item:** *Apply ROMChat Branding to the Browser Tab and Login Screen* (ADO WI # 12628)
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

- **Work item:** *Apply ROMChat Branding to the Browser Tab and Login Screen* (ADO WI # 12628)
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

- **Work item:** *Apply ROMChat Branding to the Browser Tab and Login Screen* (ADO WI # 12628)
- **Added:** 2026-07-30 by Ian Tristan
- **Files touched:** `client/public/assets/logo.svg`
- **What:** Replaced LibreChat's logo with the ROMChat bubble monogram. Rendered on the login screen
  at `AuthLayout.tsx:65`. Upstream's file is `viewBox="0 0 512 512"`, and the ROMChat master is
  512x512, so the replacement is a drop-in with no layout change.
- **True vector, 737 bytes.** Four `<path>` elements — rounded-square container, speech bubble with
  tail, and the `R`/`C` glyphs (the `R` uses `fill-rule="evenodd"` for its counter). No embedded
  raster, no base64. Two colours: `#1F6FEB` (brand blue) and `#fff`. Carries `role="img"`,
  `aria-label="ROMChat"` and a `<title>`, so the login screen announces the mark to screen readers.
- **⚠️ Reconstructed geometry, not the brand's vector master (ADO WI # 12687).** The first cut of
  this patch shipped the approved 512x512 PNG as a base64 data URI because no vector master existed.
  No master was ever supplied; instead, on 2026-08-01 the reviewer approved rebuilding the mark as
  vector geometry. The container, bubble and tail are exact primitives and match the raster closely.
  **The `R` and `C` are geometric constructions — stems, arcs and an `evenodd` counter — not the
  original typeface.** A real font's letterforms carry optical corrections and specific terminals
  that this does not reproduce, so the monogram is a close likeness rather than the authored mark.
  737 bytes against the 30KB raster, and smaller than upstream's own 5.8KB logo.
- **What would retire this caveat:** the actual source file the PNG was exported from (`.ai`, `.svg`,
  `.eps`, `.pdf`, Figma), or the typeface name used for the "RC" so the glyphs can be set rather than
  approximated. Either replaces paths 3 and 4 and lets this bullet be deleted. Until then, do not
  reuse this file as a brand asset outside the login screen — at 40px the difference is invisible,
  on a business card it would not be.
- **How to verify:** Open `/login`. The ROMChat bubble monogram appears above the login card, not
  LibreChat's logo. No 404 for `assets/logo.svg`; it serves as `image/svg+xml`. Zoom to 300% or use
  a 2x/3x DPI display — edges stay crisp, which the raster version could not do.
- **Upstream status:** not submitted — ROMTech-specific, permanent.
- **Merge notes:** Upstream rarely touches this file, but if it does, resolution is
  `git checkout --ours` — their logo is never what we want. Never regenerate this file by tracing a
  raster export of the mark; the paths here come from the supplied vector master, and a trace is not
  the mark.

### Artifacts control — developer sub-options stripped, core toggle kept (default off)

- **Work item:** *Strip Artifacts Sub-Options, Keep the Core Toggle Off by Default* (ADO WI # 12631)
- **Added:** 2026-07-30 by Ian Tristan
- **Files touched:** `client/src/components/Chat/Input/Artifacts.tsx` (badge),
  `client/src/components/Chat/Input/ArtifactsSubMenu.tsx` (Tools-dropdown row),
  `client/src/components/Chat/Input/ToolsDropdown.tsx` (handlers + props),
  `client/src/components/Chat/Input/__tests__/Artifacts.spec.tsx` (new),
  `client/src/utils/artifactMode.ts` (new, stale-value migration),
  `client/src/utils/__tests__/artifactMode.spec.ts` (new),
  `client/src/Providers/BadgeRowContext.tsx` (restore path),
  `client/src/utils/endpoints.ts` (restore path).
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
- **Stale-value migration (review finding F8).** Removing the sub-options stranded anyone who had
  already picked one: `shadcnui`/`custom` persist in localStorage under
  `LAST_ARTIFACTS_TOGGLE_<convo>`, and restoring one verbatim leaves the badge reading *on* while
  nothing renders — `useToolToggle` counts any non-empty string as enabled
  (`useToolToggle.ts:62-67`), while `generateArtifactsPrompt` returns null for `CUSTOM`, so no
  artifact instructions are ever appended. With the sub-menu gone there is no way to clear it; it
  self-heals only if the user happens to toggle off and back on. `normalizeArtifactsMode`
  (`client/src/utils/artifactMode.ts`) folds both stale values to `DEFAULT`, and is applied at **both**
  restore paths: `BadgeRowContext.tsx:136` (badge row init) and `endpoints.ts:243` (the
  `applyModelSpecEphemeralAgent` override layer for existing conversations). Fixing only the first
  leaves the bug reachable by navigating into an existing conversation. `''` (off) and the boolean
  shape used by the other toggles pass through untouched, so this cannot switch Artifacts *on* for
  anyone.
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

### Speech engine default — `browser` → `external` (Azure OpenAI read-aloud)

- **Work item:** *Natural Text-to-Speech via Azure OpenAI TTS (Config + Infra)* (ADO WI # 12632)
- **Added:** 2026-07-30 by Ian Tristan
- **Files touched:** `client/src/store/settings.ts`,
  `client/src/store/__tests__/settings.spec.tsx` (new)
- **What:** One line. The `engineTTS` atom's default changes from `'browser'` to `'external'`
  (`settings.ts:67`), so read-aloud synthesizes through the server-configured TTS provider —
  `speech.tts.azureOpenAI` in the deployment's `librechat.yaml` (separate repo), pointed at the
  `romtech-tts` / `gpt-4o-mini-tts` deployment — instead of the browser's Web Speech API. Azure
  OpenAI TTS is covered by the Microsoft BAA, so it is PHI-safe; OpenAI and ElevenLabs are not and
  are configured in no environment.
- **Why:** The robotic voice users complain about *is* `'browser'` — Web Speech API synthesis. The
  Azure deployment and the `librechat.yaml` block change nothing anyone hears until this default
  flips, and **no server config can flip it.** There is a config key that looks like it should
  (`speech.speechTab.textToSpeech.engineTTS`, plumbed through `getCustomConfigSpeech.js` →
  `useSpeechSettingsInit.ts`, which does set the atom and does respect existing localStorage), but
  its zod enum only accepts *provider* names — `'openai' | 'azureOpenAI' | 'elevenlabs' | 'localai'`
  (`packages/data-provider/src/config.ts:815`) — while the client atom accepts only
  `'browser' | 'external'` (`TTSEndpoints`, `client/src/common/types.ts:40-43`). Setting it writes an
  unmatched value, `MessageAudio.tsx:16` resolves `TTSComponents[engineTTS]` to `undefined`, and the
  read-aloud button renders nothing — and worse, the sanitizing effect at
  `Speech.tsx:142-147` rewrites the value to `'browser'` *and persists it* the first time that user
  opens Settings → Speech, permanently opting them out. So the upstream config surface for this is
  broken, not merely absent, and the one-line default is the correct lever.
- **Why the default reaches everyone without asking employees to change a setting**
  (verified in `client/src/store/utils.ts:4-31`): `atomWithLocalStorage` persists only inside
  `onSet` — i.e. only when a user actively changes the setting. On startup it applies a stored value
  *only if one exists*. Every user who has never opened Settings → Speech has no stored `engineTTS`
  and picks up the new default on next load; anyone who deliberately chose `browser` keeps it, which
  is the behavior we want. Locked by the new spec (all three cases: default, stored value wins, and
  "not written until changed"), rather than left implicit.
- **No voice needs picking, either:** `useTTSExternal.ts:45-57` auto-selects `voices[0]` from the
  server's list when nothing is stored, and the server-side `getVoice()`
  (`api/server/services/Files/Audio/TTSService.js:71-78`) falls back to a configured voice if the
  request carries none. `voices` is `["nova"]`, so a clean profile gets nova with no Settings visit.
- **Failure behavior is upstream's and is already graceful** — no patch needed: a TTS error surfaces
  as the `com_nav_audio_process_error` toast from `useTextToSpeechExternal.ts`'s `onError`, and the
  chat view is unaffected. An invalid/missing key is an Azure 401 down that same path.
- **How to verify:** In a **clean browser profile** (or with `engineTTS` absent from localStorage),
  open a conversation and click read-aloud on an assistant message. You should hear the Azure nova
  voice, not the OS voice, having visited no settings page. DevTools → Network shows
  `GET /api/files/speech/tts/voices` returning `["nova"]` and `POST /api/files/speech/tts/manual`
  returning `audio/mpeg`; Settings → Speech → Engine reads "External". Then set Engine to "Browser"
  by hand, reload, and confirm it stays
  Browser — the stored value still wins. `localStorage.removeItem('engineTTS')` + reload returns to
  the Azure voice. Unit side: `cd client && npx jest src/store/__tests__/settings.spec.tsx`.
- **Upstream status:** not submitted. Upstream's `'browser'` default is defensible for them (it is
  the only engine that works with no server config), so this is a deployment choice, not a bug fix —
  expect to re-apply it on every merge.
- **Merge notes:** A one-token change on a line upstream rarely touches; if it conflicts, keep
  `'external'`. **The one thing that would obsolete this patch:** upstream widening
  `speechTab.textToSpeech.engineTTS` to accept `'browser' | 'external'` (or otherwise letting server
  config set the engine). If that lands, **drop this patch** and set the engine in `librechat.yaml`
  instead — re-check `config.ts`'s `speechTab` schema against `TTSEndpoints` at each merge. Also
  re-check `useSpeechSettingsInit.ts`: it only applies server defaults when the localStorage key is
  absent, and this patch depends on that ordering staying intact.

### Remove "Upload to Provider" attachment option

- **Work item:** PBI 12626
- **Added:** 2026-07-30 by Andrea Tiamson
- **Files touched:** `client/src/components/Chat/Input/Files/AttachFileMenu.tsx`,
  `client/src/components/Chat/Input/Files/DragDropModal.tsx`,
  `client/src/components/Chat/Input/Files/__tests__/AttachFileMenu.spec.tsx`
- **What:** Removed the "Upload to Provider" menu item from both the paperclip attach menu and the
  drag-and-drop modal. Both files had the same shape: `if (isDocumentSupportedProvider(...)) { push
  "Upload to Provider" } else { push "Upload Image" }`. The condition was inverted so the "Upload
  Image" branch is now the only one that ever pushes an item in that menu slot (only for providers
  that don't support documents); the document-provider branch no longer pushes anything. Unused
  imports (`FileImageIcon`, `isBedrockDocumentType`) were dropped along with the dead
  `isValidProviderFile`/`supportsImageDocVideoAudio`/`isBedrock` helpers in `DragDropModal.tsx`
  that existed only to gate the removed option. Updated `AttachFileMenu.spec.tsx` to assert the
  option's absence instead of its presence (`DragDropModal.spec.tsx` only tested the
  `isDocumentSupportedProvider` helper in isolation, so it needed no changes).
- **Why:** "Upload to Provider" sends files straight to the model endpoint instead of to File
  Search. For PDFs on document-supporting providers this silently no-ops — no error, no result, and
  the user believes the document was attached. No `librechat.yaml`/env-var toggle exists for
  individual attach-menu items, so this required a source change.
- **How to verify:** In the running app, open the paperclip/attach menu — for a document-supporting
  provider (e.g. OpenAI, Anthropic) no image/document item appears in that slot at all; for a
  non-document provider (e.g. an `agents` endpoint with no resolved provider) "Upload Image" still
  appears. Drag a PDF onto the chat window — the drag-drop modal never offers "Upload to Provider".
  Upload a PDF via "Upload for File Search" and confirm a grounded answer works end-to-end. Confirm
  no console errors/React warnings when opening either UI, and that the attach menu is still fully
  keyboard-navigable (Tab/arrow keys + Enter).
- **Upstream status:** not submitted
- **Merge notes:** Upstream's `AttachFileMenu.tsx`/`DragDropModal.tsx` will very likely still have
  the original if/else pushing "Upload to Provider" — expect a conflict on that block each merge.
  Re-apply the inverted condition (keep only the "Upload Image" push, gated on
  `!isDocumentSupportedProvider(...)`) unless upstream has fixed the underlying PDF no-op bug, in
  which case this patch can be dropped and "Upload to Provider" restored.

### Paperclip becomes one-click File Search upload

- **Work item:** PBI 12627 (depends on PBI 12626, above — both touch `AttachFileMenu.tsx`)
- **Added:** 2026-07-30 by Andrea Tiamson; revised 2026-07-31 (code review follow-ups)
- **Files touched:** `client/src/utils/files.ts`,
  `client/src/hooks/Files/useFileHandling.ts`,
  `client/src/components/Chat/Input/Files/AttachFileMenu.tsx`,
  `client/src/components/Chat/Input/Files/AttachFileChat.tsx`,
  `client/src/components/Chat/Input/ToolsDropdown.tsx`, `client/src/locales/en/translation.json`,
  `client/src/components/Chat/Input/Files/__tests__/AttachFileMenu.spec.tsx`,
  `client/src/utils/__tests__/validateFiles.spec.ts`,
  `client/src/hooks/Files/__tests__/useFileHandling.test.ts`
- **What:** Collapsed the paperclip from a dropdown (Upload Image / OCR text / code environment /
  File Search / SharePoint) into a single one-click File Search uploader — no other upload modes
  remain on the paperclip. Clicking it directly opens the OS file picker pre-filtered to the
  endpoint's configured document types, always tags the upload with `EToolResources.file_search`,
  and sets `ephemeralAgent[file_search] = true` itself — removing the need to pre-toggle File Search
  in the "+" tools menu first. Removed the File Search toggle from `ToolsDropdown.tsx` (and its
  now-unused `useHasAccess(FILE_SEARCH)`/`VectorIcon`/pin-state plumbing) since the paperclip now
  sets the flag directly; `BadgeRowContext.tsx`/`useToolToggle.ts`/`FileSearch.tsx` (the input-row
  status chip) are untouched — same underlying `ephemeralAgent` flag, still works, still separately
  RBAC-gated. Added the RBAC check (`useHasAccess(PermissionTypes.FILE_SEARCH)`) to `AttachFileMenu`
  itself, since it never had one before and `ToolsDropdown` was the only place enforcing it — without
  adding it here, deleting the toggle would have left a permissions gap. For an ephemeral (no saved
  agent) conversation the button always shows if the capability/RBAC checks pass, since clicking it
  is what sets `fileSearchAllowedByAgent` true in the first place; for a real, saved Agent it only
  shows if that agent's author actually configured `file_search` as one of its tools — the chat UI
  does not override that authoring decision.
  - **Document allowlist:** the OS picker's `accept` attribute and `validateFiles()`'s file_search
    check both derive from `endpointFileConfig.supportedMimeTypes` — the same live, admin-configured,
    per-endpoint allowlist (`librechat.yaml`'s `fileConfig.endpoints.*.supportedMimeTypes`) every
    other upload path already uses — instead of a separate hardcoded list. `validateFiles()`
    (`client/src/utils/files.ts`) has no `file_search`-specific branch at all; `toolResource` doesn't
    change `mimeTypesToCheck` for it, so it validates against whatever the endpoint's own
    `supportedMimeTypes` already is, same as an unspecified-toolResource upload. `AttachFileMenu.tsx`
    builds the `accept` string from that same list via a new `mimeTypesToAcceptString()` helper
    (`client/src/utils/files.ts`), which recovers literal `"type/subtype"` strings from simple,
    admin-configured regexes via `.source` (undoing the backslash-escaping of `/` that
    `RegExp.prototype.source` always applies, regardless of how the regex was constructed) and
    silently omits any regex that doesn't reduce to one literal type (e.g. LibreChat's built-in
    bundled-alias defaults) from the visible hint — validation is unaffected by what this omits,
    since it checks the full regex list, not this string. This also finally uses the
    `endpointFileConfig` prop the component always accepted but never read.
  - **Keyboard activation:** the button has no `onKeyDown`/`onKeyDownCapture` handler. A native
    `<button>` already synthesizes a `click` event on Enter/Space, so a separate handler calling
    `inputRef.current.click()` again double-fired the file picker and the `ephemeralAgent` update on
    every keypress. `AttachFileMenu.spec.tsx`'s keyboard test uses `userEvent.keyboard('{Enter}')`
    (not `fireEvent.keyDown`, which doesn't synthesize the click a real browser fires) and asserts
    the underlying `.click()` fired exactly once, so a regression here fails loudly instead of
    passing silently.
  - **Upload failure and File Search state:** `useFileHandling.ts`'s upload `onError` only turns
    `ephemeralAgent[file_search]` off when the failed file was the *last* file_search file in the
    conversation (checks `files` — the existing `Map<string, ExtendedFile>` state — for any other
    entry with `tool_resource === 'file_search'` before disabling). Previously it unconditionally set
    the flag to `false` on any file_search upload failure: uploading two PDFs where the second fails
    would silently stop the first, already-embedded, successfully-searchable document from being
    searched on the next turn, with the UI still showing it attached — the same silent-no-op failure
    class PBI 12626 exists to remove, reintroduced by copying `execute_code`'s reset pattern without
    noticing it doesn't generalize (`execute_code` is a single on/off capability; file_search can have
    multiple files). `execute_code`'s reset is left as-is (matches upstream; not this patch's concern).
  - **Unused props (partial):** `AttachFileMenuProps` no longer declares `endpoint` — it was passed
    from `AttachFileChat.tsx` but never read inside `AttachFileMenu`. `endpointType` and
    `useResponsesApi` are still declared and still passed, and are still unused inside
    `AttachFileMenu` itself — removing those two would force removing them from
    `AttachFileChat.tsx`'s JSX as well (TS excess-property checking), which in turn would gut the
    ~15 existing `AttachFileChat.spec.tsx` assertions that use the mocked `AttachFileMenu` purely to
    observe `AttachFileChat`'s own `endpointType`/`useResponsesApi` resolution logic (which still
    runs and is still meaningful — it just no longer needs to reach `AttachFileMenu`). Deliberately
    left in place rather than rewriting that test coverage for what was flagged as a minor,
    cosmetic finding.
- **Why:** Enabling File Search required two separate, easy-to-miss decisions (toggle in "+" menu,
  then the right dropdown item) before any upload did what the user expected. No
  `librechat.yaml`/env-var toggle governs individual attach-menu behavior, so this required a source
  change. The document-allowlist, keyboard, and upload-failure behaviors above were code-review
  findings against the first version of this patch (this fork's client allowlist and the infra
  repo's `librechat.yaml` allowlist had been authored independently and disagreed in both
  directions) — fixed in place rather than tracked as separate patches, since they're corrections to
  what this same patch does, not new features.
  - **PBI 12688 closed the reconciliation loop** (2026-07-31): once the client derived its allowlist
    straight from `endpointFileConfig.supportedMimeTypes` (above), the only remaining divergence was
    the *contents* of the infra repo's `librechat.yaml` list itself. Per rule 2 above (config over
    patching), that's a config-only change — no new fork source patch, so no new entry here. The
    canonical list (and the reasoning for each inclusion/exclusion, verified against `rag_api`'s
    `document_loader.py`) is documented directly in `fileConfig.endpoints.custom.supportedMimeTypes`'s
    surrounding comment in the infra repo's `config/librechat.yaml` — that comment block is the
    owning source of truth, not this file. Net change: added `application/vnd.ms-excel` (legacy
    `.xls` — confirmed working, same Excel loader as `.xlsx`); removed `application/msword` (legacy
    `.doc` — was already broken for genuine OLE-format `.doc` files, a pre-existing "permitted but
    unreachable" bug this PBI's investigation surfaced, unrelated to the excel/powerpoint types the
    PBI named); left `application/vnd.ms-powerpoint` (legacy `.ppt`) out — it would hit the same
    loader as `.pptx` but that loader shells out to LibreOffice for the legacy format, which isn't
    installed in the `rag_api` container, so adding it today would recreate the exact bug this PBI
    exists to fix.
- **How to verify:** Click the paperclip — the OS file picker opens immediately (no dropdown),
  tooltip reads "Upload a document (PDF, Word, Excel, PowerPoint, text)", and the recommended-types
  list matches the endpoint's configured `supportedMimeTypes` exactly (e.g. `text/plain`, `text/csv`,
  `text/markdown`, `application/pdf`, docx/xlsx/pptx, legacy `.xls` for this deployment's actual
  config) — no more, no less. Upload a `.pdf`/`.csv`/`.md` and ask a question about its
  contents in the same conversation without touching any other control — expect a grounded answer.
  Open the "+" tools menu — no File Search toggle appears. Pick an unsupported type (e.g. `.png` via
  "All files") — expect a toast error and nothing attached. Upload two documents where the second
  upload fails (e.g. disconnect network mid-upload) — expect a toast error, no partial file left in
  the composer, and the *first* document to remain searchable (File Search doesn't silently turn
  off). Tab to the paperclip and press Enter — it opens the picker exactly once, not twice.
  Unit side: `cd client && npx jest src/components/Chat/Input/Files/__tests__/AttachFileMenu.spec.tsx
  src/utils/__tests__/validateFiles.spec.ts src/hooks/Files/__tests__/useFileHandling.test.ts`.
  - **PBI 12688 per-type dev checklist** (run once the updated `config/librechat.yaml` is deployed to
    the dev Container App — this needs the real `rag_api`/pgvector/LiteLLM stack, not local-only
    testing): for each of the 8 types below, upload one real file via the paperclip and ask a
    question whose answer only exists in that file's content, in a fresh conversation, without
    touching any other control:
    1. `.txt` (`text/plain`) — expect a grounded answer.
    2. `.csv` (`text/csv`) — expect a grounded answer (this is the type the original finding said was
       configured-but-unreachable from the client; confirms the client can now actually reach it).
    3. `.md` (`text/markdown`) — expect a grounded answer (same as above).
    4. `.pdf` (`application/pdf`) — expect a grounded answer.
    5. `.docx` (modern, saved from current Word/Google Docs) — expect a grounded answer.
    6. `.xlsx` (modern) — expect a grounded answer.
    7. `.pptx` (modern) — expect a grounded answer.
    8. `.xls` (genuine legacy binary format — e.g. save a sheet as "Excel 97-2003 Workbook", not just
       rename a `.xlsx`) — expect a grounded answer. This is the new addition; confirm it actually
       works and isn't silently misrouted.
    Then confirm the negative cases: attempt a `.ppt` (legacy PowerPoint) and a `.doc` (legacy Word)
    via "All files" in the OS picker — both should be silently absent from the filtered picker view,
    and if forced through "All files" anyway, client validation should reject them with a visible
    toast (not a silent no-op) since neither MIME type is in `supportedMimeTypes` anymore. Attempt a
    `.png` — same expected rejection, confirming images are still blocked on every path (upload API
    included — try posting a `.png` directly to the upload endpoint with `tool_resource=file_search`
    if you want to confirm server-side enforcement too, not just the client check).
- **Upstream status:** not submitted. The derive-from-`endpointFileConfig` allowlist approach and
  `mimeTypesToAcceptString` are generally useful beyond this fork and could be proposed upstream, but
  haven't been.
- **Merge notes:** This patch depends on the PBI 12626 patch above landing first in the same file
  (`AttachFileMenu.tsx`) to avoid a guaranteed conflict; resolve 12626 first, then re-apply this one.
  Upstream's `AttachFileMenu.tsx` will still have the full dropdown (Upload Image/OCR/code/File
  Search/SharePoint) and `ToolsDropdown.tsx` will still have the File Search toggle — expect conflicts
  in both. Re-apply the one-click single-button version of `AttachFileMenu.tsx` and the toggle
  removal in `ToolsDropdown.tsx`, unless upstream has shipped an equivalent one-click file-search
  entry point, in which case this patch (and possibly the SharePoint/OCR/code-upload removal
  specifically) should be reconsidered — this fork traded those modes away deliberately for
  simplicity, which upstream may not have. If upstream ever ships its own File-Search-specific
  document allowlist, compare it against this derive-from-`endpointFileConfig` approach before
  assuming a conflict means "keep ours."

### First-run guided tour, once per browser

- **Work item:** PBI 12633
- **Added:** 2026-07-30 by Andrea Tiamson; revised 2026-07-31 (integration review — anchor timing)
- **Revision 2026-07-31 — start gating (`GuidedTour.tsx`):** the tour originally started a fixed two
  `requestAnimationFrame`s after mount. That was not enough. The sidebar anchors (steps 3-4) paint on
  the first frames, but the composer anchors (steps 1-2) only mount once the startup-config and
  endpoints queries resolve, which is network-bound. On a cold load the walk therefore began before
  the composer existed, **skipped the upload step — the whole point of the tour — and a later step
  still marked the tour seen, so it never came back.** It now polls per frame until step 1's anchor is
  in the DOM, and **that flag gates the step walk itself, not merely what renders** —
  `useGuidedTour(onEnd, enabled)`. This distinction is the whole fix: a first attempt gated only the
  render, the walk still ran at mount, and the bug survived unchanged. If you ever refactor this,
  keep the `enabled` gate on the layout effect.
  Only step 1 is waited on deliberately: waiting on every anchor would stall the tour for the full
  timeout whenever a step is legitimately absent (e.g. hidden by permissions). Step 1's mount
  dependencies are a strict superset of step 2's, so waiting on it covers both — incidental, not
  enforced; see the comment in `GuidedTour.tsx`. Later steps keep the original skip-if-missing
  behaviour. On the 8s backstop expiring with the anchor still absent the tour **does not start at
  all**, leaving `seen` unset so it retries next load — starting anyway would skip the upload step and
  still mark it seen, burning onboarding for a user whose cold load merely ran slow.
  Covered by three tests — a late-mounting anchor, a missing later anchor not delaying startup, and
  the pre-existing skip behaviour. Onboarding suite: 11/11 passing.
- **Dependency deviation (read this first):** the PBI names #12626, #12627, and **#12631** as hard
  prerequisites — "building this before ... land guarantees rework." #12626 and #12627 are the two
  patches directly above. **#12631 was not available when this was built and was explicitly skipped
  by request** rather than blocking. This is a known, deliberate risk: if #12631 changes the tour's
  anchor elements (paperclip, tools menu, new-chat button, or account menu), the steps in
  `client/src/components/Onboarding/tourSteps.ts` will need updating to match. Whoever picks up
  #12631 should check this file's anchors against the post-#12631 UI before considering this patch
  done.
- **Files touched:** `packages/data-provider/src/config.ts` (one `LocalStorageKeys` member),
  `client/src/routes/Root.tsx` (one mount line), `client/src/locales/en/translation.json` (new
  `com_onboarding_tour_*` keys), and everything new under `client/src/components/Onboarding/`:
  `tourSteps.ts`, `useTourSeen.ts`, `useGuidedTour.ts`, `TourPopover.tsx`, `GuidedTour.tsx`, and
  `__tests__/GuidedTour.spec.tsx`.
- **What:** A 4-step tour (document upload, tools/Artifacts, conversations, Settings/My Files) shown
  once per browser via a new `LocalStorageKeys.GUIDED_TOUR_SEEN` flag, mounted as a sibling of
  `TermsAndConditionsModal` in `Root.tsx` (structurally mirrors that modal's mount pattern — a
  boolean-gated component in the same spot — though the ToS modal itself is actually server-side
  gated, not localStorage; this tour is localStorage-only per the PBI). Each step anchors to a
  stable, always-in-DOM outer trigger (`#attach-file-menu-button`, `#tools-dropdown-button`,
  `[data-testid="new-chat-button"]`, `[data-testid="nav-user"]`) via Radix Popper's `virtualRef`
  anchor mechanism, rather than the deeper nested items (Artifacts toggle, Settings menu item) that
  don't exist in the DOM until their parent menu is opened — a scope decision confirmed before
  building, since forcing those menus open programmatically would couple the tour to two unrelated
  menu systems (Ariakit for the account menu, the tools dropdown's own state). If an anchor is
  missing at runtime (e.g. RBAC hid that button), the step is skipped automatically instead of
  showing a popover pointing at nothing; if literally none of the four anchors are ever found, the
  tour is not marked seen, so it retries next load instead of silently burning its one shot on a
  broken render. No new dependency — reuses `@radix-ui/react-popover` (already a client dependency)
  and `framer-motion` (matching the fade/scale timing already used in
  `TwoFactorAuthentication.tsx`). `Popover.Content` is kept as one persistent node across steps, with
  only the inner `motion.div` re-keyed per step inside `AnimatePresence` — re-keying `Popover.Content`
  itself conflicts with `AnimatePresence`'s ref requirements (produced a real React ref warning
  during development; fixed by not re-mounting the Radix primitive on every step). The tour is
  mounted in `Root.tsx` only once we're certain the Terms modal won't also be showing (ToS feature
  disabled, or `termsData` has resolved as already-accepted), rather than merely checking the
  current `showTerms` boolean, to avoid a race where the tour could flash on before the ToS query
  resolves.
- **Why:** New users have no way to discover document upload, tools/Artifacts, conversation
  management, or Settings except by accident. No `librechat.yaml`/env-var can add a client-side
  onboarding overlay, so this required new source files.
- **How to verify:** Clear `localStorage`, reload — the tour appears, pointing at the paperclip, then
  the "+" tools button, then the new-chat button, then the account-menu button, in that order.
  Reload again — it does not reappear. Clear `localStorage` again — it reappears. Press Escape at any
  step — it closes and does not come back on reload. Tab through a step — focus cycles only among
  that step's Back/Skip/Next buttons, and Escape/Shift+Tab/Tab all work without a mouse. If ToS
  modal-acceptance is enabled in this environment, confirm the tour never appears until after Terms
  is accepted, and that dismissing/accepting Terms doesn't also silently dismiss the tour.
- **Upstream status:** not submitted — fork-only feature, not a candidate for upstreaming.
- **Merge notes:** Purely additive (new directory, one enum member, one mount line) — should not
  conflict on an upstream merge. The one thing to re-check after any merge: confirm the four anchor
  selectors in `tourSteps.ts` still match real elements in whatever `AttachFileMenu.tsx`,
  `ToolsDropdown.tsx`, `NewChat.tsx`, and `AccountSettings.tsx` look like post-merge.

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
