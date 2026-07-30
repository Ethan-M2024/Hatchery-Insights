# Security

## Threat model

This project reads a web page it does not control (`wdfw.wa.gov`), turns links on
that page into filenames on your computer, downloads files, parses them, and builds
an HTML page you open in your browser. The untrusted side of that boundary is
everything WDFW's site returns — and by extension anyone who can tamper with it: a
compromised CMS, a hijacked DNS answer, a proxy on a café or hotel network.

The design rule is that **nothing on the far side of that boundary may choose where a
file lands, which host is contacted, how much is read, or what code runs.**

Nothing here handles credentials, and the dashboard stores nothing in your browser.

---

## Audit, 2026-07-28

Ten issues were found and fixed. Severity is judged by what an attacker who could
tamper with WDFW's page — or intercept the connection — could achieve.

### 1 · Arbitrary file write outside the download folder — CRITICAL · fixed

`weekly_filename()` replaced `/` with `__` **before** URL-decoding, so a percent-
encoded traversal survived the sanitising and came back as real separators:

```
href="/sites/default/files/%2e%2e%2f%2e%2e%2f%2e%2e%2f%2e%2e%2f.ssh%2fauthorized_keys"
  -> "../../../../.ssh/authorized_keys"
  -> wrote outside the download folder
```

A single crafted link could drop a file into `~/.ssh/authorized_keys`, `~/.bashrc`,
`~/.zshrc`, or the Windows Startup folder — remote code execution on your machine the
next time you opened a shell or logged in.

**Fixed** in `src/safety.py`: `safe_filename()` decodes repeatedly *first* (defeating
double-encoding), strips NULs, takes the basename, then reduces the result to
`[A-Za-z0-9._-]`. `resolve_within()` then re-resolves the joined path and refuses to
return it unless it is genuinely inside the intended folder. Windows device names
(`CON`, `PRN`, `LPT1`…) are prefixed so they cannot be created either.

### 2 · Redirects followed to any host, including plain HTTP — HIGH · fixed

`urllib` follows redirects anywhere by default. A `302` from `wdfw.wa.gov` to
`http://attacker.example/payload.pdf` would have been fetched silently, defeating the
fact that every URL in the source starts out HTTPS.

**Fixed**: `_StrictRedirectHandler` re-checks every hop against an explicit host
allow-list (`wdfw.wa.gov`, `geodataservices.wdfw.wa.gov`) and rejects non-HTTPS.
Verified: `http://`, `file://`, `evil.example.com` and the look-alike
`wdfw.wa.gov.evil.com` are all refused.

### 3 · Unbounded response read — HIGH · fixed

`get()` called `r.read()` with no ceiling. A hostile or malfunctioning server could
stream indefinitely and exhaust memory, then disk.

**Fixed**: `safety.fetch()` checks `Content-Length`, reads in 64 KB chunks, and
aborts past 96 MB (the largest real report is about 9 MB).

### 4 · Decompression bomb — MEDIUM · fixed

The shipped `data/*.csv.gz` are read with no limit on expanded size. A malicious pull
request could have replaced one with a bomb that fills the disk of anyone who ran an
update.

**Fixed**: gzip reads go through `safety.bounded_reader()`, which raises past 512 MB.

### 5 · KML injection via `]]>` — MEDIUM · fixed

The KML export wrapped facility text in `<![CDATA[ … ]]>`. XML entity-escaping does
not protect a CDATA section, so a value containing `]]>` would close it early and the
rest would be parsed as live KML markup — injecting placemarks, or arbitrary content,
into a file you might forward to a colleague.

**Fixed**: CDATA removed; descriptions are entity-escaped like every other field.

### 6 · `javascript:` URL sink in the page — MEDIUM · fixed

The footer did `a.href = m.repo`, taking a URL straight from the embedded payload. If
that payload were ever tampered with, `javascript:…` would execute on click.

**Fixed**: URLs are parsed and only accepted when the resolved protocol is `https:`.

### 7 · Unpinned dependency — MEDIUM · fixed

`pdfplumber>=0.10` meant every update installed whatever was newest on PyPI. One
compromised release — an all-too-common supply-chain attack — would have run on your
machine the next time you double-clicked the updater.

**Fixed**: `requirements.lock.txt` pins the whole resolved tree (8 packages) by
SHA-256, for every platform, and the launchers install with `--require-hashes`.
Verified: corrupting a hash makes pip refuse the package outright.
Regenerate deliberately with `python src/lock_requirements.py`.

### 8 · Unpinned GitHub Actions — MEDIUM · fixed

`actions/checkout@v4` is a *mutable tag*. Whoever controls that repository can
repoint it at new code, which then runs with the workflow's `contents: write` token.

**Fixed**: both actions pinned to full commit SHAs, with the version in a comment.

### 9 · Weekly workflow could commit code changes — MEDIUM · fixed

The refresh job holds a write token. It only ever *should* touch `data/` and `docs/`,
but nothing enforced that.

**Fixed**: a step now fails the run if anything outside `data/` and `docs/` differs,
before the commit step is reached. The workflow has no `pull_request_target` trigger
and interpolates no untrusted input into `run:` blocks.

### 10 · No Content-Security-Policy — LOW · fixed

The page loads no external resources by design, but nothing enforced it.

**Fixed**: `default-src 'none'` with only inline script/style, `data:` images and
fonts, `form-action 'none'`, `base-uri 'none'`, plus `referrer: no-referrer`.
If the page is ever modified to call out to a third party, the browser blocks it.

---

## Verified clean

- **No secrets, tokens or keys** anywhere in the working tree or in git history.
- **No local filesystem paths** or personal data in any committed file, including the
  run log that was removed in an earlier commit.
- **The dashboard makes zero network requests.** Every `http(s)://` string in it is an
  XML namespace identifier or a link you click deliberately. No CDN, no web font, no
  analytics, no tracker.
- **Nothing is stored in your browser** — no cookies, no `localStorage`, no
  `sessionStorage`, no IndexedDB. This matters because GitHub Pages serves all of a
  user's repositories from one origin (`ethan-m2024.github.io`), so anything stored
  would be readable by any other page there.
- **All export files are generated locally** in your browser. Nothing is uploaded.
- **No `eval`, `new Function`, `innerHTML`, `document.write`** or string-argument
  `setTimeout` in the page; all text goes into the DOM via `textContent`.
- **No `subprocess`, `eval`, `exec`, `pickle`, or shell interpolation** in the Python.
  The parse cache is JSON, never pickle — pickle would be straightforward RCE.

## Hosts this project will contact

The allow-list in `src/safety.py` is the whole of it; anything else is refused, and a
redirect to anything else is refused too:

| Host | Why |
|---|---|
| `wdfw.wa.gov` | the escapement reports |
| `geodataservices.wdfw.wa.gov` | WDFW hatchery locations |

Each entry is a deliberate decision. Adding one widens the attack surface of every
update, so the list is short and the reason is recorded beside it.

## What was checked, and what was not

**Checked and clean:** the code in this repository, its git history, the built page,
every export format, the workflow's triggers and token scope, and the pinned
dependency versions against the OSV vulnerability database (no known advisories at
the time of the audit).

**Not audited:** the source of `pdfplumber` and its dependency tree — roughly 50,000
lines across `pdfminer.six`, `pillow`, `cryptography`, `cffi` and `pypdfium2`. Those
are widely used and actively maintained, but they are trusted, not verified, and
`pillow` and `cryptography` have both carried CVEs in the past. Dependabot alerts are
enabled precisely because pinning by hash stops a bad release getting in but also
stops a good one arriving on its own.

**Also not covered by anything in this repository:** the security of the GitHub
account itself. A repository is only as safe as the account that owns it — 2FA, the
scope of any personal access tokens on your machine, and who has write access matter
more than anything in this codebase.

## Residual risks, accepted and stated

- **`pdfplumber` parses files from the internet.** A malicious PDF that exploited a
  parser bug would run with your user's privileges. Mitigated by pinning with hash
  verification and by the host allow-list; not eliminated. Keep the pin current.
- **Clickjacking is not blocked.** `frame-ancestors` only works as an HTTP header and
  GitHub Pages does not let you set one. Impact is negligible: the page is read-only,
  holds no session, and has no state-changing action to hijack.
- **You trust WDFW for the data itself.** These fixes stop a tampered site from
  attacking your computer; they cannot tell you whether the fish counts are honest.
  That is what `src/validate.py` is for — it reconciles every figure against WDFW's
  own published totals and fails the build on a mismatch.
- **Your commit email is public.** `ethannmuhlestein@gmail.com` appears in the git
  history, which is normal for GitHub but not always intended. To use GitHub's
  no-reply address going forward:
  ```
  git config user.email "<your-id>+Ethan-M2024@users.noreply.github.com"
  ```
  (find the exact address under GitHub → Settings → Emails, and tick *Keep my email
  address private*). Rewriting existing history would change every commit hash; that
  is usually not worth it for a public data project.

## Keeping it that way

- **Act on Dependabot alerts.** They are on, and with hashed pins they are the only
  thing that will tell you a dependency has gone bad. Move the pin, then
  `python src/lock_requirements.py`.
- **Do not remove `--require-hashes`** from the launchers to make an install error go
  away. That check is the supply-chain defence.
- **Re-run the exploit tests** after touching `src/safety.py` or `weekly_filename()`.
- **Keep 2FA on the GitHub account** and avoid long-lived personal access tokens with
  `repo` scope where a fine-grained token would do.

## Reporting a problem

Open a private security advisory under the repository's **Security** tab rather than
a public issue.


---

## Second audit — 30 July 2026

A full re-read of the repository after the analytical features landed. Two security
findings, both fixed and verified.

### CSV formula injection in the exports — medium

Every export path built CSV by quoting commas and nothing else. A spreadsheet treats a
cell beginning `=`, `+`, `-` or `@` as a formula, and the DDE form of that trick runs a
shell command on open. Facility and stock names come from PDFs published by someone
else, so a tampered report could have put a live formula into a file you then forward
to a colleague — the payload executes on their machine, not the one that downloaded it.

Fixed with a single `csvCell()` used by both exporters. Text starting with a trigger
gets a leading apostrophe, which spreadsheets strip on display and never evaluate.

Getting the exemption right took two passes. The first version exempted anything
*starting* with a digit so negative numbers stayed numeric — but `-2+3` starts with a
digit and Excel still evaluates it. The guard now exempts only strings that are
entirely a number. Verified across eleven cases with zero misclassifications:
`=cmd|'/c calc'!A1`, `+1+1`, `-2+3`, `@SUM(A1)` and a leading tab are all neutralised,
while `-1234`, `-12.5`, `1998-99` and `Kalama-Falls` pass through untouched.

### The daily job could silently drop hash verification — medium

`refresh.yml` installed from the hash-locked file and fell back to the unpinned
`requirements.txt` on any failure:

```yaml
pip install --require-hashes -r requirements.lock.txt \
  || pip install -r requirements.txt
```

A registry hiccup, a network blip, or an attacker able to fail one request would have
turned off SHA-256 verification on the one job that runs unattended every day, with a
green tick either way. That is precisely the job where a supply-chain substitution
would go unnoticed longest. The fallback is gone: a failure now stops the run.

### Re-verified clean

No secrets, tokens or local paths in the tree or in git history. No `eval`,
`innerHTML`, `document.write`, `subprocess` or `pickle`. Nothing stored in the browser.
Workflow permissions are `contents: write` with no `pull_request_target`, so no fork
can run code against the token. All eight pinned dependencies still carry zero known
CVEs.
