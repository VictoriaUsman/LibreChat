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
- **⚠️ This is a raster embedded in an SVG wrapper, not a true vector.** The approved mark was only
  ever supplied as a 512x512 PNG; no vector master exists yet. Rather than hand-trace the "RC"
  letterforms — which would approximate the brand typography and risk distorting it — the PNG is
  embedded verbatim as a base64 data URI inside an SVG with the correct viewBox. The embedded bytes
  are identical to the master (sha256-verified), so there is no recompression loss.
- **Why this is acceptable here:** `AuthLayout.tsx:65` renders the logo inside `h-10` (40px tall)
  with `object-contain`, so the displayed size is ~40px — 512px of source is ample even at 3x DPI
  (120px). The file is 30KB vs upstream's 5.8KB, loaded on the login page only.
- **When a real vector arrives, replace this file.** Nothing else needs to change: same path, same
  filename, same viewBox. That swap is the entire follow-up, tracked as
  **ADO WI # 12687** (*Replace the raster ROMChat logo with a true vector master*), which is blocked
  on the owner supplying a vector master — it cannot be derived from the 512x512 PNG. Closing 12687
  also means deleting this bullet and the raster-debt warning above it.
- **How to verify:** Open `/login`. The ROMChat bubble monogram appears above the login card, not
  LibreChat's logo. No 404 for `assets/logo.svg`; it serves as `image/svg+xml`.
- **Upstream status:** not submitted — ROMTech-specific, permanent.
- **Merge notes:** Upstream rarely touches this file, but if it does, resolution is
  `git checkout --ours` — their logo is never what we want. Do not "fix" the embedded data URI by
  converting it to `<path>` data unless you have the genuine vector artwork; a trace is not the mark.

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
     dropdown row with a pin button) — the exact shape PBI 12627 deleted, now sitting next to Skills.
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

### Guided tour becomes modal — dimmed backdrop, blocked interaction, speech-bubble tail

- **Work item:** PBI 12746 (builds on the "First-run guided tour" patch above, PBI 12633)
- **Added:** 2026-08-01 by Andrea Tiamson
- **Files touched:** `client/src/components/Onboarding/TourBackdrop.tsx` (new),
  `client/src/components/Onboarding/GuidedTour.tsx`,
  `client/src/components/Onboarding/TourPopover.tsx`,
  `client/src/components/Onboarding/__tests__/GuidedTour.spec.tsx`
- **What:** Two fixes to the tour's original non-modal Radix Popover:
  1. **Dimmed, click-absorbing backdrop.** New `TourBackdrop.tsx` portals a single
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
