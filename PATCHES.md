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
- **Added:** 2026-07-30 by Andrea Tiamson; revised 2026-08-01 (dev-testing follow-ups, `ChatGptForEmployees.docs/local/Launch_Feedback_2026-07-31.md`)
- **Anchor timing — history worth keeping:** the tour originally started a fixed two
  `requestAnimationFrame`s after mount, which was not enough. The sidebar anchors paint on the first
  frames while the composer anchors mount only once the startup-config/endpoints queries resolve. On
  a cold load the walk therefore began before the composer existed, **skipped the upload step — the
  whole point of the tour — and a later step still marked the tour seen, so it never came back.**
  Two fixes were attempted before this one: the first gated only what *rendered* while the walk still
  ran at mount, so the bug survived unchanged while looking fixed; the second gated the walk but
  waited on step 1's anchor alone, leaving later steps exposed to the same race. Both are superseded
  by the current design — `useGuidedTour` retries **each** step's anchor lookup
  (`ANCHOR_RETRY_INTERVAL_MS` × `ANCHOR_RETRY_MAX_ATTEMPTS`, ~10s), so no step can be lost to a slow
  mount and no start gate is needed at all.
  ⚠️ **If you refactor this, verify behaviourally that a late-mounting anchor still shows its step.**
  A structural read of the code passed for the fix that did not work; only a test that mounts the
  anchor late catches it.
- **Dependency deviation (read this first):** the PBI names #12626, #12627, and **#12631** as hard
  prerequisites — "building this before ... land guarantees rework." #12626 and #12627 are the two
  patches above. **#12631 was not available when this was built and was explicitly skipped by
  request** rather than blocking. This is a known, deliberate risk: if #12631 changes the tour's
  anchor elements (paperclip, tools menu, sidebar rail, or account menu), the steps in
  `client/src/components/Onboarding/tourSteps.ts` will need updating to match. Whoever picks up
  #12631 should check this file's anchors against the post-#12631 UI before considering this patch
  done.
- **Files touched:** `packages/data-provider/src/config.ts` (one `LocalStorageKeys` member),
  `client/src/routes/Root.tsx` (one mount line), `client/src/locales/en/translation.json` (new
  `com_onboarding_tour_*` keys), `client/src/components/UnifiedSidebar/ExpandedPanel.tsx` (one new
  `data-testid` per rail icon), and everything new under `client/src/components/Onboarding/`:
  `tourSteps.ts`, `useTourSeen.ts`, `useGuidedTour.ts`, `TourPopover.tsx`, `GuidedTour.tsx`, and
  `__tests__/GuidedTour.spec.tsx`.
- **What:** A 4-step tour (document upload, Artifacts, sidebar rail, Settings/My Files) shown once
  per browser via a new `LocalStorageKeys.GUIDED_TOUR_SEEN` flag, mounted as a sibling of
  `TermsAndConditionsModal` in `Root.tsx` (structurally mirrors that modal's mount pattern — a
  boolean-gated component in the same spot — though the ToS modal itself is actually server-side
  gated, not localStorage; this tour is localStorage-only per the PBI). Each step anchors to a
  stable, always-in-DOM outer trigger via Radix Popper's `virtualRef` anchor mechanism, rather than
  deeper nested items (Settings menu item, individual sidebar icons) that don't exist in the DOM
  until their parent menu is opened — a scope decision confirmed before building, since forcing
  those menus open programmatically would couple the tour to unrelated menu systems. If an anchor is
  missing at runtime (e.g. RBAC hid that button), the step is skipped automatically instead of
  showing a popover pointing at nothing; if literally none of the four anchors are ever found, the
  tour is not marked seen, so it retries next load instead of silently burning its one shot on a
  broken render. No new dependency — reuses `@radix-ui/react-popover` (already a client dependency)
  and `framer-motion` (matching the fade/scale timing already used in
  `TwoFactorAuthentication.tsx`). The tour is mounted in `Root.tsx` only once we're certain the Terms
  modal won't also be showing (ToS feature disabled, or `termsData` has resolved as already-accepted),
  rather than merely checking the current `showTerms` boolean, to avoid a race where the tour could
  flash on before the ToS query resolves.
  - **Dev-testing follow-ups (2026-08-01):**
    - **Step 2 copy corrected, not just reworded.** The dropdown this step anchors to
      (`ToolsDropdown.tsx`, `#tools-dropdown-button`) had its Web Search/Code Interpreter toggles
      removed entirely by PBI 12627/upstream config, and its File Search toggle was removed by
      PBI 12627 specifically (the paperclip sets File Search directly now — see that entry above).
      Given ROMChat's actual `librechat.yaml` (`agents.capabilities: [file_search, artifacts]`,
      everything else off), that menu offers **Artifacts only** today. The original copy named all
      three removed/never-present tools; the dev-testing note's own suggested fix (name Artifacts
      *and* File Search) would have been equally inaccurate, since File Search isn't in this menu
      either. Rewrote to name only what's actually there (`com_onboarding_tour_step_tools_title`/
      `_body`), plus a one-line definition of what an Artifact is, since the term is internal
      jargon.
      ⚠️ **Superseded twice since.** "Artifacts only" stopped being true when the File Search toggle
      was restored to this menu (see that patch below), and the wording that replaced it was itself
      rewritten by the plain-language copy pass at the end of this entry. Read that pass for the
      copy actually shipping.
    - **Step 3 rebuilt as a single "sidebar" step** covering all four icons in the
      `ExpandedPanel.tsx` rail (Close Sidebar, New Chat, Chat History, Attach Files) instead of only
      "New Chat" with vague copy — kept as one step per the decision to avoid a 4→7-step tour.
      Re-anchored from `[data-testid="new-chat-button"]` to `#close-sidebar-button` (top of the
      rail, already had both an `id` and a `data-testid`; assumes the sidebar starts expanded, the
      default state). Two of the four icons (`Chat History`, `Attach Files`) had **no** stable
      selector at all before this patch — only a localized `aria-label`, which breaks under any
      non-English locale. Added `data-testid={\`nav-icon-${link.id}\`}` to every rail icon in
      `NavIconButton` (`ExpandedPanel.tsx`) — not just the two the tour needed, since the whole rail
      had the same gap and this is cheap, generically useful test/automation infrastructure, not a
      tour-specific hack.
    - **Fixed a visible flash on "Next"** (`TourPopover.tsx`). Traced the actual mechanism: contrary
      to the dev-testing note's literal description, `currentStep` doesn't pass through `null`
      between two valid steps (`useGuidedTour.ts`'s layout effect sets it directly from step N to
      step N+1 in one update). The real cause: `Popover.Content` repositions to the new anchor the
      instant the anchor ref updates, but the outgoing content was still mid-fade-out (300ms) at
      that moment — so it visually teleported to the new position while still fading, instead of
      fading out in place. Fixed by making the exit instant (`duration: 0`, no visible fade-out) and
      only animating the entry, at the already-correct new position — avoids the reposition-while-
      visible window entirely without restructuring the mount lifecycle. Also added a defensive
      `lastStepRef` fallback (`displayStep = step ?? lastStepRef.current`) so that if `step` ever is
      transiently `null` between valid steps via some timing path not covered by the analysis above,
      the popover keeps rendering the last real step instead of unmounting — belt-and-suspenders,
      not required by the confirmed mechanism, but cheap insurance. Full "smoothly slide between
      anchors" treatment (a persistent backdrop, a pointer tail) is out of scope here — tracked in
      #12746, which this note says is likely the more complete version of the same fix; coordinate
      before #12746 lands so the two don't fight each other structurally.
    - **Fixed a critical anchor-detection timing bug** (`useGuidedTour.ts`, discovered during this
      round of testing, not in the original dev-testing note). The original implementation checked
      `document.querySelector(anchorSelector)` exactly once, in a `useLayoutEffect` keyed on the
      current step. On a real page load this is wrong: the sidebar's anchors mount well before the
      composer's (`#attach-file-menu-button`, `#tools-dropdown-button`) resolve, since the composer
      waits on conversation/config data the sidebar doesn't need — measured 3-5s apart in practice
      via a Playwright timing script. The one-shot check ran before the composer anchors existed, so
      steps 1 and 2 were silently and permanently skipped for essentially every real user on a fresh
      load; the bug was invisible in manual testing because by the time a developer paused to look,
      the anchors had already mounted. Fixed by replacing the single check with a retrying
      `setTimeout` poll (`ANCHOR_RETRY_INTERVAL_MS = 250`, `ANCHOR_RETRY_MAX_ATTEMPTS = 40`, ~10s
      total) — a step is only treated as genuinely absent (e.g. RBAC-hidden) after exhausting the
      retry window, not after a single premature check. This also let `GuidedTour.tsx` drop its
      redundant rAF-based two-frame "ready" delay, since the retry loop itself is now the readiness
      signal. Verified both via a new unit test (`GuidedTour.spec.tsx`, "retries a not-yet-rendered
      anchor instead of skipping it immediately" — mounts the anchor via direct DOM mutation
      mid-test rather than `rerender()`, since inserting a new sibling ahead of `GuidedTour` in an
      unkeyed children array shifts its position and causes React to unmount+remount it, invalidating
      a `rerender()`-based version of this test) and live against the running dev server, confirming
      the tour now starts at step 1 instead of skipping to step 3.
  - **Plain-language copy pass (2026-08-04, all four body strings):** reviewed with the product owner
    after the tour reached dev. Every step was written from the implementation outward and leaked
    internal vocabulary to an audience of non-technical staff. `client/src/locales/en/translation.json`
    only — no logic, no step order, no anchors changed.
    - **Prior finding this builds on — partly wrong, corrected 2026-08-04.** A team-lead spot-check
      after the v2 merge reported steps 2 and 3 as reading confused. Andrea Tiamson investigated
      live against a running dev server — normal transitions, frame-by-frame capture, and a rapid
      double-click on Next to rule out a state race — and concluded there was **no code-level
      swap**: step index, title and anchor tracked correctly in every case. Her diagnosis of step 2
      (that it explained step 1's control inside its own paragraph) was right and is carried into
      the rewrite below.
      ⚠️ **The "no logic bug" conclusion was wrong**, and this entry previously repeated it. There
      *was* a logic bug — see the "Step advance could render the previous step" entry below. It
      only reproduces when a step's anchor is absent, which for step 3 means a collapsed sidebar,
      which is the default below 768px. On the expanded-sidebar desktop session she tested, step 3
      works correctly and the fault is invisible. Both the copy and the logic were genuinely
      broken; fixing the copy first made the remaining symptom look like more copy trouble.
    - **Step 1 (`_upload_body`)** dropped "It's indexed for File Search automatically." Indexing is a
      mechanism the user neither controls nor needs a word for; the promise is that questions work
      immediately, so the copy now says only that.
    - **Step 2 (`_tools_body`)** dropped "the paperclip turns it on for you," which explained step 1's
      control inside step 2 and was the main reason the two steps read as blurred together. File
      Search is now described by what it does — "lets the assistant read and search the documents
      you've attached to this chat" — rather than by the name of the control.
      ⚠️ **No "it's already on" clause, deliberately — dropped 2026-08-05 after seeing it in dev.**
      Three versions were tried and all were rejected: "It's already on for anything you upload"
      and "uploading a document turns it on for you" both overclaimed, and the hedged
      "you won't usually need to turn it on yourself" didn't read well. The underlying difficulty
      is that the claim is genuinely conditional: the paperclip (`AttachFileMenu.tsx`) and the rail
      panel (`PanelTable.tsx`) set `EToolResources.file_search` unconditionally, but drag-and-drop
      routes through `useDragHelpers.ts`'s `handleOptionSelect`, which only sets the resource the
      user picked in the drop modal — dropping a file and choosing Image or Code leaves File
      Search off. Any sentence short enough for a tour either overstates it or hedges into
      mush. Step 1 already tells the user questions work right after upload, which is the part
      that matters. **If you reintroduce a version of this, re-check `handleOptionSelect` first.**
      Also: the opener is **"Open this menu for chat options."** It went "Two switches live here"
      → "Two options live here" → this. "Switches" was wrong on the code: `ToolsDropdown.tsx` rows
      toggle on row-click and render only a pin button, so there is no switch or checkbox drawn to
      look for. "Two options" was accurate but **counted the rows**, making the copy a config
      assertion that goes stale the moment a capability is toggled in `librechat.yaml` — which had
      already happened twice. The current wording names neither a control type nor a count, so it
      can't be invalidated by config at all. It also mirrors step 4's "Open this menu for…" and
      stays a description rather than an instruction, which matters because the tour's backdrop
      blocks clicks: "click here" would ask for something the user can't do until the tour ends.
    - **Step 3 (`_sidebar_body`)** rewrote the Attach Files clause as a sentence with a verb: "lets
      you add a document you've already uploaded to the chat you're in." ⚠️ This deliberately keeps
      the attach capability that the superseded branch `feature/pbi-12626-12627-12633` proposed
      removing on the grounds that the panel is read-only. It is not read-only:
      `SidePanel/Files/Panel.tsx` renders `PanelTable.tsx`, whose filename cell is `role="button"`
      with `tabIndex={0}` and `onClick`/`onKeyDown` handlers calling `handleFileClick` →
      `addFile({ ..., attached: true })`. That is the same path the File Search patch below hooks to
      auto-enable `EToolResources.file_search`. Do not "correct" this sentence back.
    - **Step 4 (`_account_body`)** reframed from "My Files, where every document you've uploaded is
      listed" to "the full list of everything you've uploaded," and extended to name **Help & FAQ**,
      which the menu has always had (`AccountSettings.tsx`, rendered unless
      `startupConfig.helpAndFaqURL === '/'`, which our config never sets) and which is plausibly the
      most useful item in it for non-technical staff. Items are listed in the order they appear in
      the menu — My Files, Help & FAQ, Settings — so the sentence can be read top-to-bottom against
      the open dropdown. Log out is left unnamed as self-evident.
      Steps 3 and 4 previously made the
      same claim in different words, which is what made the back half of the tour feel repetitive.
      The split is **editorial, not functional**: step 3's sentence is about attaching from the rail,
      step 4's is about reaching the library from the account menu. Do not read it as a difference in
      what the two surfaces show — `Files/Panel.tsx` and `MyFilesModal.tsx` both list every file
      (the modal passes a `select` that normalizes fields but drops no rows), calling the same
      `useGetFiles()`, and `PanelTable.tsx`'s "Manage Files" button opens the very same modal step 4
      opens. Step 3's copy is accurate only because it never claims to *list* anything.
    - **These strings are downstream of `librechat.yaml`, and have already been invalidated twice by
      config changes.** Anything the tour asserts about *what is on screen* is a config-dependent
      claim, not a source fact. Step 2's opener used to count the rows ("Two options live here"),
      which held only while `agents.capabilities: [file_search, artifacts]` with
      `interface.skills`/`webSearch`/`runCode` all false and no `mcpServers` block —
      `ToolsDropdown.tsx` gates six possible rows and exactly two survive that config. It no longer
      names a count, so that dependency is gone; but the two rows it then *describes* (File Search,
      Artifacts) are still exactly those keys, so flipping them still makes the step wrong.
      Step 3's four icons hold only while
      `interface.agents`/`memories`/`bookmarks`/`prompts`/`parameters` are false, which is what
      leaves `useSideNavLinks` with Chat History and Attach Files. **If you flip any of those keys,
      re-read these two strings** — nothing in the build will fail, the tour will simply lie.
- **Why:** New users have no way to discover document upload, Artifacts, the sidebar rail, or
  Settings except by accident. No `librechat.yaml`/env-var can add a client-side onboarding overlay,
  so this required new source files. The dev-testing follow-ups exist because the first version
  named features that don't exist in this deployment, described the sidebar too vaguely to be
  useful, and had a rendering artifact — QA testing this "as a new user would" is exactly the kind
  of check a tour needs before it reaches real employees.
- **How to verify:** Clear `localStorage`, reload on a genuinely fresh page load (not a hot-reloaded
  dev session, which masks the timing bug above) — the tour appears, pointing at the paperclip
  ("Upload documents"), then the "+" tools button ("Artifacts" — singular, no Web Search/Code
  Interpreter/File Search mentioned), then the top of the sidebar rail ("Your sidebar", naming all
  four icons), then the account-menu button ("Settings & files"), in that order. Reload again — it
  does not reappear. Clear `localStorage` again — it reappears. Click Next repeatedly — no visible
  flash/jump as the popover moves between anchors. Press Escape at any step — it closes and does not
  come back on reload. Tab through a step — focus cycles only among that step's Back/Skip/Next
  buttons. If ToS modal-acceptance is enabled in this environment, confirm the tour never appears
  until after Terms is accepted.
- **Not changing (decided, don't re-raise):** tour completion stays in `localStorage` (per browser,
  per device) — no cross-device/account-linked "seen" state. No "replay tour" affordance — Help &
  FAQ covers this.
- **Upstream status:** not submitted — fork-only feature, not a candidate for upstreaming.
- **Merge notes:** Mostly additive (new directory, one enum member, one mount line, one new
  `data-testid` prop on an existing sidebar component) — should not conflict on an upstream merge
  beyond a possible one-line conflict on `NavIconButton`'s `<Button>` props in `ExpandedPanel.tsx`.
  The main thing to re-check after any merge: confirm the four anchor selectors in `tourSteps.ts`
  still match real elements in whatever `AttachFileMenu.tsx`, `ToolsDropdown.tsx`,
  `ExpandedPanel.tsx`, and `AccountSettings.tsx` look like post-merge — this fork's sidebar was
  already redesigned once (`ExpandedPanel.tsx`, unified icon-strip layout) since this tour was first
  built, which is exactly the kind of drift these anchors are most exposed to.

### File Search toggle restored to tools menu; auto-enabled on every attach path

- **Work item:** PBI 12745
- **Added:** 2026-08-01 by Andrea Tiamson
- **Files touched:** `client/src/components/Chat/Input/ToolsDropdown.tsx`,
  `client/src/components/SidePanel/Files/PanelTable.tsx`,
  `client/src/hooks/Files/useDragHelpers.ts`
- **What:** Two independent fixes for the same underlying failure class (a user ends up with File
  Search silently off and no way back):
  1. **Re-added the File Search entry to `ToolsDropdown.tsx`** (`VectorIcon`, `useHasAccess(FILE_SEARCH)`,
     `fileSearchEnabled` from `useAgentCapabilities`, a `handleFileSearchToggle` callback, and a
     dropdown row with a pin button) — the exact shape PBI 12627 deleted. ⚠️ This originally read
     "now sitting next to Skills"; there is no Skills row in this deployment (`interface.skills:
     false` in `librechat.yaml`, and the row is gated on `canUseSkills && skillsEnabled` in
     `ToolsDropdown.tsx`). In practice File Search sits next to Artifacts, the only other surviving
     row — corrected 2026-08-04.
     `BadgeRowContext.tsx`/`useToolToggle.ts`/`FileSearch.tsx` (the input-row status chip) were never
     touched by 12627 and needed no changes here; the toggle/pin state they expose was simply
     unreachable from any UI once the menu row was gone. Restoring the row makes both toggling and
     pinning reachable again, so the chip in `FileSearch.tsx` (`fileSearchEnabled || isPinned`) can be
     dismissed and recovered instead of being a one-way door.
  2. **Attaching an already-uploaded file from the Files side panel now turns File Search on.**
     `PanelTable.tsx`'s `handleFileClick` calls `addFile({..., attached: true, ...})` but never touched
     the ephemeral-agent state; it now also calls
     `setEphemeralAgent((prev) => ({ ...prev, [EToolResources.file_search]: true }))` (same
     `ephemeralAgentByConvoId` atom family every other toggle/attach path reads and writes,
     keyed the same way — `conversation?.conversationId ?? Constants.NEW_CONVO`).
  3. **(Not in the PBI's acceptance criteria, added because it's the same bug class):** drag-and-drop's
     "Upload for File Search" option in `DragDropModal.tsx` routes through
     `useDragHelpers.ts`'s `handleOptionSelect`, which had an explicit
     `toolResource !== EToolResources.file_search` exclusion — comment: *"File search is not
     automatically enabled to simulate legacy behavior."* That meant picking the option literally
     labeled "Upload for File Search" did not enable File Search. Removed the exclusion; `file_search`
     is now enabled the same way `execute_code`/`context` already were on that path.
- **Why:** File Search's badge (`FileSearch.tsx`) only renders when `fileSearchEnabled || isPinned` —
  clicking it off makes the badge itself disappear, and pinning was only ever reachable from the
  tools-menu row PBI 12627 removed. Once both are gone, a user who toggles File Search off has no UI
  path back to it short of re-uploading a file (which forces it back on via the paperclip, but the
  paperclip's one-click flow only fires on a *new* upload, not on attaching a file that already
  exists). The Files-sidebar attach path independently never set `file_search` at all, so attaching
  a previously uploaded document could leave a conversation with the document attached but not
  searchable, with no error shown. Same silent-no-op class as PBI 12626, reached through different
  doors. No `librechat.yaml`/env-var surface governs tools-menu contents or per-attach-path ephemeral
  state, so this required source changes.
- **This deliberately reverses part of PBI 12627.** That PBI's acceptance criterion "the File Search
  toggle no longer appears in the +/tools menu" was reasonable on its own — the paperclip's one-click
  upload made the menu toggle *redundant for the upload case* — but it missed that the toggle was
  also the only way to turn File Search back on or pin the badge once it was off, with no other
  affordance introduced to replace either. Restoring the toggle is an intentional decision recorded
  here, not unfinished work on #12627; the paperclip still does not require pre-toggling File Search
  (unaffected by this patch), so #12627's actual goal (one-click upload) stands.
- **No regression check:** none of the three changes touch file-type validation. `PanelTable.tsx`'s
  existing `defaultFileConfig.checkType(...)` gate (endpoint `supportedMimeTypes`) runs unchanged
  before the new `setEphemeralAgent` call is reached; `AttachFileMenu.tsx`'s paperclip flow (already
  unconditionally setting `file_search: true` on click since the PBI 12627 patch, so it already met
  this PBI's paperclip acceptance criterion with no changes needed here) and the drag-drop
  modal's per-endpoint options are both untouched. Images are rejected on every upload path exactly
  as before.
- **How to verify:** Open the "+" tools menu — a "File Search" row appears with a checkbox-style
  toggle and a pin icon; toggling it flips the input-row badge; pinning it keeps the badge visible
  after toggling off. Upload a document via the paperclip, then use the new tools-menu toggle to turn
  File Search off, then back on (no re-upload) — ask about the document's contents and confirm a
  grounded answer. Open the Files side panel, click a previously-uploaded document's filename with
  File Search off beforehand — the tools-menu toggle (and badge, if pinned) flips on, and asking about
  that document's contents in the same conversation is grounded in it. Drag a document onto the chat
  window, choose "Upload for File Search" in the modal — File Search turns on immediately (previously
  it did not). Attempt to attach/upload a `.png` on each of the three paths — still rejected the same
  way it was before this patch (paperclip: file-type filter/toast; Files panel: `checkType` toast;
  drag-drop: image-only branch or rejection), confirming no regression there.
- **Upstream status:** not submitted — ROMTech-specific product decision (this fork's tools-menu
  contents and attach-path behavior), reversing another ROMTech-specific patch (#12627). Not a
  candidate for upstreaming.
- **Merge notes:** This patch's `ToolsDropdown.tsx` change is layered directly on top of the removal
  in the PBI 12627 entry above — if upstream's `ToolsDropdown.tsx` diverges further before the next
  merge, re-apply by re-adding the File Search row (this entry's exact block) rather than assuming
  the PBI 12627 entry's removal is still verbatim-reversible. `PanelTable.tsx` and `useDragHelpers.ts`
  are small, additive/removal-only diffs (one new hook call; one deleted `if` condition) and should
  merge cleanly unless upstream rewrites either file's attach logic, in which case re-locate the
  equivalent attach point and re-add the `setEphemeralAgent`/unconditional-enable call.

### Guided tour: model step, and dark-mode button colours

- **Work item:** product-owner request, 2026-08-05
- **Added:** 2026-08-05
- **Files touched:** `client/src/components/Onboarding/tourSteps.ts`,
  `client/src/components/Onboarding/TourPopover.tsx`,
  `client/src/components/Chat/Menus/Endpoints/ModelSelector.tsx`,
  `client/src/locales/en/translation.json`,
  `client/src/components/Onboarding/__tests__/GuidedTour.spec.tsx`,
  `client/src/components/Chat/Menus/Endpoints/__tests__/ModelSelector.tourAnchor.spec.ts` (new)
- **What:**
  1. **A fifth step covering model choice.** The tour never mentioned that there are two models.
     New step `model`, anchored on the model spec selector and placed **third** — after the two
     composer steps and before the sidebar — so the walk finishes the chat area before moving to
     the left rail. Copy names ROMChat Fast and ROMChat Standard, says every new chat starts on
     Fast, and gives a reason to switch rather than just naming the button.
     ⚠️ `placement: 'bottom'`, unlike the two `right` steps after it — the header anchor is
     left-aligned in a 52px bar, so `right` pushed a 300px popover off-screen on phones, and
     Radix's `shift` is `crossAxis: false`, so it would not have corrected it. See the comment in
     `tourSteps.ts`, which also records the ordering coupling with the sidebar step.
     ⚠️ The copy deliberately does **not** claim Standard helps with longer documents. Both specs
     are pinned to `maxContextTokens: 64000`, and document length is handled by File Search
     retrieval rather than the context window, so model choice does not affect it.
     `ModelSelector.tsx` gains `id="model-selector-button"` on both the `TooltipAnchor` and its
     render element, matching how upstream sets the other two tour anchors: the tour resolves
     anchors with `document.querySelector` and that component exposed no stable hook.
  2. **Dark-mode button colours.** Two different problems, worth keeping distinct:
     - **Next was a genuine WCAG failure.** `text-primary-foreground` resolves to `#171717` in
       dark mode against `bg-surface-submit` (`#047857`): **3.2:1** at rest and **2.3:1** on
       hover, both under AA for 14px text. Forced to white → 5.5:1 and 7.8:1. This is the half of
       the change that must survive an upstream merge.
     - **Back was legibility-fine but faceless.** It has no background of its own, so it took the
       popover's dark surface — light text on dark at ~16:1 with a border, perfectly readable, it
       just didn't look like a button. Inverted for dark using the `--primary` /
       `--primary-foreground` token pair. Purely aesthetic; don't let the wording above imply it
       was a contrast bug.
     Light mode is untouched in both cases — the tokens are already correct there.
- **Why:** Config can't add a tour step or restyle its buttons. The model step matters because
  `modelSpecs.enforce: true` with `interface.modelSelect: false` means that button is the *only*
  model control a user has, and nothing else in the product explains the Fast/Standard split.
- **How to verify:** Clear `guidedTourSeen`, reload, and walk the tour. Step 3 of 5 reads
  "Fast and Standard" and points at the model button in the chat header. In **dark mode**, Back is
  white with dark text and Next is green with white text; in light mode both are unchanged.
- **Upstream status:** not submitted. `Onboarding/` is ours; the only upstream file touched is the
  one-attribute id in `ModelSelector.tsx`.
- **Merge notes:** ⚠️ **If an upstream merge drops that id, nothing fails loudly.** The step is not
  simply "skipped": mid-tour a missing anchor costs 12 × 250ms of full-screen, click-blocking,
  backdrop with no popover on it — invisible in **dark** mode, where the backdrop is transparent
  (`TourBackdrop.tsx` is `bg-black/35 dark:bg-transparent`) — on every load, for every user, with
  no error and no telemetry. It also spends 12 of the 48-attempt whole-tour budget, which resets on
  the next success but leaves less margin if another anchor is slow on the same load. Realistically
  it presents as a silent three-second dead zone nobody notices until a user complains.
  `client/src/components/Chat/Menus/Endpoints/__tests__/ModelSelector.tourAnchor.spec.ts` guards
  the id for exactly this reason — `GuidedTour.spec.tsx` cannot, since it mounts its own stand-in
  anchor and stays green while the real app loses the step.
  **All five tour anchors live in upstream-owned files** — `#attach-file-menu-button`,
  `#tools-dropdown-button`, `#model-selector-button`, `#close-sidebar-button` (`OpenSidebar.tsx` /
  `ExpandedPanel.tsx`) and `[data-testid="nav-user"]` (`AccountSettings.tsx`). Only the model one
  has a guard; the other four are pre-existing and fail just as silently. Two of them we added, the
  rest we re-used, but the exposure is identical either way.
  The step's copy is config-dependent the same way steps 2 and 5 are (inserting this step made the
  sidebar step 4 and the account step 5): it describes exactly the two entries in
  `modelSpecs.list`, and "every new chat starts on Fast" holds because
  `prioritize: true` makes the default spec win over the last-selected one on every new chat.
  Changing `modelSpecs` means re-reading this string.
  ⚠️ Step count is asserted in `GuidedTour.spec.tsx` ("Step N of 5"), and the skip-path tests
  assume the model step follows Tools. Adding or reordering steps means updating those.

### Guided tour: step advance could render the previous step; backdrops stacked

- **Work item:** follow-up to PBI 12633 / 12746, from product-owner testing in dev
- **Added:** 2026-08-04
- **Files touched:** `client/src/components/Onboarding/useGuidedTour.ts`,
  `client/src/components/Onboarding/TourPopover.tsx`,
  `client/src/components/Onboarding/TourBackdrop.tsx`,
  `client/src/components/Onboarding/GuidedTour.tsx`,
  `client/src/components/Onboarding/tourState.ts` (new),
  `client/src/components/UnifiedSidebar/UnifiedSidebar.tsx`,
  `client/src/components/Onboarding/__tests__/GuidedTour.spec.tsx`
- **What:** Three faults, all reported as one symptom — *"step 3 points at the toggle options in
  the chat."*
  1. **Advancing a step could render the previous step under the new step's number.** `stepIndex`
     advances the moment Next is clicked, but `currentStep` was only reassigned once the new
     step's anchor was found in the DOM — and `TourPopover` fell back to `lastStepRef` whenever
     `step` was null. So while the retry loop hunted for a missing anchor, the popover rendered
     the *outgoing* step's copy at the *outgoing* step's anchor, while the footer read
     `stepIndex + 1`. Step 2's popover, sitting on the Tools button, labelled "Step 3 of 4", for
     up to the full 10s window before the step was skipped. Fixed by clearing `currentStep` when
     the step changes and deleting the fallback: the popover now shows the right step or nothing.
     On a normal transition this costs nothing — the anchor resolves in the same synchronous
     effect, so React batches both updates and no blank frame is committed. That guarantee is
     narrower than it sounds, though: the click sets `stepIndex` first, so React paints one frame
     carrying the new number before the effect runs. `GuidedTour` therefore derives the displayed
     number from the step actually on screen (`tourSteps.indexOf(currentStep)`) rather than from
     `stepIndex`, closing the remaining single-frame flash outright.
     Two things the deleted fallback had been covering incidentally, now handled directly:
     `TourPopover`'s Escape/Tab handler is **no longer gated on having a step** — otherwise the
     entire retry window ran with no Escape and no focus trap while the backdrop still swallowed
     clicks, so a keyboard user could tab into the blocked app and activate it. And `GuidedTour`
     stops rendering once the tour ends **including the `no-anchors` path**, which deliberately
     doesn't mark the tour seen: that path previously left the backdrop mounted indefinitely,
     which was a visible grey sheet before and would now be an invisible click-blocker over an
     app that looks entirely normal.
  2. **Step 3's anchor doesn't exist when the sidebar is collapsed on desktop.** `ExpandedPanel.tsx`
     assigns `CLOSE_SIDEBAR_ID` only while `expanded`, and `Sidebar.tsx` passes the real
     `expanded` through — so a desktop user who has ever collapsed the sidebar has no anchor, and
     `sidebarExpanded` is sticky in `localStorage`, so it stays that way. `GuidedTour` now expands
     the sidebar **while the sidebar step is the one being looked for**, then restores.
     ⚠️ Keyed on the *pending* step (`tourSteps[stepIndex]`), never on `currentStep`. `currentStep`
     is only assigned once an anchor resolves, so keying off it is circular — the anchor can't
     exist until the sidebar expands, and the sidebar wouldn't expand until the anchor existed, so
     the step silently timed out. That circularity shipped briefly and was caught in review; if
     this ever gets "simplified" back to `currentStep`, step 3 stops appearing for exactly the
     users it was fixed for.
     ⚠️ **Below 768px the mechanism is different**, and an earlier version of this entry had it
     wrong: `UnifiedSidebar.tsx`'s small-screen branch renders `<ExpandedPanel>` with **no**
     `expanded` prop, and the prop defaults to `true` (`ExpandedPanel.tsx:124`), so the id is
     always assigned there — collapsed or not, since the panel is merely translated off-screen.
     On mobile the pre-fix symptom was an anchor that *resolved to an off-screen rect*, so the
     popover appeared detached rather than absent. Same fix, different cause; don't try to
     reproduce the desktop mechanism at mobile widths.
     **The expansion is scoped to that one step deliberately.** Holding it open for the whole
     walk breaks steps 1 and 2 below 768px, where the sidebar is a `fixed` overlay up to 380px
     wide that covers the composer controls those steps anchor to.
     **The stored preference is protected.** `store.sidebarExpanded` is an `atomWithLocalStorage`,
     so setting it writes `unifiedSidebarExpanded` immediately, and React cleanup cannot undo
     that on a reload or tab close — anyone quitting mid-tour would have kept a permanently
     expanded sidebar. The effect rewrites the stored value back on the next tick and lets the
     in-memory atom carry the expansion, so only the live session is affected. The pre-tour value
     is captured from `localStorage` rather than from the atom, because a remount mid-step (which
     `Root.tsx`'s config/terms gating can cause) would otherwise capture the `true` we just set
     and make the expansion permanent.
     **Two limits worth knowing.** A user who deliberately collapses the sidebar *during* the
     sidebar step still gets it restored to the pre-tour value on exit — the tour can't tell that
     apart from its own expansion. And this only guards the sidebar preference; it is not a
     general "the tour never writes state" claim.
  4. **Retry windows: shorter mid-tour, and capped overall.** `ANCHOR_RETRY_MAX_ATTEMPTS` (40,
     ~10s) exists for the cold-load race, where the composer may still be mounting. Once any step
     has rendered the app is demonstrably up, so a missing anchor is genuinely missing —
     `ANCHOR_RETRY_MAX_ATTEMPTS_MID_TOUR` (12, ~3s) applies from then on, gated on `shownAnyStep`.
     The windows still compound, though: with nothing on the page, four steps at the cold-start
     window would hold a full-screen click blocker for ~40s — invisible in dark mode, Tab
     hard-blocked, no popover to explain it, and repeating on every load since `no-anchors`
     doesn't mark the tour seen. `ANCHOR_RETRY_MAX_TOTAL_ATTEMPTS` (48, ~12s) ends the tour
     instead. It counts **consecutive** failures and resets on every successful render, or normal
     use would drain it — see the Back handling below.
  5. **Back was a one-way valve, and could dismiss the tour for good.** Skipping a never-appearing
     step always incremented, so pressing Back onto a missing step blanked the popover, then
     bounced forward to the step just left — no way past it. Worse, each bounce spent 12 of the
     total budget, so four bounces ended the tour via `onEnd('finished')`, which marks it seen:
     mashing Back could permanently dismiss it. Skipping now follows the direction of travel
     (`direction` ref), and the budget resets on success.
  6. **Step 4's anchor lives inside the sidebar the tour had just closed.** `AccountSettings`
     (`[data-testid="nav-user"]`) renders inside `ExpandedPanel`. On desktop that stays on screen
     as a narrow rail when collapsed, but below 768px the whole panel is translated off-screen and
     `inert`. Scoping the expansion to the sidebar step meant collapsing exactly as step 4 began —
     and because `document.querySelector` ignores transforms the anchor still *resolved*, so there
     was no retry and no skip, just a popover pointing at something sliding out of view. Below
     768px the expansion now covers the account step too.
  7. **Two backdrops stacked.** Below 768px `UnifiedSidebar.tsx` renders its own `bg-black/50`
     scrim behind the expanded sidebar; under the tour's `bg-gray-600/65` / `dark:bg-black/80` that
     compounded to ~0.83 alpha in light and ~0.90 in dark, so the user couldn't see what the
     popover was pointing at — and fix 2 would have made it worse by expanding the sidebar. The
     sidebar's scrim is now suppressed while the tour runs (new `tourActiveState` atom — whose
     effect **must** clear it on unmount, or a logout or route change mid-tour strands it at true
     for the life of the `RecoilRoot`, which sits above the router; the scrim would then be
     permanently `pointer-events-none opacity-0`, so on mobile the sidebar opens with no dim and
     tap-outside-to-close is dead), and the
     tour's own backdrop drops to the minimum that still reads as modal: **`bg-black/35` in light,
     fully transparent in dark.** The asymmetry is deliberate — a bright page needs something to
     separate the popover from it, while dimming an already-near-black app only muddies it.
     ⚠️ **This pairing was reversed on 2026-08-05.** It first shipped the other way round (dim in
     dark, transparent in light) on a devtools comparison; seeing it in the deployed build showed
     the opposite was right. Both values are judgement calls made against the running app, not
     derived — if you find yourself "correcting" them back, check in the app first.
     Interaction stays blocked in both themes: an element with no background still receives pointer
     events, which is why `pointer-events-none` must never be added here.
     Note this is a first-run-visible surface in **both** themes: `ThemeProvider` defaults to
     `'system'` (`getInitialTheme`, no stored `color-theme` key), so a user whose OS is in dark
     mode meets the tour in dark on their first ever load.
- **Why:** Config can't reach any of this — it's component state and DOM anchoring. Fix 1 is the
  important one: a tour that confidently shows the wrong step is worse than no tour, and the
  failure is invisible in the environment most developers test in (desktop, sidebar expanded),
  which is exactly why it survived a live investigation that concluded "no code-level swap."
- **How to verify:** Clear `guidedTourSeen` from localStorage each time.
  1. **Desktop, sidebar collapsed** (the unanchored case): walk the tour. Step 3 shows "Your
     sidebar" pointing at the sidebar toggle — never step 2's copy on the Tools button. The
     sidebar opens for step 3 only, and returns to collapsed after Done or Skip.
  2. **Below 768px**: steps 1 and 2 must point at the composer with the sidebar **not** covering
     it; the sidebar appears for step 3, with a single backdrop, not two.
  2b. **Below 768px, step 4**: the sidebar must **stay open** through the account step — its
     anchor lives inside the panel, so if it collapses on the way in, the popover points at
     something sliding off-screen rather than failing visibly. Press Back from step 4 too; the
     sidebar should still be open on step 3.
  3. **Quit mid-tour on step 3, then reload**: `unifiedSidebarExpanded` in localStorage must
     still hold whatever it held before the tour.
  4. **During the anchor-hunt window** (easiest to force by removing `#tools-dropdown-button` in
     devtools, then pressing Next): Escape must still dismiss, and Tab must not reach the app
     behind the backdrop. With the same anchor removed, press **Back** repeatedly from step 3 —
     it must not bounce forward, and repeated presses must not end the tour.
  4b. **Escape below 768px on the sidebar step**: dismissing must not also collapse the sidebar
     and leave it in the wrong state.
  5. **Dark and light**: dark keeps a light dim, light is fully transparent, and clicks are
     swallowed in both.
- **Upstream status:** not submitted — `Onboarding/` is entirely ours; only the `UnifiedSidebar.tsx`
  scrim condition touches an upstream file.
- **Merge notes:** The `UnifiedSidebar.tsx` change is two lines (a `useRecoilValue` and a condition)
  and is the only conflict surface. If upstream reworks that scrim, the requirement is simply:
  don't render a second full-screen overlay while `tourActiveState` is true.

### Guided tour becomes modal — dimmed backdrop, blocked interaction, speech-bubble tail

- **Work item:** PBI 12746 (builds on the "First-run guided tour" patch above, PBI 12633)
- **Added:** 2026-08-01 by Andrea Tiamson
- **Files touched:** `client/src/components/Onboarding/TourBackdrop.tsx` (new),
  `client/src/components/Onboarding/GuidedTour.tsx`,
  `client/src/components/Onboarding/TourPopover.tsx`,
  `client/src/components/Onboarding/__tests__/GuidedTour.spec.tsx`
- **What:** Two fixes to the tour's original non-modal Radix Popover:
  1. **Dimmed, click-absorbing backdrop.** ⚠️ *The dim was removed on 2026-08-04 — see the entry
     above; the backdrop is now transparent and blocks clicks only.* As originally written: new
     `TourBackdrop.tsx` portals a single
     `fixed inset-0 z-[9998]` dim div (`bg-gray-600/65` / `dark:bg-black/80` — the same tokens
     `@librechat/client`'s `Dialog.tsx` overlay uses) straight to `document.body`. It is rendered
     by `GuidedTour.tsx` itself (`ready && !seen`), as a sibling of `TourPopover`, not by
     `TourPopover` — `TourPopover` unmounts/remounts on the brief frames where `currentStep` goes
     `null` while `useGuidedTour` skips a step whose anchor is missing, and mounting the backdrop
     there would flicker it off and back on every such skip. No click handler is needed to
     "block" anything: the div's z-index puts it above the whole app in the paint order, so the
     browser's own hit-testing resolves any click inside the viewport to the backdrop, not to
     whatever app control is under it — including the spotlighted anchor itself, per the decision
     to block interaction entirely rather than build a click-through cutout. The popover content
     (`z-[9999]`) stays above the backdrop and remains fully interactive.
  2. **Speech-bubble tail.** Added `Popover.Arrow` (from `@radix-ui/react-popover`, a sibling of
     the existing `Popover.Content`) styled `fill-surface-primary stroke-border-medium` to match
     the bubble's own background/border. Deliberately left to Radix's own positioning rather than
     derived from `step.placement`: Radix recomputes both the content's side/align *and* the
     arrow's offset/rotation together whenever its collision detection flips the popover to fit
     the viewport, so the tail keeps pointing at the true anchor at any width without any
     width-specific logic here.
  - **`aria-modal="true"`** added to both `Popover.Content` and the inner `role="dialog"`
    `motion.div` (kept on both since assistive tech may key off either the Radix-owned outer
    dialog role or the inner one this component already had). The existing hand-rolled Tab trap
    (`TourPopover.tsx`'s `handleKeyDown`) was not touched — it already contained keyboard focus;
    the gap was strictly the mouse/pointer path and the missing modal announcement.
  - **Not built:** a spotlight cutout around the anchor. Per the PBI's open sub-question, the
    plain dim was chosen over a cutout that tracks the anchor's box through scroll/resize — the
    speech-bubble tail already gives the visual connection to the target that a cutout would
    otherwise provide, at a fraction of the complexity, and the PBI's own guidance was to prefer
    plain dim unless it tests poorly. Revisit if user feedback says the plain dim doesn't read as
    clearly as the tail was expected to.
  - **Not attempted here:** the separate step-transition flash reported as feedback T3 against
    #12633. Keeping the backdrop mounted across step transitions (rather than remounting per step)
    removes one possible source of that flash as a side effect of fix #1 above, but this patch
    does not claim to close T3 — no `#12633`-specific flash reproduction or fix was verified here.
- **Why:** The tour previously had no overlay at all — `TourPopover.tsx` was a plain non-modal
  `Popover.Root` with only `onPointerDownOutside`/`onInteractOutside` `preventDefault`s, which stop
  Radix's own auto-close behavior but never stop a real click from reaching whatever DOM element is
  under the cursor (Radix's outside-interaction callbacks don't call the clicked element's own
  handler). A first-time user could click straight through the tour into the live app mid-walk.
  Separately, the popover floated near its anchor with no visual link to it, so which control a
  given step described was left to proximity/guesswork. No `librechat.yaml`/env-var surface governs
  onboarding UI, so this required source changes to fork-only files (not upstream's).
- **How to verify:** Clear `localStorage`, reload. On step 1: the page behind the tour is visibly
  dimmed, and clicking any app control behind the dim (e.g. the sidebar, a nav item) does nothing —
  focus and app state don't change. The popover has a visible triangular tail touching the dimmed
  page and aimed at the paperclip. Resize the window to a narrow (mobile-width) viewport mid-tour —
  the tail still visibly touches its anchor (Radix may have flipped the side; the tail follows).
  Step through all 4 steps (paperclip, tools button, new-chat button, account button) at both a
  wide and a narrow viewport — the tail points at the correct element every time, and the dim never
  flickers off/on between steps. Inspect the popover in devtools' accessibility tree: it reports as
  a dialog with `aria-modal: true`. Tab from the primary button — focus still cycles only within
  Back/Skip/Next as before (unchanged trap). Press Escape — the tour closes, the dim is completely
  gone (inspect `document.body` for a stray full-screen div — none should remain), and every app
  control is immediately clickable. Click Skip — same result. Reload after either — the tour does
  not reappear; clear `localStorage` — it does. Unit side:
  `cd client && npx jest src/components/Onboarding/__tests__/GuidedTour.spec.tsx` (17/17, including
  new backdrop-presence, backdrop-removal, and `aria-modal` assertions). Real-browser/visual checks
  (dim opacity, tail alignment/rotation at both viewport widths, no residual overlay) were not
  run against the deployed app as part of this change — do that before sign-off, since Radix's
  Popper positioning and the arrow's collision-driven rotation aren't meaningfully exercised by
  jsdom (no real layout/paint), only their DOM structure and ARIA attributes are.
- **Upstream status:** not submitted — fork-only onboarding feature (same status as the PBI 12633
  patch it modifies), not a candidate for upstreaming.
- **Merge notes:** Purely additive/behavioral on top of files that are themselves fork-only
  (`client/src/components/Onboarding/*` doesn't exist upstream), so this should never conflict with
  an upstream merge — only re-check it if the PBI 12633 patch's anchor selectors or file layout
  change first. If `#12633`'s separate step-transition-flash fix (feedback T3) lands and also
  touches `TourPopover.tsx`/`GuidedTour.tsx`, reconcile rather than assuming a conflict means "keep
  ours" — the two fixes are explicitly meant to compose (see "Not attempted here" above).

<!-- new entries go here -->

### Configurable SameSite on the login session cookie

- **Work item:** ROMTech Staff App — architecture assistant (embedded ROMChat)
- **Added:** 2026-08-25 by Jack Stanley
- **Files touched:** `packages/api/src/oauth/csrf.ts`, `packages/api/src/oauth/csrf.spec.ts`, `api/server/socialLogins.js`
- **What:** Adds `sessionCookieSameSite()` beside the existing `shouldUseSecureCookie()`, reading a new
  optional `SESSION_COOKIE_SAME_SITE` env var, and spreads its result into the OpenID **and** SAML session
  cookie options. Unset — the default, and what every current deployment has — returns `undefined` and leaves
  express-session's behaviour byte-identical.
- **Why:** ROMChat is being embedded as an iframe in the ROMTech Staff App's Integrations Diagram page. The
  iframe is served from a different site (`*.azurecontainerapps.io` inside `*.azurewebsites.net`), so
  `connect.sid` — which has no SameSite attribute and is therefore treated as `Lax` — is never sent on the
  cross-site request. The OIDC state written before the Okta redirect cannot be read back at the callback, and
  login fails with an opaque `Error in OAuth authentication: Unknown OAuth error`. Config could not do it:
  there is no existing env var for the session cookie's SameSite, which is why this is a patch rather than a
  setting. Everything else about the deployment was verified correct first — client secret (Okta returns
  `invalid_grant`, not `invalid_client`), redirect URI (matches character for character), and
  `DOMAIN_SERVER`.
- **How to verify:** In a deployment with `SESSION_COOKIE_SAME_SITE=none` and a Secure cookie, request any
  page and inspect the response: `set-cookie: connect.sid=...; SameSite=None; Secure`. Without the variable
  the same request must show **no** SameSite attribute at all — that absence is the regression test for every
  existing ROMChat deployment. `none` is deliberately ignored when the cookie would not be Secure, because
  browsers reject that combination outright and a dropped cookie is harder to diagnose than the default.
- **Upstream status:** not submitted — worth upstreaming; it is small, additive and generally useful to
  anyone embedding LibreChat.
- **Merge notes:** Sits directly beside upstream's `shouldUseSecureCookie()` in `oauth/csrf.ts` and follows
  its `SESSION_COOKIE_SECURE` convention, so it should read as native code at merge time. The
  `socialLogins.js` change is three lines inside two `cookie: {}` literals that upstream touches
  occasionally (last: PKCE #12364, admin-auth #12472) — expect conflicts there, not in the helper. **Drop this
  patch entirely** if upstream adds any SameSite control of its own; the env var name is ours, so prefer
  upstream's spelling over keeping this.


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

### Content-filter rejections show generic copy, not the raw LiteLLM/Azure error

- **Work item:** 12941
- **Added:** 2026-08-07 by Ian Tristan, revised the same day after review
- **Files touched:** `packages/data-provider/src/config.ts`,
  `packages/api/src/utils/azure.ts`,
  `packages/api/src/utils/azure.spec.ts`,
  `api/server/middleware/abortMiddleware.js`,
  `api/server/middleware/abortMiddleware.handleAbortError.spec.js` (new),
  `api/server/controllers/agents/client.js`,
  `client/src/components/Messages/Content/Error.tsx`,
  `client/src/locales/en/translation.json`
- **What:** When Azure's content filter rejects a prompt, the raw LiteLLM exception was rendered
  verbatim in the chat bubble — including our internal model group names (`ROMTech AI Fast`,
  `ROMTech AI Fast Backup`), the whole `fallbacks=[...]` routing table, and the
  `content_filter_result` payload. Four additive pieces replace it with one sentence:
  1. `ErrorTypes.CONTENT_FILTER = 'content_filter'` added to the enum (`config.ts:2059`).
  2. New `isAzureContentFilterError()` (`azure.ts:168`) — a detector, exported through
     `@librechat/api`. It prefers Azure's **structured** fields (`code === 'content_filter'`,
     `innererror.code === 'ResponsibleAIPolicyViolation'`, or a `content_filter_result` object on a
     400), then falls back to three **fixed** string markers (`azure.ts:153`):
     `ContentPolicyViolationError`, `ResponsibleAIPolicyViolation`, `content management policy`.
     Those three are hardcoded in Azure OpenAI and LiteLLM themselves, so they are stable across
     environments — deliberately **not** model or model-group names, which are `librechat.yaml`
     config and differ per env.
  3. Both server leak paths substitute `{"type":"content_filter"}` for the error text:
     `handleAbortError()` (`abortMiddleware.js:225`) and `AgentClient.sendCompletion()`'s own catch
     (`client.js:1129`). **Two patches, not one, and the second is the one that actually fires for
     our chats** — see "Why both" below.
  4. Client maps the new type to `com_error_content_filter` (`Error.tsx:40`) with the copy
     *"I'm unable to assist with requests that violate our content policies. Please modify your
     prompt and try again."*
- **Why a new `CONTENT_FILTER` rather than reusing `MODERATION`:** different producer, different
  stage, different remedy. `ErrorTypes.MODERATION` comes from `moderateText.js`, LibreChat's own
  pre-flight moderation middleware — our code, before the request leaves us. `CONTENT_FILTER` is
  the upstream provider rejecting a request we already sent. Collapsing them would make a local
  pre-flight block indistinguishable from a provider rejection in logs and telemetry, and would
  force one string to serve both — `com_error_moderation` talks about "our community guidelines",
  which is wrong for a provider-side filter. Two near-identical enum members look like a mistake;
  they aren't. Don't merge them.
- **Why the string-marker fallback exists (the non-obvious part):** the structured checks alone
  do **not** catch our production case. LiteLLM's router retries the configured
  `content_policy_fallback` chain first; once every fallback is exhausted it re-wraps everything
  into a single flattened `litellm.BadRequestError: litellm.ContentPolicyViolationError: ...`
  message string, and Azure's original `code` / `innererror` / `content_filter_result` fields are
  **gone** by the time the error reaches us. A structural-only detector returns `false` and the raw
  dump goes straight through — which is exactly what happened on the first attempt at this fix.
- **Why both server paths:** `handleAbortError()` only runs for request-level failures. A
  content-filter rejection mid-generation is caught by `AgentClient.sendCompletion()`'s own
  try/catch, which pushes `err.message` into a `ContentTypes.ERROR` content part — bypassing
  `abortMiddleware` entirely. That second path is the one custom-endpoint (LiteLLM Gateway) chats
  actually take, so patching only `abortMiddleware` looks correct and fixes nothing.
- **⚠️ Revised after review: the leak is closed for ALL errors, not just content-filter ones.**
  The first version sanitised the content-filter case and left every other upstream failure
  interpolating `err.message` into user-visible text. That is not a safe boundary here: LiteLLM
  formats its rate-limit, auth and deployment errors with the *same* envelope as the
  content-filter one — model-group names, the full `fallbacks=[...]` table, backup deployment
  names — and 429s during busy periods and 401s during key rotation are far more common than
  policy rejections. Both call sites now emit a generic string for anything they cannot classify,
  and the detail is still logged server-side, so support keeps full visibility.
  `handleAbortError()` additionally no longer forwards an upstream body just because it contains
  the substring `"type"`: LiteLLM's OpenAI-style proxy envelope matched that test, and since it
  carries no *top-level* `code`/`type`, `Error.tsx` failed to map it and printed the raw body
  after "Something went wrong. Here's the specific error message we encountered:". The check is
  now anchored to our own `{"type": ...}` payloads.
- **Deliberately NOT patched:** the same raw-`error.message` pattern exists in
  `api/server/controllers/assistants/chatV1.js:202` and
  `api/server/controllers/assistants/errors.js:146`. Both are on the OpenAI **Assistants** flow,
  which no environment configures (`ENDPOINTS=custom`, no `assistants`/`azureAssistants` endpoint,
  enforced `modelSpecs` → everything routes through the LiteLLM Gateway custom endpoint), so they
  are unreachable and were left alone to keep the patch small. **If Assistants is ever enabled,
  these two leak the same way** and need the same treatment.
- **Why config couldn't do it:** no `librechat.yaml` or env-var surface controls error-message
  text. `interface.customWelcome` and friends cover static copy only; the error string is built in
  server code and consumed by a client component keyed on `ErrorTypes`. LiteLLM's own
  `content_policy_fallback` is also not a substitute — it changes *routing*, not what the user is
  shown once routing gives up.
- **Existing behaviour preserved:** the `INVALID_REQUEST`, `NO_SYSTEM_MESSAGES`, and moderation
  branches are untouched. The new `abortMiddleware` check is ordered **after** the existing
  `INVALID_REQUEST` branch on purpose: Azure content-filter errors also carry
  `type: "invalid_request_error"`, so checking first would let the generic branch overwrite the
  sanitised text. There is a regression test for exactly that ordering.
- **⚠️ The soft marker is anchored on purpose.** The message scan matches
  `"Azure OpenAI's content management policy"`, not the bare words `content management policy`.
  Upstream errors routinely quote request context back — context-length errors quote the
  offending messages, guardrail and proxy errors echo params — so the unanchored form would
  report a benign failure to the user as a policy violation. That is the worse direction to be
  wrong in, and it is reachable without any cooperation from our own code. The other two markers
  are vendor identifiers that cannot appear by accident. There is a regression test for exactly
  this (a context-length error quoting a user asking about a content management policy).
- **The scan covers nested message shapes.** LiteLLM's proxy puts the human-readable text at
  `error.message`; whether it is hoisted to a top-level `message` depends on which client layer
  wrapped it. Checking only the top level would silently drop back to the raw dump after a
  LiteLLM upgrade, so `error.message` and `response.data.error.message` are checked too.
- **Known gap (pre-existing, not introduced here):** `handleAbortError()` returns early via
  `abortMessage()` when there is partial text, discarding `errorText`. An OUTPUT-side filter
  tripping mid-stream therefore shows the truncated partial with no error at all — and output
  filtering is the case most likely to have partial text. Not addressed in this patch.
- **How to verify:** ⚠️ **rebuild and restart in the right order first, or you will "verify" stale
  code.** `nodemonConfig.ignore` includes `packages/`, so a `packages/api` rebuild does *not*
  restart the backend: run `npm run build:data-provider && npm run build:api`, **then** restart the
  backend, and confirm the server process started *after* the `dist` write time. Then in a chat,
  send a prompt that trips Azure's filter. Expect the single sentence above — and grep the rendered
  bubble for `ROMTech`, `fallbacks=`, `litellm`, `content_filter_result`: **zero hits**. Confirm the
  full raw error is still in the server log (ops visibility is intentional; only the client text is
  sanitised). Note the client bundle matters too: on `:3080` a stale `client/dist` lacks
  `com_error_content_filter` and will render `{"type":"content_filter"}` instead of the copy (no
  leak, wrong text) — use `:3090` (Vite HMR) or `npm run build:client`. Unit side:
  `cd packages/api && npx jest src/utils/azure.spec.ts` (31/31, includes the real flattened
  production message) and `cd api && npx jest server/middleware/abortMiddleware` (12/12, includes
  the three no-regression cases).
- **Not yet done at the time of writing:** manual regression of the three pre-existing error types
  (invalid request, no-system-messages, moderation-flagged) in the running app — they are covered by
  unit tests only. The PBI's DoD asks for a manual pass on those before QA sign-off.
- **Upstream status:** not submitted — **good upstreaming candidate.** Leaking a raw provider
  exception into the chat bubble is an upstream bug, not a ROMTech-specific need; only the copy is
  ours. If upstream adds native content-filter handling, **drop this patch** and keep only the
  localisation string.
- **Merge notes:** All four pieces are additive — a new enum member, a new exported function, one
  new `if` in each of two error handlers, one new map entry — so conflicts should be small and
  resolvable by re-adding rather than reasoning. **The fragile piece is
  `CONTENT_FILTER_MESSAGE_MARKERS`:** it depends on LiteLLM's exception class name and Azure's
  compliance sentence staying byte-identical. If content-filter errors ever start rendering as the
  raw dump again after a LiteLLM upgrade, check those three strings first — that is the failure
  mode. Re-check `client.js`'s catch block on every upstream merge: if upstream refactors
  `sendCompletion`'s error handling, the `isAzureContentFilterError` guard must move with it, and
  losing it silently restores the leak with no test failure in `/api` to catch it.

### Assistant message icon invisible in light mode

- **Work item:** 13121
- **Added:** 2026-08-12 by Behnam Bozorgi
- **Files touched:** `client/src/components/Endpoints/MessageEndpointIcon.tsx`
- **What:** Added `text-text-primary` to the `className` on the `UnknownIcon` in the map's
  `default` entry. The same class is also set on the `custom` entry's `CustomMinimalIcon`, but see
  the caveat below — that branch is dead code for us and is a guard only.
- **Why:** The bot glyph beside the assistant's name did not appear in light mode. It was rendering
  the whole time, in white. Three upstream facts combine: the entry ROMChat actually hits supplies
  no `bg`, so the shared wrapper falls back to `background: 'transparent'`; that same wrapper
  hard-codes `text-white`; and the glyph is stroked with `currentColor`. White strokes on a
  transparent background read fine against dark mode's page and vanish against light mode's. Every
  other endpoint in the map sets a `bg` — Azure a gradient, OpenAI a computed colour, Anthropic
  `#d09a74`, Bedrock `#268672` — so white-on-a-tile is right for them. Setting the colour on the
  icon itself beats the inherited `text-white`, and `--text-primary` already resolves per theme
  (`gray-800` light, `gray-100` dark), so no `dark:` variant is needed and the icon matches the
  message title beside it, which uses the same token.
- **⚠️ Which branch actually renders — the non-obvious part.** `endpointIcons` is keyed on the **raw
  endpoint string**, and a *named* custom endpoint carries its **name**, never the literal
  `"custom"` — `custom` is only its `type` (`packages/api/src/endpoints/custom/config.ts`:
  `customEndpointsConfig[name] = { type: EModelEndpoint.custom, … }`). ROMChat's endpoint is named
  `"LiteLLM Gateway"`, and both modelSpecs pin `endpoint: "LiteLLM Gateway"`, so that string is what
  reaches the message. `getIconEndpoint` never substitutes the type. So `endpointIcons["LiteLLM
  Gateway"]` is undefined, the lookup falls to `default` → `UnknownIcon` → no matching
  `knownEndpointAssets` entry → `CustomMinimalIcon` again. **Same glyph, different line**, which is
  why fixing the `custom` entry alone looks identical in a screenshot and changes nothing. The rest
  of the codebase writes `endpointType ?? endpoint` where it needs the type; this map does not, and
  `MessageIcon` never passes `endpointType`.
- **Why config was rejected, not impossible.** Fork rule 2 prefers config, so this was checked
  properly: setting `iconURL` on the custom endpoint in `librechat.yaml` **would** fix the main chat
  view, because the `default` branch does honour it (`UnknownIcon` renders `<img src={iconURL}>`
  before reaching the glyph). It does **not** fix the shared-conversation view —
  `client/src/components/Share/MessageIcon.tsx` calls `getIconEndpoint` with
  `endpointsConfig: undefined` and passes only the avatar URL, so shared links fall through to the
  uncoloured glyph regardless. Config would fix one surface and leave the other broken, so the
  patch covers both.
- **How to verify:** In light mode, send any message and look at the bot glyph to the left of the
  response's name — it must be dark grey and clearly visible against the page. Switch to dark mode
  and confirm it is still visible (near-white). Then open a shared conversation link and check the
  same glyph there, since that view reaches this component by a different route. To confirm *which*
  branch rendered, inspect the glyph: the `default` branch wraps it in the `h-6 w-6` /
  `overflow-hidden rounded-full` div pair.
- **Not affected, deliberately:** `client/src/components/Endpoints/MinimalIcon.tsx` renders the same
  glyph and has the same keying flaw (its `custom` entry is equally unreachable, so ROMChat gets its
  `default` → `UnknownIcon` branch), but its wrapper uses `text-text-secondary`, which is already
  theme-aware. No bug there; left alone.
- **Upstream status:** not submitted — this is an upstream bug, not a ROMTech preference, and it hits
  anyone running a named custom endpoint in light mode. Good upstreaming candidate, ideally together
  with the keying flaw. If either merges, revisit this patch.
- **Merge notes:** Sits in the `endpointIcons` map, which upstream edits whenever it adds a provider
  (`GPT-5.1`, `o4-mini` and the 2026 UI refresh all touched this file). A conflict is likely and the
  resolution is trivial: keep upstream's map, re-add `text-text-primary` to the `default` entry's
  `UnknownIcon` className. **Two things would make this patch wrong rather than merely redundant:**
  (1) upstream keying the map on `endpointType ?? endpoint`, which makes the `custom` branch live —
  that is exactly what the guard on the `custom` entry is for, so keep both classes in sync; and
  (2) upstream giving the `default` entry a `bg`, which would put a dark glyph on a coloured tile —
  in that case drop the class and let `text-white` apply again. Do **not** "simplify" this by giving
  `default` a `bg` instead: that branch also serves endpoints whose logos render as `<img>` from
  `knownEndpointAssets`, so a tile would land behind DeepSeek/Ollama/Mistral logos too.

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
