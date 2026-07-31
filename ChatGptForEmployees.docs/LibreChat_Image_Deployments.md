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
| **Dev** | `acrcgfedev.azurecr.io/librechat@sha256:65932ee0fe428d1ac695b6d94dc4228646e5c2b84d42b0a156784ee7f96c7a2f` | 2026-07-31 | `7e80cac6c` | **First patched build** — launch UI work. ACR tag `25042`. |
| **Test** | `ghcr.io/danny-avila/librechat:v0.8.6` | — | n/a | ⚠️ Still upstream's prebuilt image, by **mutable tag**. Not yet migrated. |
| **Prod** | `ghcr.io/danny-avila/librechat:v0.8.6` | — | n/a | ⚠️ Still upstream's prebuilt image, by **mutable tag**. Not yet migrated. |

> **This table is a convenience, not the source of truth.** The authoritative record is
> `ChatGptForEmployees.bicep/main.<env>.bicepparam` — that file is what actually deploys. To see what
> is *genuinely* running right now, query Azure (§4).

---

## History

Newest first. One entry per image change per environment.

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

```bash
# 1. Copy the exact digest into the target env's registry
az acr import --name acrcgfetest \
  --source acrcgfedev.azurecr.io/librechat@sha256:<digest> \
  --image librechat@sha256:<digest>

# 2. Confirm it arrived
az acr repository show --name acrcgfetest --image librechat@sha256:<digest> --query digest -o tsv
```

**Then set `main.test.bicepparam` to that env's OWN registry host:**

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

- **Test and prod are not yet on our fork** — still pulling `ghcr.io/danny-avila/librechat:v0.8.6` by
  mutable tag. Migrating them is the outstanding supply-chain hardening.
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
