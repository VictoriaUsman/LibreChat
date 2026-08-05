# LibreChat image — what's deployed, and how to change it

ROMChat runs **our own build** of LibreChat, from the fork repo
**`ChatGptForEmployeesLibreChatFork`**, pinned by **immutable digest** (never a mutable tag).

This document is the **promotion log**: which build is in which environment, since when, and what's
in it. Update it **in the same PR** as the `libreChatImage` change it describes — that's what keeps
it from drifting out of sync with reality.

---

## Current state

| Env | Image | Since | Fork commit | Notes |
|---|---|---|---|---|
| **Dev** | `acrcgfedev.azurecr.io/librechat@sha256:7f4b246df2d70f6c8ee93026e4f27e5cee310b8305b847fbef4e2cbd422e612c` | 2026-08-05 | `a4e71a966` | Tour model step + dark-mode button colours. ACR tag `26023`. |
| **Test** | `acrcgfetest.azurecr.io/librechat@sha256:7f4b246d…22e612c` | *staged* | `a4e71a966` | Set in `dev`; **deploys when `dev` → `test` promotes.** Image imported automatically by `test.yml`. |
| **Prod** | `acrcgfeprod.azurecr.io/librechat@sha256:7f4b246d…22e612c` | *staged* | `a4e71a966` | Set in `dev`; **deploys when `test` → `main` promotes.** Image imported automatically by `prod.yml`. |

> **ACR tags differ between registries.** The `Since`/`ACR tag` values above are the *dev* build's
> tag, assigned by the fork pipeline. The copy into test and prod tags the same manifest with the
> first 12 hex characters of its digest instead, so `az acr repository show-tags` will disagree
> across registries. The **digest** is identical everywhere, and the digest is what deploys.
>
> **This table is a convenience, not the source of truth.** The authoritative record is
> `ChatGptForEmployees.bicep/main.<env>.bicepparam` — that file is what actually deploys. To see what
> is *genuinely* running right now, query Azure (§4).

---

## History

Newest first. One entry per image change per environment.

### 2026-08-05 — Dev — `sha256:7f4b246d…22e612c`

- **Fork commit:** `a4e71a966` (fork `main` after PR 11602) · **ACR tag:** `26023` · **arch:** amd64
- **What's in it:** a fifth guided-tour step covering model choice — ROMChat Fast vs Standard,
  anchored on the model spec selector and placed third, so the walk finishes the chat area before
  moving to the left rail. Plus two dark-mode button fixes in the tour popover: Next was
  `#171717` on the green submit surface, **3.2:1 at rest and 2.3:1 on hover — both below WCAG AA**
  for 14px text, now white at 5.5:1 and 7.8:1; and Back, which had no background of its own and so
  took the popover's dark surface, now uses the inverted `--primary` token pair.
- **Paired infra change:** none beyond this digest bump.
- ⚠️ **This deploy initially did not happen.** The PR bumped `DEPLOY_TRIGGER` 2 → 3, which we then
  believed was required; `BicepCreate` was Skipped anyway and dev kept serving `25780`. That is
  what finally disproved the counter and led to the real cause and fix in §5. The digest below
  reached dev only after `bicepDetectFolder: ''` landed.
- **Verified before deploy:** digest present in `acrcgfedev` (`az acr repository show`), linux/amd64,
  tag `26023`, built 2026-08-05 14:29 UTC.
- **Not covered by automated tests:** the client suite has still not been run against any build in
  this series. This one adds a step to the tour and a new `ModelSelector.tourAnchor.spec.ts` guard,
  neither executed. Highest-value manual check is **step 3 at phone width in dark mode**, where the
  new step's placement, the button colours, and the transparent-in-dark backdrop all land together.
- **Rollback:** restore `sha256:308082f9…1f137468` and redeploy — still in the registry.

### 2026-08-04 — Dev — `sha256:308082f9…1f137468`

- **Fork commit:** `84ad8d651` (fork `main` after PR 11560) · **ACR tag:** `25780` · **arch:** amd64
- **What's in it:** two corrections after seeing tag `25740` running in dev. The tour backdrop's
  dim moved from dark mode to light — dimming an already-near-black app only muddied it, while a
  bright page needs something to separate the popover from it. And step 2's copy was simplified:
  the "it's already on" clause dropped, and the opener changed to "Open this menu for chat
  options," which no longer counts the menu's rows and so can't be invalidated by a
  `librechat.yaml` capability toggle.
- **Paired infra change:** none beyond this digest bump.
- **`DEPLOY_TRIGGER` bumped 1 → 2** in the same PR, believed at the time to be what made the
  deploy run. It wasn't — the counter was never load-bearing (§5). This deploy succeeded because
  the detect step's baseline happened to be an older commit, not because of the bump.
- **Verified before deploy:** digest present in `acrcgfedev` (`az acr repository show`), linux/amd64,
  tag `25780`, built 2026-08-04 19:45 UTC.
- **Rollback:** restore `sha256:12c7731e…9d556942` and redeploy — still in the registry.

### 2026-08-04 — Dev — `sha256:12c7731e…9d556942`

- **Fork commit:** `03925623b` (fork `main` after PR 11524) · **ACR tag:** `25740` · **arch:** amd64
- **What's in it:** the guided tour's plain-language copy pass — all four step bodies rewritten to
  drop internal vocabulary ("indexed for File Search", "switches") for a non-technical audience —
  plus three fixes to the tour's step machinery found while testing it in dev:
  advancing a step could render the *previous* step's copy on the previous step's anchor under the
  new step's number; step 3's anchor doesn't exist when the sidebar is collapsed, so the step was
  skipped for anyone who'd ever collapsed it; and below 768px the tour's backdrop stacked on top
  of the sidebar's own scrim, leaving the app too dark to see what the popover pointed at. The
  backdrop is now transparent in light mode and lightly dimmed in dark.
- **Paired infra change:** none. Source-only — no `librechat.yaml` or bicep change beyond this
  digest bump.
- **Verified before deploy:** digest present in `acrcgfedev` (`az acr repository show`), linux/amd64,
  tag `25740`, built 2026-08-04 18:11 UTC.
- **Not covered by automated tests:** the client suite was not run against this build in the
  authoring environment. The sidebar expand/restore and scrim suppression have no test coverage at
  all — see the fork's `PATCHES.md` "How to verify" list for the manual checks, particularly
  desktop-with-collapsed-sidebar and sub-768px.
- **Rollback:** restore `sha256:5e198b62…6be19544` and redeploy — still in the registry.

### 2026-08-03 — Dev — `sha256:5e198b62…6be19544`

- **Fork commit:** `0b202deef` (fork `main` after PR 11452) · **ACR tag:** `25436` · **arch:** amd64
- **What's in it:** the second round of launch review work, integrated on the fork's
  `integration/romchat-launch-v2` branch — PBI 12687 (raster ROMChat logo replaced with a true
  vector master), 12745 (File Search restored to the tools menu and enabled from every attach
  path), 12746 (guided tour made modal: dimmed backdrop, blocked interaction, pointer to target),
  and 12633's tour copy/anchor reconciliation. Three branches had each independently changed the
  tour; the integration commit resolved the conflicts and fixed a cross-branch defect where the
  merged tour described the tools menu while omitting File Search.
- **Paired infra change:** none. This build is source-only — no `librechat.yaml` or bicep change
  travels with it beyond the digest bump itself.
- **Test + prod staged in the same commit.** All three `main.<env>.bicepparam` files are authored
  on `dev` and carried upward by the promotion merges (`dev` → `test` → `main`) — we never edit an
  env's param on its own branch. Each value is inert until its branch is reached, so the test and
  prod entries deploy nothing today. This is also the migration of test and prod off upstream's
  mutable `ghcr.io` tag.
- **Cross-registry promotion automated in the same change.** Stage 1.3 built only the dev half of
  the fork pipeline and deferred test/prod promotion as "a later step" — so the first promotion past
  dev would have needed a hand-run `az acr import`. `test.yml` and `prod.yml` now carry an
  `ImportLibreChatImage` stage that does it from the param file (§3). Promotion is merge-and-go.
- **Verified before deploy:** digest present in `acrcgfedev` (`az acr repository show`), linux/amd64,
  tag `25436`, built 2026-08-03 13:29 UTC.
- **Rollback:** restore `sha256:65932ee0…f96c7a2f` and redeploy — still in the registry.

### 2026-07-31 — Dev — `sha256:65932ee0…f96c7a2f`

- **Fork commit:** `7e80cac6c` (fork `main` after PR 11430) · **ACR tag:** `25042` · **arch:** amd64
- **What's in it:** the first build carrying ROMChat source patches — PBI 12626 (remove "Upload to
  Provider"), 12627 (paperclip → one-click File Search upload), 12628 (browser-tab + login branding),
  12631 (Artifacts sub-options stripped), 12633 (first-run guided tour), and the `engineTTS`
  fork patch that makes 12632's Azure TTS audible.
- **Paired infra change:** merged separately as PR 11429 (`dev`) — 12629 (`context` capability
  removed), 12688 (document allowlist reconciled; legacy `.doc` dropped, `.xls` added), 12632's
  bicep/config half, and the `fileConfig` YAML anchor that closed a **live server-side image-upload
  hole** on the `agents` and `default` endpoints.
- **Verified before deploy:** digest present in `acrcgfedev` (`az acr repository show`), amd64,
  tag `25042`.
- **Rollback:** restore `sha256:6c97e7f9…4051d0e` and redeploy — still in the registry. Note that
  rolling the image back does **not** roll back the config merged in PR 11429.

### 2026-07-28 — Dev — `sha256:6c97e7f9…4051d0e`

- **Fork commit:** `566e20b6` (unmodified upstream `v0.8.6`) + our `azure-pipelines.yml`
- **What's in it:** nothing of ours. A deliberate **zero-patch parity build**, to prove the
  build-and-deploy path in isolation before introducing any source changes.
- **Infra PR:** 11239 (`be95c98`) → `dev`
- **Verified:** 2026-07-29 — revision `ca-librechat-dev--0000018`, single active revision, 100%
  traffic, Healthy/Running, serving the digest above. Okta login + chat smoke test passed.
- **Significance:** closes the mutable-tag supply-chain exposure **for dev**. Test and prod still
  pull `:v0.8.6` from ghcr, where a re-pushed tag would reach us on any replica pull.

---

## 1. Why digests, not tags

A tag like `:v0.8.6` is a mutable pointer — whoever controls the registry can repoint it at different
content, and we'd pick it up silently on the next pull. A digest is a cryptographic fingerprint of
exact image content: it cannot be repointed. For a system handling PHI, every deployment should be
reproducible and auditable, so **every environment should be pinned by digest.** Test and prod aren't
yet — that's the open migration work.

## 2. Deploying a new build to dev

The infra pipeline **does not build anything.** It deploys an image that must already exist in the
target environment's registry. Order is load-bearing: **build → copy digest → verify → deploy.**
(For dev that is the whole story. For test and prod the copy happens *inside* the deploy run, as
the **first** stage — before `BicepCreate` repoints the app. See §3.)

1. Merge the change in the **fork** repo → its pipeline builds and prints the digest.

   ⚠️ **The build log contains two digests. Only one is ours.** `az acr build` emits a summary
   block listing `image.digest` (the ROMChat image we just built — **this is the one**) and
   `runtime-dependency.digest` (the `node:20-alpine` base image it pulled from Docker Hub —
   provenance only, never a deploy target). Take the digest from the pipeline's own
   `Deploy by DIGEST` banner at the end of the log, which prints only the correct one.

   Deploying the base-image digest wouldn't fail loudly at deploy time: the container would
   start without ROMChat in it, fail `/health`, and Container Apps would keep the previous
   revision serving — so the app would look fine while the deploy had actually failed (§4).
   Step 2 catches this, because the base-image digest doesn't exist in our registry at all.
2. **Verify the digest exists in the target registry** before deploying:
   ```bash
   az acr repository show --name acrcgfedev \
     --image librechat@sha256:<digest> --query digest -o tsv
   ```
   A miss = don't deploy yet.
3. Update `ChatGptForEmployees.bicep/main.dev.bicepparam` → `libreChatImage`, **and add a History
   entry above, in the same PR.**

   Changing the digest is now sufficient. It wasn't until 2026-08-05 — see §5 for what used to
   go wrong and how to recognise it if it ever returns.
4. Merge to `dev`. `BicepCreate` applies the image; Container Apps rolls a new revision automatically
   because the digest changed.
5. **Verify what's actually serving** (§4).

**Safe failure mode:** a bad or missing digest means the new revision never passes `/health`, and
`activeRevisionsMode: Single` keeps the last healthy revision serving. You get a loud
`ProgressDeadlineExceeded`, **not** an outage.

## 3. ⚠️ Promoting to test / prod — the registry-host footgun

Promotion is **not a rebuild.** The same digest is copied into the target environment's registry, so
test and prod run bit-identical images to what was validated in dev.

**The copy is automatic.** `test.yml` and `prod.yml` each have an `ImportLibreChatImage` stage: it
reads `libreChatImage` from that environment's bicepparam, imports the digest from `acrcgfedev` if
it isn't already there, and verifies it landed. Set the digest in the param file and promote —
nothing else to do.

**It runs *before* `BicepWhatIf`/`BicepCreate`.** The image is in the target registry by the time
Bicep points the Container App at that digest, so the new revision pulls on creation and comes up
healthy. If the copy can't happen, the run fails before any infrastructure is touched.

### Why it was reordered on 2026-08-05, and how to put it back

It originally ran *after* `BicepCreate`, so that on a first run the registry would exist before the
import needed it. The cost of that ordering was paid on every deploy, not just the first:

- **Bicep created a revision that couldn't pull.** It stayed unhealthy until the later
  `DeployLibreChat` restart retried it — making that restart the recovery mechanism for image
  rollout, a path never actually exercised. `UploadConfigs`, `DeployLiteLLM` and `DeployRagApi` all
  run in between, each waiting on a restart of its own, so the revision could pass its progress
  deadline before the retry arrived.
- **A failed `BicepCreate` gated the import off**, so a re-run couldn't self-heal — the image could
  never land without a hand-run import.
- `activeRevisionsMode: Single` meant none of this took the app down; it just meant the environment
  could sit on the old image behind a green pipeline.

The bootstrap case it protected is one-time per environment, both target registries already exist,
and the stage now checks for a missing registry and skips rather than failing.

**Two consequences of the new order, both accepted:**

1. A brand-new environment needs the registry to exist first. There is deliberately **no**
   "skip if the registry is missing" branch — one was added and removed the same day, because its
   condition was also true for a missing RBAC read, throttling or a token blip, turning any of
   those into a green run that skipped the import. Bootstrap a new environment by running the
   manual import in this section once, or let the stage fail and re-run after `BicepCreate` has
   created the registry. Neither current environment is in this position.
2. The copy now happens **before** the Prod environment's approval gate, since that gate sits on
   `BicepCreate`. What lands early is a tagged manifest that nothing points at — the import tags it
   deliberately, since untagged manifests are what ACR retention policies delete. Nothing deploys
   without the approval, and a rejected approval leaves the manifest in the registry; remove it by
   hand if that matters.

**To revert:** move the `ImportLibreChatImage` stage back below the `insert-stage-bicep-create`
template in `test.yml` and `prod.yml`, and restore `dependsOn: BicepCreate` with
`condition: in(dependencies.BicepCreate.result, 'Succeeded', 'SucceededWithIssues', 'Skipped')`.
Nothing else changes — the downstream stages check both `BicepCreate` and the import either way, and
the registry-exists branch is harmless in that position. The same instructions are in the stage's own
comment block.

**A green run still does not prove the new image is serving.** Nothing asserts the LibreChat revision
went healthy on the new digest, and `Single` mode makes a failed rollout look identical to a
successful one from the pipeline's point of view. Verify with §4 after any promotion.

The stage is idempotent (a redeploy of an unchanged digest is one lookup), and it no-ops on any
reference that isn't for that environment's own ACR, so it stays harmless on a param still pointing
at upstream's public `ghcr.io` image.

Doing it by hand — for a one-off, or if you're diagnosing the stage:

```bash
# 1. Copy the exact digest into the target env's registry.
#    TARGET must be repo:TAG — `--image/-t` takes 'repo/image:tag', and a digest there is rejected
#    ('@' isn't legal in a repository name). The manifest is copied as-is either way, so the
#    resulting DIGEST is identical; the tag is only a handle. The pipeline derives it from the
#    digest (first 12 hex chars), which is why a mirrored image carries a different tag from the
#    dev build's ACR tag.
#    `-r` names the SOURCE registry so it resolves via AAD. Without it, `--source` is treated as an
#    external registry and returns 401 even when you do have access.
az acr import --name acrcgfetest \
  -r /subscriptions/e64069c2-4b14-4c32-a1f0-3493457f0eff/resourceGroups/rg-dev-shared/providers/Microsoft.ContainerRegistry/registries/acrcgfedev \
  --source librechat@sha256:<digest> \
  --image librechat:<short-digest>

# 2. Confirm it arrived
az acr repository show --name acrcgfetest --image librechat@sha256:<digest> --query digest -o tsv
```

> **Permissions — the one cross-environment exception.** The import step runs as
> **`ChatGptForEmployeesDevSC`**, not as the environment's own service connection. It has to: the
> Test and Prod connections cannot read `acrcgfedev`, and the source has to be readable by whoever
> performs the copy. The step also passes `acrcgfedev`'s admin credentials explicitly for the source
> side. Every other stage in these pipelines still runs as the environment's own connection.
>
> ⚠️ **The command above and the pipeline authenticate differently.** The manual command uses
> `-r <source-resource-id>`, which resolves the source via AAD. The stage instead passes
> `acrcgfedev`'s admin username/password with a bare `--source` FQDN, because without `-r` a
> login-server source is treated as an external registry and 401s. Both work. Now that the role
> grant exists the credential form is probably unnecessary, and dropping it would remove an
> admin password from the pipeline's process arguments — worth doing, but it changes a working
> path, so it wants a deliberate test rather than a drive-by edit. The password is registered
> with `issecret=true` so the agent masks it in the meantime.
>
> That principal needs **`Container Registry Data Importer and Data Reader`** on `acrcgfetest` and
> `acrcgfeprod` — granted by Ops 2026-08-05. ⚠️ **`AcrPush` does not work**: `az acr import` is a
> control-plane operation and `AcrPush` only grants data-plane push. An earlier version of this note
> said `AcrPull`, which was wrong in the same way.

**Then set `main.test.bicepparam` to that env's OWN registry host** — edited on `dev` and carried up
by the `dev` → `test` promotion, like every other param change. Never edit it on the `test` branch:

```bicep
param libreChatImage = 'acrcgfetest.azurecr.io/librechat@sha256:<digest>'
//                      ^^^^^^^^^^^ MUST be acrcgfetest — NOT acrcgfedev
```

**Why this matters:** `libreChat.bicep` builds its registry credentials from *this environment's*
`acrcgfe<env>` only. The host in the bicepparam is hand-typed. Leaving `acrcgfedev` in
`main.test.bicepparam` or `main.prod.bicepparam` means the pull fails for lack of credentials — or,
worse, points a production environment at the **dev** registry.

> **Recommended when wiring test/prod:** eliminate the footgun by construction. Pass only the *digest*
> as the param and build the full reference inside `libreChat.bicep` from
> `acr.properties.loginServer`. Then the host is always correct and cannot be mistyped.

## 4. Verifying what's actually running

**"I opened the app and it worked" is not verification.** With `activeRevisionsMode: Single`, a
deployment that fails to start leaves the previous healthy revision serving traffic — so a failed
deploy presents as a perfectly working app.

```bash
az containerapp revision list -n ca-librechat-<env> -g rg-<env>-shared \
  --query "[?properties.active].{name:name, traffic:properties.trafficWeight, health:properties.healthState, running:properties.runningState, image:properties.template.containers[0].image}" -o table
```

Check the **active revision's** image. Querying the app's `properties.template` instead shows the
*desired* spec and would look correct whether or not the deploy succeeded — that's the trap.

Resource groups: `rg-dev-shared`, `rg-test-shared`, `rg-prod-shared`. Apps: `ca-librechat-dev`,
`ca-librechat-test`, `ca-librechat-prod`.

You can also ask the app itself: **Settings → About** reports the `BUILD_COMMIT`, `BUILD_BRANCH`, and
`BUILD_DATE` baked into the image, which maps a running deployment back to an exact fork commit.

## 5. Known gaps

- **RESOLVED 2026-08-05 — a digest bump used to silently not deploy.** Worth reading, because the
  failure is invisible and the first two diagnoses were wrong.

  **Symptom.** A digest-only PR merges, the run goes green, and the container app keeps its
  previous image. No new revision, no ARM deployment in the resource group, and the app's own
  `/api/config` `buildInfo` still reports the old commit. The restart stages still run — they were
  made to tolerate a Skipped `BicepCreate` in PR 10964 — so the app cycles on the **old** image and
  looks perfectly healthy. Hit us on PR 11547 (tag `25740`) and again on PR 11602 (tag `26023`).

  **Cause.** `DetectBicepChanges` (`ROMTech/PipelineTemplates`,
  `insert-stage-detect-folder-changes.yml`) gates `BicepWhatIf` on `RunStage == 'true'`, and
  `BicepCreate` is `condition: succeeded('BicepWhatIf')` — so a false detection skips both while
  the run reports success. The detection is **folder-based, not file-type-based**: it runs when a
  changed path falls under `ChatGptForEmployees.bicep/`, which includes `.bicepparam`. The real
  problem is the baseline it diffs against —
  `builds?definitions=<id>&resultFilter=succeeded&$top=1`, **no branch filter**. A PR
  build-validation run builds the PR's merge commit, already containing the change, and becomes
  that baseline; the subsequent merge to `dev` then diffs against a commit that already had
  everything and finds nothing to do. That also explains why PR 11458 on 08-03 deployed fine —
  the baseline happened to be older.

  **Two wrong diagnoses, recorded so nobody repeats them.** First: "it only counts `.bicep`
  files" — false, it is folder-based. Second, following from it: the `DEPLOY_TRIGGER` counter in
  `main.bicep`, a comment bumped by hand to make a digest change touch a `.bicep` file. It could
  never have helped, and PR 11602 proved it — counter bumped, deploy still skipped. Removed.

  **Fix.** `dev.yml`, `test.yml` and `prod.yml` now pass `bicepDetectFolder: ''` to
  `insert-stage-bicep-whatif.yml`, taking the detect template's documented "no folder resolved →
  run the stage" path. Whatif and create now run on every push to the env branch. Cost: a couple
  of minutes and an idempotent ARM deployment when nothing infra changed. `BicepCreate` is still a
  deployment job bound to its environment, so any approval gate is unaffected.

  **If it ever comes back**, the detect step logs both halves — `Last successful build SHA:` and
  `Changed files:`. A baseline that isn't the previous env-branch tip is the tell.

- **Test and prod are staged for our fork but not yet running it** — their params point at
  the current digest in their own registries, but that only takes effect as the promotions reach
  them. Until then both are still serving `ghcr.io/danny-avila/librechat:v0.8.6` by mutable tag.
  The import is automatic now (§3), but the supply-chain hardening isn't done until both
  promotions have completed and been verified (§4).
- **`ImportLibreChatImage` has not run yet in either environment.** It ships unexercised. Watch the
  first `dev` → `test` promotion for an authorization error against `acrcgfedev` — that's the one
  thing about it that depends on role assignments we haven't confirmed.
- **ACR pull uses admin credentials** (mirroring the scheduled-jobs pattern) rather than a managed
  identity with `AcrPull`. The password is never exposed in the container environment — it's used by
  the Container Apps platform via `passwordSecretRef` — but identity-based pull is the target state.
  Tracked as **WI 12306**; higher priority for this app than for the internal jobs, since ROMChat is
  external-facing and PHI-adjacent.
- **`what-if` noise:** `acr.listCredentials()` is a runtime function `what-if` cannot evaluate, so the
  `acr-password` secret and `registries` block always appear as changes or unknowns in what-if output.
  Expected — not a drift signal.

## 6. Related

- **Fork repo:** `ChatGptForEmployeesLibreChatFork` — see its `ROMCHAT_DEV_GUIDE.md` (developer
  workflow) and `PATCHES.md` (inventory of our divergences from upstream).
