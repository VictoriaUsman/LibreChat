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
| **Dev** | `acrcgfedev.azurecr.io/librechat@sha256:12c7731e5ff2588b6cb30b13260aa27119b16c066195af431a78d2dc9d556942` | 2026-08-04 | `03925623b` | Guided-tour copy + step-advance fixes. ACR tag `25740`. |
| **Test** | `acrcgfetest.azurecr.io/librechat@sha256:12c7731e…9d556942` | *staged* | `03925623b` | Set in `dev`; **deploys when `dev` → `test` promotes.** Image imported automatically by `test.yml`. |
| **Prod** | `acrcgfeprod.azurecr.io/librechat@sha256:12c7731e…9d556942` | *staged* | `03925623b` | Set in `dev`; **deploys when `test` → `main` promotes.** Image imported automatically by `prod.yml`. |

> **This table is a convenience, not the source of truth.** The authoritative record is
> `ChatGptForEmployees.bicep/main.<env>.bicepparam` — that file is what actually deploys. To see what
> is *genuinely* running right now, query Azure (§4).

---

## History

Newest first. One entry per image change per environment.

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
4. Merge to `dev`. `BicepCreate` applies the image; Container Apps rolls a new revision automatically
   because the digest changed.
5. **Verify what's actually serving** (§4).

**Safe failure mode:** a bad or missing digest means the new revision never passes `/health`, and
`activeRevisionsMode: Single` keeps the last healthy revision serving. You get a loud
`ProgressDeadlineExceeded`, **not** an outage.

## 3. ⚠️ Promoting to test / prod — the registry-host footgun

Promotion is **not a rebuild.** The same digest is copied into the target environment's registry, so
test and prod run bit-identical images to what was validated in dev.

**The copy is automatic.** `test.yml` and `prod.yml` each have an `ImportLibreChatImage` stage that
runs before `BicepCreate`: it reads `libreChatImage` from that environment's bicepparam, imports the
digest from `acrcgfedev` if it isn't already there, and verifies it landed. Set the digest in the
param file and promote — nothing else to do.

The stage is idempotent (a redeploy of an unchanged digest is one lookup), and it no-ops on any
reference that isn't for that environment's own ACR, so it stays harmless on a param still pointing
at upstream's public `ghcr.io` image.

Doing it by hand — for a one-off, or if you're diagnosing the stage:

```bash
# 1. Copy the exact digest into the target env's registry
az acr import --name acrcgfetest \
  --source acrcgfedev.azurecr.io/librechat@sha256:<digest> \
  --image librechat@sha256:<digest>

# 2. Confirm it arrived
az acr repository show --name acrcgfetest --image librechat@sha256:<digest> --query digest -o tsv
```

> **First run only:** the import reads from `acrcgfedev`, which lives in `rg-dev-shared`, while the
> stage runs as that environment's own service connection (`ChatGptForEmployeesTestSC` /
> `…ProdSC`). If those principals lack read access to the dev registry, the stage fails with an
> authorization error and prints the exact grant needed — `AcrPull` on `acrcgfedev`. Same
> subscription, so it's a role assignment, not a cross-tenant problem.

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

- **Test and prod are staged for our fork but not yet running it** — their params point at
  `sha256:5e198b62…` in their own registries, but that only takes effect as the promotions reach
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
