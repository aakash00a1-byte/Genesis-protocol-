# Instagram publisher: setup, permissions and limits

This document covers `genesis_protocol/instagram/`, a module that publishes
content to an **Instagram professional account** through Meta's official API,
with an owner approval gate, duplicate protection, a content calendar and an
audit trail.

Everything below was checked against Meta's own documentation on **2026-11-25**,
and every claim carries the sentence it came from. Where Meta's documentation
does not answer a question, this document says so instead of guessing.

---

## 1. What this module does, and what it refuses to promise

| Capability | Status | Basis |
|---|---|---|
| Publish an image post | implemented | container + `media_publish` flow |
| Publish a video post | implemented | `media_type=VIDEO` |
| Publish a reel | implemented | `media_type=REELS` |
| Publish a story (image or video) | implemented, account must be eligible | `media_type=STORIES` |
| Publish a carousel of 2-20 items | implemented | `media_type=CAROUSEL` + `children` |
| Schedule a post | **ours**, not Meta's | no scheduling parameter exists in the API |
| Upload media bytes to Meta | **not supported by Meta** | Meta fetches the media URL itself |
| Publish to a personal Instagram account | **not supported by Meta** | platform serves professional accounts |
| Serve a client with no role on the app | **needs App Review first** | Standard vs Advanced Access |
| Read insights/analytics | not in this module | needs an extra permission (`instagram_manage_insights` / `instagram_business_manage_insights`) |

---

## 2. Who can use the API at all

> "The Instagram Platform is a collection of APIs that allows your app to access
> data for Instagram professional accounts, including business and creator
> accounts."
> — <https://developers.facebook.com/docs/instagram-platform/overview>

There are three setups, all of which this module can talk to (the Graph host
differs):

> "There are three Instagram API setups: Instagram API with Unified Login is
> recommended for new integrations. App users can connect their Instagram
> professional account by logging in with either Instagram or Facebook, without
> a Facebook Page."
> — <https://developers.facebook.com/docs/instagram-platform/overview>

> "Instagram API with Instagram Login serves Instagram professional accounts
> without requiring a linked Facebook Page."
> — <https://developers.facebook.com/docs/instagram-platform/overview>

> "Instagram API with Facebook Login serves Instagram professional accounts
> linked to a Facebook Page."
> — <https://developers.facebook.com/docs/instagram-platform/overview>

In code: `login_type="instagram_login"` targets `graph.instagram.com`,
`login_type="facebook_login"` targets `graph.facebook.com` and requires a
`page_id`.

**A personal (non-professional) Instagram account cannot publish through this
API at all.** A client must first convert to a business or creator account -
that is a client-side action in the Instagram app, not something this module can
do.

---

## 3. Exact permissions

From the permission table in the content-publishing guide
(<https://developers.facebook.com/docs/instagram-platform/content-publishing>):

> "Login Type Facebook Login for Business Business Login for Instagram Facebook
> Login for Business Permissions instagram_basic instagram_content_publish
> instagram_business_basic instagram_business_content_publish instagram_basic
> instagram_content_publish pages_read_engagement"

Read as a matrix (the table flattens badly in text form; the three columns are
the three login types):

| Setup | Permissions to request |
|---|---|
| Instagram API with Instagram Login | `instagram_business_basic`, `instagram_business_content_publish` |
| Unified Login / Facebook Login for Business | `instagram_basic`, `instagram_content_publish` (+ `pages_read_engagement` when the account is reached through a Page) |

The Unified Login permissions page confirms the mapping between the old and new
names:

> "You use today Request for the Instagram API with Unified Login
> instagram_business_basic instagram_basic instagram_business_content_publish
> instagram_content_publish ..."
> — <https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login/permissions>

**For this module the only publishing permission that matters is
`instagram_content_publish` (or `instagram_business_content_publish` for
Instagram Login).** Nothing here needs messaging, comment or insights scopes.

---

## 4. Standard Access vs Advanced Access - the sentence that decides your
   business model

> "When you save your configuration, your app gets Standard Access to its
> permissions. Standard Access lets you test with people who have a role on your
> app. To connect clients who don't have a role on your app, your app needs
> Advanced Access to each permission, granted through App Review, and your app
> must be in Live mode."
> — <https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login/permissions>

> "If your app will be used by anyone without a Role on the app or a role in a
> Business that has claimed the app, it must first undergo App Review. If your
> app will only be used by app users who have a role on the app itself, App
> Review is not required."
> — <https://developers.facebook.com/docs/app-review>

Consequences for a paying client:

* while the app is in development / Standard Access, **only accounts with a role
  on the app can be published to** - i.e. your own test account, not a client's;
* a real client account needs **Advanced Access + App Review + Live mode**;
* the client side also needs:
  > "What your clients need A Facebook account or an Instagram professional
  > account to log in with Access to the business portfolio that owns the
  > Instagram assets"
  > — <https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login/eligibility-and-troubleshooting>

This is the single largest remaining blocker before a first paying client, and
it is a review process, not a coding task.

---

## 5. Tokens

> "Native mobile apps using Facebook's SDKs get long-lived User access tokens,
> good for about 60 days."
> — <https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived>

The module therefore treats every token as expiring:

* `InstagramAccount.token_expires_at` is stored per account;
* `inspect_token()` reports `present`, `expired`, `days_left` and
  `needs_rotation` (7-day window) **without ever returning the value**;
* `assert_usable()` refuses to publish on an absent or expired token, before any
  network call;
* publishing status (`status` / `GET /api/...`) never contains the token.

Server-side proof (recommended, optional here):

> "Access tokens are portable." … "If this setting is enabled, all
> client-initiated calls must be proxied through your backend where the
> appsecret_proof parameter can be added to the request before sending it to the
> Graph API, or the call will fail."
> — <https://developers.facebook.com/docs/graph-api/securing-requests>

Set `IG_APP_SECRET` (or a per-account `app_secret_env`) and the client adds
`appsecret_proof` (HMAC-SHA256 of the token, keyed by the app secret) to every
call.

**Rotating a token:** mint a new long-lived token in the Meta dashboard,
update the environment variable the account names in `token_env`, and update
`token_expires_at` in the accounts file. Nothing else changes; no code edit.

---

## 6. Media must be on a public server

> "We cURL media used in publishing attempts, so the media must be hosted on a
> publicly accessible server at the time of the attempt."
> — <https://developers.facebook.com/docs/instagram-platform/content-publishing>

So the publisher does not accept file uploads - it accepts URLs. `validate_post`
refuses anything that is not `https`, that embeds credentials, or that points at
`localhost`, a private, loopback, link-local or reserved address.

The URL must be reachable **at publish time**, not merely when the post was
queued - which is why the calendar stores the URL and the scheduler re-validates
at publish time.

---

## 7. Limits - and a contradiction in Meta's own documentation

Two different numbers appear in the same content-publishing guide:

> "Instagram accounts are limited to 100 API-published posts within a 24-hour
> moving period. Carousels count as a single post. This limit is enforced on the
> POST /<IG_ID>/media_publish endpoint when attempting to publish a media
> container."
> — <https://developers.facebook.com/docs/instagram-platform/content-publishing>

> "Accounts are limited to 50 published posts within a 24-hour period.
> Publishing a carousel counts as a single post."
> — <https://developers.facebook.com/docs/instagram-platform/content-publishing>
> (carousel limitations section)

**We do not guess which is current.** The module enforces its own conservative
cap - `HARD_DAILY_CAP = 25` per account per rolling 24 hours, further lowered by
`daily_cap` on the account record - so a client cannot reach either ceiling.
Meta still enforces the real limit server-side; if it refuses, the publish fails
loudly and is not retried.

Meta's quota endpoint is also read for observability:

> "/<IG_ID>/content_publishing_limit — check app user's current publishing rate
> limit usage."
> — <https://developers.facebook.com/docs/instagram-platform/content-publishing>

The exact JSON shape of that response is **not** asserted by this module: a
payload it does not recognise is reported as empty and never blocks a publish.

---

## 8. The publishing flow

> "/<IG_ID>/media_publish — publish uploaded media using their media containers."
> … "/<IG_CONTAINER_ID>?fields=status_code — check media container publishing
> eligibility and status."
> — <https://developers.facebook.com/docs/instagram-platform/content-publishing>

> "we recommend … querying a container's status once per minute, for no more
> than 5 minutes"
> — <https://developers.facebook.com/docs/instagram-platform/content-publishing>

Implemented in `Publisher`:

1. validate the post and the account (no network);
2. check the token (no network);
3. check the duplicate ledger (no network);
4. check the local daily cap (no network);
5. verify the owner approval token (no network);
6. `POST /<IG_ID>/media` → container id (retried on transient failures only);
7. poll `GET /<CONTAINER_ID>?fields=status_code` until `FINISHED`
   (default: once a minute, five-minute ceiling);
8. `POST /<IG_ID>/media_publish` → media id;
9. record the fingerprint, write the audit entry, return the post id.

A carousel creates one container per item (with `is_carousel_item=true`), polls
each, then a `CAROUSEL` container whose `children` is the comma-separated list.

> "children — A comma separated list of up to 20 container IDs of each image and
> video that should appear in the published carousel."
> — <https://developers.facebook.com/docs/instagram-platform/content-publishing>

---

## 9. Stories

> "media_type — If the container will be for a video, set to VIDEO , REELS , or
> STORIES ."
> — <https://developers.facebook.com/docs/instagram-platform/content-publishing>

> "Story posts To publish a reel, create a container for the media object and
> include the media_type parameter set to STORIES ."
> — <https://developers.facebook.com/docs/instagram-platform/content-publishing>
> (quoted exactly; "reel" appears to be a typo in Meta's page)

Two honest limits:

* Meta's guide documents stories for professional accounts but exposes no cheap
  "is this account eligible for stories?" endpoint, so eligibility is not
  pre-checked. `InstagramAccount.stories_supported` records the expectation, and
  a refusal comes back as Meta's own error, surfaced verbatim.
* **alt text is not allowed on stories or reels**:

  > "On March 24, 2025, we introduced the new alt_text field for image posts on
  > the /<INSTAGRAM_PROFESSIONAL_ACCOUNT_ID>/media endpoint. Reels and stories
  > are not supported."
  > — <https://developers.facebook.com/docs/instagram-platform/content-publishing>

  `validate_post` refuses `alt_text` on `STORY` and `REEL` rather than sending a
  parameter Meta documents as unsupported.
* stories take **no caption** in the publishing parameters, so a caption on a
  story is dropped (documented in code, asserted by a test).

---

## 10. Scheduling is ours, because Meta has none

There is **no** "publish at" parameter in the Instagram content-publishing API.
Meta explicitly leaves scheduling to the app:

> "We recommend that your app also enforce the publishing rate limit, especially
> if your app allows app users to schedule posts to be published in the future."
> — <https://developers.facebook.com/docs/instagram-platform/content-publishing>

So scheduling is a durable JSON calendar plus an explicit drain
(`ContentCalendar` + `run_due`), never a background timer:

* `python3 scripts/instagram.py schedule ... --at 2026-12-01T09:00:00Z`
* `python3 scripts/instagram.py due` → **dry run** (default)
* `python3 scripts/instagram.py due --live --token <entry_id>=<approval>` → publishes

A due entry with no approval token is reported `awaiting-approval` and stays
`planned`. It is never skipped silently and never published anyway.

---

## 11. Configuration reference

Environment variables (values are never written to disk or logged):

| Variable | Meaning |
|---|---|
| `IG_ACCOUNTS_FILE` | path to the accounts JSON (default `data/instagram_accounts.json`) |
| `IG_LEDGER_FILE` | duplicate ledger (default `data/instagram_published.json`) |
| `IG_CALENDAR_FILE` | content calendar (default `data/instagram_calendar.json`) |
| `IG_APPROVAL_SECRET` | **required** to publish; mints/verifies approval tokens |
| `IG_APP_SECRET` | optional; adds `appsecret_proof` to calls |
| `<account.token_env>` | the access token for one account, e.g. `IG_TOKEN_ACME` |
| `<account.app_secret_env>` | per-account app secret override (default `IG_APP_SECRET`) |
| `GLUTEN_AUDIT_LOG` | the project-wide audit log path (reused, not duplicated) |

Accounts file:

```json
{"accounts": [
  {"account_id": "acme-cafe", "client_id": "acme",
   "ig_user_id": "17841400000000001", "username": "acme.cafe",
   "login_type": "instagram_login",
   "token_env": "IG_TOKEN_ACME",
   "token_expires_at": "2027-01-30T00:00:00Z",
   "daily_cap": 25, "enabled": true}
]}
```

`account_id` is the publishing unit; `client_id` groups accounts per customer.
A publish names exactly one account, and a post whose `client_id` does not match
the account's `client_id` is **refused** - one client's content can never be
posted to another client's account.

---

## 12. Manual setup checklist (every step a human must do)

Nothing below can be done by this repository. All of it is Meta-side or
infrastructure-side.

**Meta app and account**

1. Create a Meta app of type **Business** (a non-business app must be recreated
   as Business; per the Instagram Login getting-started page, Advanced Access
   then requires App Review).
2. Attach the app to a **business portfolio** (the dashboard's "API setup with
   Unified login" tab only appears for a business-owned app).
3. Convert the client's Instagram account to **professional** (business or
   creator).
4. Add the Instagram account's owner as a **tester/role** on the app while in
   Standard Access.
5. Add the **Instagram product** to the app and generate a **long-lived access
   token** for the account (60-day lifetime).
6. Record the **Instagram user id** (`ig_user_id`) and the token's expiry date.
7. Request **Advanced Access** for the content-publishing permission through
   **App Review**, then switch the app to **Live mode** - required before any
   client without a role on the app can be served.
8. Complete the client's business-portfolio access (see the eligibility page's
   "What your clients need").

**Infrastructure**

9. Store the token in the deployment secret store under the name the account
   record references (`token_env`), e.g. `IG_TOKEN_ACME`.
10. Set `IG_APPROVAL_SECRET` (a long random string) wherever the publisher runs.
11. Host media on a **public HTTPS** bucket/CDN; confirm the URL is reachable at
    publish time (Meta fetches it then).
12. Point `IG_ACCOUNTS_FILE` at a file containing the account record.
13. Decide a `daily_cap` per account (default 25, hard ceiling 25).
14. Schedule your own `due --live` run (cron/automation) if you want scheduled
    posts to fire; nothing in this module runs on a timer.
15. Set a reminder to rotate tokens before `token_expires_at`.

**Verification before a client goes live**

16. Publish one real post to a **test** account you control, with a real token,
    and compare the result with the Instagram app.
17. Publish one story and one carousel to the same test account.
18. Confirm the audit log shows `instagram.publish.success` for each.

---

## 13. Security review

| Threat | Control |
|---|---|
| Publishing without the owner's say-so | `ApprovalGate`: HMAC-SHA256 token bound to account + content fingerprint, expiring (default 15 min), constant-time compare, **fails closed** when `IG_APPROVAL_SECRET` is unset |
| Replaying an approval for other content | token covers `account_id` and the content fingerprint; a mismatch is refused |
| Double-posting after a crash or a retry | fingerprint ledger (24h window) + optional idempotency key (30 days), written atomically |
| One client's content landing on another client's account | `Publisher._assert_same_client` refuses any mismatch; account lookup never falls back to a default account |
| Publishing with a dead token | `assert_usable` before any network call; expired tokens never reach Meta |
| Retry storms | retries bounded by attempts, delay cap and deadline; only network/5xx/rate-limit codes retried; validation, auth, duplicate and approval failures never retried |
| Token leaking into logs or API responses | token read from env by name only; `status()` returns booleans/dates; error text is redacted; audit records ids and a fingerprint, never captions or URLs |
| Publishing media Meta cannot fetch | `validate_post` requires public `https`, rejects credentials-in-URL, localhost and private ranges |
| Silent success that never happened | success is only reported when Meta returns a media id; every refusal and failure is audited with its reason |
| Unbounded daily volume | local cap (25) independent of Meta's, plus Meta's own enforcement |

Residual risks, stated plainly:

* a compromised host that holds `IG_APPROVAL_SECRET` **and** the access token
  can publish - the gate protects against unauthorised callers, not against a
  fully compromised server;
* `daily_cap` is per process: two independent deployments sharing one account
  would count separately (Meta's own limit still applies);
* the ledger and calendar are local files; they are not a distributed lock, so
  two hosts publishing the same content at the same moment could both pass the
  duplicate check;
* nothing here verifies that a media URL is *appropriate* content - that stays a
  human review step, which is exactly why approval is mandatory.

---

## 14. Readiness for a first business client

**Not ready to take money yet.** What is ready is the software: publishing flow,
approvals, duplicate protection, retries, audit, calendar, client separation, 119
offline tests. What is missing is entirely outside the code:

1. **App Review / Advanced Access + Live mode** - without it, a client's account
   cannot be served at all (quoted in section 4).
2. **Business verification / business portfolio** - the app must belong to a
   business portfolio.
3. **A real end-to-end publish** against a test professional account with a real
   long-lived token - the only proof that permissions and account setup are
   right.
4. **Token custody** - someone must own rotation every ~60 days.
5. **Media hosting** - a public HTTPS bucket/CDN per client.
6. **Operational scheduling** - a cron/automation that runs `due --live`.

Until 1-3 are done, this is a **fully tested integration that has never touched
a live Instagram account** - and no report can honestly say more than that.
