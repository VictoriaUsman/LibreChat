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

This fork was previously at **zero source patches** — an unmodified upstream `v0.8.6` (fork commit
`566e20b6`) plus our own `azure-pipelines.yml`. A build of exactly that tree was deployed to dev on
2026-07-28 and behaved identically to upstream's published image, which is how we proved the
build/deploy path before taking on any source risk.

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
- **Added:** 2026-07-30 by Andrea Tiamson
- **Files touched:** `packages/data-provider/src/file-config.ts`, `client/src/utils/files.ts`,
  `client/src/hooks/Files/useFileHandling.ts`,
  `client/src/components/Chat/Input/Files/AttachFileMenu.tsx`,
  `client/src/components/Chat/Input/ToolsDropdown.tsx`, `client/src/locales/en/translation.json`,
  `client/src/components/Chat/Input/Files/__tests__/AttachFileMenu.spec.tsx`
- **What:** Collapsed the paperclip from a dropdown (Upload Image / OCR text / code environment /
  File Search / SharePoint) into a single one-click File Search uploader — no other upload modes
  remain on the paperclip. Clicking it directly opens the OS file picker pre-filtered to PDF/Word/
  Excel/PowerPoint/text (new `fileSearchDocumentExtensions` constant in `file-config.ts`), always
  tags the upload with `EToolResources.file_search`, and sets
  `ephemeralAgent[file_search] = true` itself — removing the need to pre-toggle File Search in the
  "+" tools menu first. Added a matching `fileSearchDocumentMimeTypes` allowlist and a new branch in
  `validateFiles()` (`client/src/utils/files.ts`) so a file that slips past the OS filter (e.g. a
  `.png` picked via "All files") is validated against the document-only list, not the endpoint's
  broad general allowlist — otherwise it would silently pass and upload as a non-indexed attachment,
  the same failure mode PBI 12626 already fixed once, just recreated at this new entry point. Added
  an `onError` reset of `ephemeralAgent[file_search]` back to `false` in `useFileHandling.ts`,
  mirroring the existing `execute_code` reset, so a failed upload doesn't leave file_search "on" for
  a turn with no file behind it. Removed the File Search toggle from `ToolsDropdown.tsx` (and its
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
- **Why:** Enabling File Search required two separate, easy-to-miss decisions (toggle in "+" menu,
  then the right dropdown item) before any upload did what the user expected. No
  `librechat.yaml`/env-var toggle governs individual attach-menu behavior, so this required a source
  change.
- **How to verify:** Click the paperclip — the OS file picker opens immediately (no dropdown),
  tooltip reads "Upload a document (PDF, Word, Excel, PowerPoint, text)", and the file type filter is
  restricted to those types. Upload a `.pdf`/`.docx` and ask a question about its contents in the
  same conversation without touching any other control — expect a grounded answer. Open the "+"
  tools menu — no File Search toggle appears. Pick a `.png` via "All files" in the OS dialog — expect
  a toast error and nothing attached. Disconnect network mid-upload — expect a toast error and no
  partial file left in the composer. Tab to the paperclip and press Enter/Space — it activates.
- **Upstream status:** not submitted
- **Merge notes:** This patch depends on the PBI 12626 patch above landing first in the same file
  (`AttachFileMenu.tsx`) to avoid a guaranteed conflict; resolve 12626 first, then re-apply this one.
  Upstream's `AttachFileMenu.tsx` will still have the full dropdown (Upload Image/OCR/code/File
  Search/SharePoint) and `ToolsDropdown.tsx` will still have the File Search toggle — expect conflicts
  in both. Re-apply the one-click single-button version of `AttachFileMenu.tsx` and the toggle
  removal in `ToolsDropdown.tsx`, unless upstream has shipped an equivalent one-click file-search
  entry point, in which case this patch (and possibly the SharePoint/OCR/code-upload removal
  specifically) should be reconsidered — this fork traded those modes away deliberately for
  simplicity, which upstream may not have.

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
