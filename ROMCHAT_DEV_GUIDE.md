# ROMChat — developer guide to this fork

**Read this before your first change.** It explains what this repo is, how your work reaches the
running app, and the one rule that keeps this fork maintainable.

---

## 1. What this repo is

This is **ROMTech's fork of [LibreChat](https://github.com/danny-avila/LibreChat)** — the open-source
chat application behind ROMChat. It was branched from upstream release **`v0.8.6`**.

Two repos matter, and they do different jobs:

| Repo | What lives there |
|---|---|
| **`ChatGptForEmployeesLibreChatFork`** (this one) | The application source. Your UI/feature changes. The pipeline that builds the container image. |
| **`ChatGptForEmployees`** (infra) | Azure infrastructure (bicep), `librechat.yaml` config, and the setting that decides **which built image each environment runs**. |

They are coupled by exactly one thing: **an image digest** (see §4).

### Why we forked

We ran upstream's prebuilt image until 2026-07-28. That meant zero source control over the app — no
branding, no UI adjustments. Forking buys that, at the cost of maintaining a divergence from
upstream. Everything below exists to keep that cost small.

### Upstream is still a live remote

```bash
git remote -v
# origin    → ADO (ours)
# upstream  → github.com/danny-avila/LibreChat
```

We periodically merge upstream releases. **This is why §3 matters so much.**

---

## 2. Prefer config over code — seriously

Before you patch anything, check whether it can be done **without touching this repo**:

- **`librechat.yaml`** (infra repo) — model config, endpoints, most feature toggles, interface options
- **Environment variables** (`libreChat.bicep`, infra repo) — `APP_TITLE`, `CUSTOM_FOOTER`,
  `HELP_AND_FAQ_URL`, and much more
- **The help page** — a separate static web app in the infra repo

A config change costs nothing when we merge upstream. A source patch costs something **every time,
forever.** If config can do it, config should do it. Ask before patching if you're unsure.

---

## 3. The one rule: every source change gets a PATCHES.md entry

**In the same PR as the change.** No exceptions.

[`PATCHES.md`](./PATCHES.md) is the complete inventory of how this fork differs from upstream. When
we pull LibreChat's next release, `git merge upstream` will conflict wherever we've diverged — and
the person resolving those conflicts usually isn't the person who wrote the patch. They need to know
*what you were trying to achieve*, so they can tell whether upstream's new code already achieves it.

Without an entry, the safe-looking resolution is always "keep ours," and we accumulate patches nobody
can justify or remove. That's how a fork becomes unmaintainable.

`PATCHES.md` has a copy-paste template. Fill in all of it — especially **How to verify** (concrete
steps in the running app) and **Why config couldn't do it**.

**Keep patches small and local.** Prefer adding to a file over rewriting it. Smaller surface = smaller
conflict later. If a change is generally useful, consider opening a PR against upstream too — merged
upstream means the patch deletes itself.

---

## 4. How your change reaches the running app

```
  branch → PR → merge to main → pipeline builds image → digest
                                                          ↓
                        infra repo: paste digest into main.dev.bicepparam
                                                          ↓
                                    merge to dev → deploys → verify
```

**A "digest"** is `sha256:` + a long hex string — a fingerprint identifying one exact build. We deploy
by digest, never by a tag like `:latest`, so a deployment is unambiguous and can't silently change.

### Step by step

1. **Branch off `main`**, implement your work item, add your `PATCHES.md` entry.
2. **Push and open a PR.** Pushing a branch does **not** trigger a build — push as often as you like.
3. **Merge to `main`.** *This* triggers the build pipeline (~10 minutes).
4. **Copy the digest** the pipeline prints at the end. It looks like:
   ```
   ==================================================================
   Image pushed. Deploy by DIGEST (put this in libreChatImage):
     acrcgfedev.azurecr.io/librechat@sha256:6c97e7f9...
   ==================================================================
   ```
5. **In the infra repo**, paste it into `ChatGptForEmployees.bicep/main.dev.bicepparam`
   (`libreChatImage`), and add a row to `ChatGptForEmployees.docs/LibreChat_Image_Deployments.md`
   in the **same PR**. Merge to `dev` → the dev pipeline deploys it.
6. **Verify it actually landed** — see §5. Then test your change in dev.

> Promotion to test/prod is **not** a rebuild. The same digest gets copied into those environments'
> registries. Ops handles that — see the infra repo's deployment log.

### When the pipeline runs

| Action | Builds? |
|---|---|
| Push to a feature branch | **No** |
| Open / update a PR | **No** *(unless a build-validation policy is enabled on `main`)* |
| Merge to `main` | **Yes** |
| Merge a docs-only change (`**/*.md`) to `main` | **No** — excluded, since docs can't change the image |

> **Maintainer note:** if you ever want PRs to build before merge, a `pr:` block in
> `azure-pipelines.yml` **will not work** — Azure Repos silently ignores YAML `pr:` triggers (they're
> GitHub/Bitbucket only). You need a **Build Validation branch policy** on `main`
> (Repos → Branches → `main` → Branch policies → Build Validation). Gate it on
> `Build.Reason == PullRequest` and pass `--no-push` so PR runs validate the build without
> publishing a throwaway image.

---

## 5. Verify your change actually deployed

**Do not rely on "I opened the app and it worked."** The container platform runs in
`activeRevisionsMode: Single`, which means **if a new deployment fails to start, the previous healthy
version keeps serving traffic.** A failed deploy therefore looks exactly like a perfectly working app.

Two reliable checks:

**A. Ask the running app what it is.** Open ROMChat → **Settings → About**. The image reports the
`BUILD_COMMIT`, `BUILD_BRANCH`, and `BUILD_DATE` it was built from. If the commit isn't yours, your
change isn't live.

**B. Ask Azure which revision is actually serving:**
```bash
az containerapp revision list -n ca-librechat-dev -g rg-dev-shared \
  --query "[?properties.active].{name:name, traffic:properties.trafficWeight, health:properties.healthState, image:properties.template.containers[0].image}" -o table
```
The active revision's image must be your digest. (Checking the *app's* `properties.template` instead
would show the desired spec and look correct either way — that's the trap.)

---

## 6. Local development

Standard LibreChat setup applies — see upstream's [`README.md`](./README.md) and
[`AGENTS.md`](./AGENTS.md)/[`CLAUDE.md`](./CLAUDE.md) for structure and conventions. Run the test
suites and linting before opening a PR, as upstream documents.

Note the deployed app is configured entirely from the **infra** repo (`librechat.yaml` + env vars),
so local behavior can differ from dev if your change interacts with configuration. When in doubt,
verify in dev after deploy.

---

## 7. Merging upstream releases

Not routine day-to-day work, but it's why the rules above exist. The procedure — including walking
every `PATCHES.md` entry and dropping patches upstream has adopted — is in
[`PATCHES.md`](./PATCHES.md) § *Upstream merge procedure*.
