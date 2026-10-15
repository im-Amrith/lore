# lore-sandbox: the story

`lore-sandbox` is a small, clearly fake company repo that we control. It exists so the demo can show three things the real FalkorDB data can't be relied on for: a decision that gets reversed live, a planted "paper owner", and an agent that writes back to GitHub without touching a real project.

**Create the repo on Oct 15 (after 12:01 AM IST).** This file is just the script. Say in the README that the sandbox is synthetic data built for the demo.

## The fake product

**Tern** is a tiny URL-shortener service: it creates short links, redirects visitors and counts clicks. Everyone understands it in five seconds, and it has enough moving parts for ownership, decisions and duplicates.

```
lore-sandbox/
  README.md                 # "Tern: a demo URL shortener. Synthetic repo for the Lore hackathon project."
  CODEOWNERS
  api/        handlers.py  codes.py  limits.py
  cache/      link_cache.py
  analytics/  clicks.py  export.py
  storage/    db.py  compaction.py
  docs/
    adr/      0001-link-cache.md  0002-short-codes.md
    expiry.md
```

The code files only need a few lines of plausible Python each. Claude Code can generate them on Oct 15 in a minute. What matters is which person's commits touch which folder.

## The cast

You need real GitHub accounts for anything that opens, reviews or approves. Commits can carry any author name. Don't create extra GitHub accounts to fake people (GitHub allows one free account per person). Use teammates or friends who agree to it, plus commit-only authors.

| Role in the story | Who plays them | What they do |
| --- | --- | --- |
| **You**: owns `api/` and `cache/` | Your GitHub account | Opens all issues and PRs, commits to `api/` and `cache/` |
| **Reviewer**: listed as owner of `analytics/` | A teammate or friend's real account (ask first) | Approves PR 1 and PR 6. Never commits to `analytics/`, which makes them the **paper owner** |
| **Priya Raman**: the real analytics expert | Commit-only author (`--author`) | All commits in `analytics/` |
| **Marta Silva**: the only person who knows storage | Commit-only author (`--author`) | All commits in `storage/` (bus factor 1) |

Commit-only author syntax (use the `.invalid` domain so the address can never be real; Lore drops emails anyway):

```
git commit --author="Priya Raman <priya@tern.invalid>" -m "..."
git commit --author="Marta Silva <marta@tern.invalid>" -m "..."
```

These commits show on GitHub with no linked account. Tell Claude Code in M3 that a commit author with no GitHub login becomes `person:name:<slug>`.

If you have no reviewer available: put your own login in CODEOWNERS for `analytics/` instead (you're still a paper owner if you never commit there, since Priya does all the work), and skip the approvals. Decisions then have PROPOSED edges but no APPROVED edges.

## CODEOWNERS

```
/api/        @<your-login>
/cache/      @<your-login>
/analytics/  @<reviewer-login>
/storage/    @<your-login>
/docs/       @<your-login>
```

`storage/` lists you on purpose: you're the official owner, but Marta wrote all of it. That makes it a second paper-owner case, and the bus-factor-1 module.

## Issues

Open these in order. Close the ones marked closed through the PR that fixes them, so the PR-to-issue CLOSES links exist.

| # | Title | Body (summary to write out) | Labels | Ends |
| --- | --- | --- | --- | --- |
| 1 | Cache misses spike after every deploy | After each deploy, redirect latency jumps for ~20 minutes. Each API replica has its own in-process cache, so all 3 replicas start cold, and invalidation after a link edit only reaches one replica. | bug, link-cache | Closed by PR 1 |
| 2 | Short codes are guessable | Codes are sequential (`aaab`, `aaac`…). Anyone can walk every link and estimate our volume. | security, short-codes | Closed by PR 2 |
| 3 | Redirect returns 500 for codes with uppercase letters | `/Xk9fT2a` returns 500. Lookup lowercases the code before querying, but codes are case-sensitive. | bug, redirects | Closed by PR 3 |
| 4 | Click counts drift between dashboard and export | Dashboard shows more clicks than the CSV export for the same day. Looks like cache hits are counted twice. | bug, analytics | Closed by PR 4 |
| 5 | Compaction job holds the DB lock for minutes | Nightly compaction runs one huge transaction; redirects stall while it runs. | bug, storage | Closed by PR 5 |
| 6 | p99 redirect latency regressed after the Redis cache | Since the Redis cache shipped, p99 went from 4 ms to 12 ms: every redirect now makes a network hop. We now run 2 replicas in one region. | performance, link-cache | Stays open; PR 6 refers to it |
| 7 | Allow custom aliases for links | Users want `/launch` instead of a random code. | enhancement, short-codes, good first issue | Open |
| 8 | Docs: explain how link expiry works | Nobody can find how and when links expire. | docs | Open |
| 9 | CSV export times out above 100k clicks | Export builds the whole file in memory. | bug, analytics | Open |
| 10 | Rate-limit link creation per API key | One key created 50k links in an hour. | enhancement, api-limits | Open |

## Pull requests

Write the PR descriptions in full (over ~300 characters), because the decision extractor only reads PRs with real descriptions. The "Decision" lines are what Lore should pull out.

**PR 1: Cache resolved links in Redis with a 24h TTL** (closes #1)
- Commits by you, touching `cache/link_cache.py`, `api/handlers.py`; also adds `docs/adr/0001-link-cache.md`.
- Reviewer approves.
- Description to write: *We're moving the link cache out of the API process into a shared Redis instance with a 24-hour TTL. Each of our 3 replicas kept its own LRU, so every deploy started 3 cold caches and an edited link stayed stale on 2 of them. A shared cache stays warm across deploys and an edit is a single delete. We considered keeping the in-process LRU and adding pub/sub invalidation, but with 3 replicas across 2 regions that's more moving parts than one Redis. Trade-off: every redirect now makes a network hop, which we expect to cost ~1–2 ms.*
- **Decision:** use a shared Redis link cache (24h TTL). **Rejected:** in-process LRU + pub/sub invalidation.

**PR 2: Generate short codes as random 7-character base62** (closes #2)
- Commits by you, touching `api/codes.py`; adds `docs/adr/0002-short-codes.md`.
- Description: *Sequential codes leak volume and let anyone enumerate links. Codes are now 7 random base62 characters (about 3.5 trillion combinations), with a retry on collision. We rejected hashids over the auto-increment id: they look random but can be decoded if the salt leaks, and they still reveal ordering.*
- **Decision:** random 7-char base62 codes. **Rejected:** hashids.

**PR 3: Keep short-code lookup case-sensitive end to end** (closes #3)
- Commits by you, touching `api/handlers.py`.
- Description: short bug fix; the handler lowercased codes; remove that and add a test for mixed-case codes.

**PR 4: Count a click once per redirect, not per cache hit** (closes #4)
- 2–3 commits authored as **Priya**, touching `analytics/clicks.py`. You open the PR.
- Description: click events were emitted in both the cache layer and the handler; emit only in the handler.

**PR 5: Compact storage in batches of 1,000 rows** (closes #5)
- 2–3 commits authored as **Marta**, touching `storage/compaction.py`. Add 2–3 more small Marta commits to `storage/db.py` on other days so she clearly dominates `storage/`.
- Description: *one transaction per 1,000 rows instead of one for the whole table; redirects no longer stall; total runtime goes up ~10%, which is fine at night.*
- **Decision:** batch compaction (1,000 rows). **Rejected:** moving compaction to a read replica (we don't have one).

**PR 6: Replace the Redis link cache with an in-process LRU and pub/sub invalidation** (refs #6; DRAFT, merged live in the demo)
- Commits by you, touching `cache/link_cache.py`, `api/handlers.py`; updates `docs/adr/0001-link-cache.md` to say "Superseded" and adds `docs/adr/0003-in-process-cache.md`.
- Reviewer approves (if available).
- Description: *This reverses the decision in #<PR 1>. The Redis hop pushed p99 from 4 ms to 12 ms (#6), and we now run 2 replicas in a single region, so the reason for a shared cache is gone. Each replica keeps an in-process LRU; a link edit publishes an invalidation message that every replica applies. Cold starts after deploys are handled by warming the top 10k links on boot. Supersedes ADR 0001.*
- **Decision:** in-process LRU + pub/sub invalidation. **Supersedes:** the PR 1 decision.

Also add a few plain commits so history isn't only PRs: README tweaks by you, a typo fix in `docs/expiry.md`.

## Live demo moments

1. **Why-trace before the reversal.** Ask "Why do we cache links in Redis?" → Lore shows the PR 1 decision → closes #1 → you proposed, reviewer approved, plus ADR 0001.
2. **Paper owner.** Module page for `analytics/`: CODEOWNERS says the reviewer; the real expert is Priya. `storage/`: listed owner is you; the only expert is Marta (bus factor 1).
3. **Live triage.** During the demo, open a new issue:
   *"Links with capital letters 404 in the mobile app. Opening /Xk9fT2a from the iOS app shows 'not found'; the same link works on desktop."*
   Expected draft from Steward: likely related to #3 (closed by PR 3, same `api/` module), suggested owner you (CODEOWNERS + active expert), suggested reviewer the reviewer. Approve it and the comment appears on GitHub.
   Backup issue for the paper-owner angle: *"Yesterday's clicks are missing from the CSV export"* → related #4 and #9, suggested expert Priya, with a note that the CODEOWNERS owner hasn't touched `analytics/`.
4. **Reversal.** Merge PR 6. After the sync, ask the same "Why do we cache links in Redis?" question: Lore says that decision was superseded by PR 6's decision and shows both. Then "What changed since I last asked?" lists it.

## Order of work on Oct 15

1. Create the public repo `lore-sandbox` with the README and CODEOWNERS (ask your reviewer first if using their login).
2. Have Claude Code generate the stub files.
3. Open issues 1–10.
4. Create PRs 1–5 in order with the commit authors above; get approvals; merge them so they close their issues.
5. Open PR 6 as a draft and leave it unmerged.
6. Add the extra plain commits.
7. Run the M2 fetch on the sandbox first.

## Sandbox golden checks

These go into `docs/golden_set.yaml` under `sandbox`:

- **s01 (why):** "Why do we cache links in Redis?" Before PR 6: shared cache because per-replica caches went cold on deploys and edits went stale; rejected in-process LRU + pub/sub; cites PR 1, #1, ADR 0001. After PR 6: that decision is superseded; now in-process LRU because of the p99 regression (#6) and single-region setup; cites PR 6, ADR 0003.
- **s02 (owns):** "Who owns analytics?" → CODEOWNERS lists the reviewer, but Priya Raman wrote all the analytics code; ask Priya.
- **s03 (risk):** "Which modules depend on one person?" → `storage/` (only Marta Silva).
