# CodeLeet bot

A Slack bot for Codebase's **#codeleet** channel. Every morning it pings the channel to solve a problem. Members log
solves with a screenshot and earn points. At night it boos whoever skipped, and on Sundays it posts a weekly recap.

It's separate from CodeCompBot: it has its own Slack app, Render service and database, and never touches the team
competition.

- [How members use it](#how-members-use-it)
- [One-time setup](#one-time-setup)
- [Changing settings](#changing-settings)
- [Troubleshooting](#troubleshooting)
- [Developing locally](#developing-locally)
- [How the code is organized](#how-the-code-is-organized)

---

## How members use it

The bot only works in one channel (set by `LEET_CHANNEL_ID`). Messages must start with `leet`; upper/lower case and
extra spaces don't matter.

| Message | What happens |
|---|---|
| `leet Two Sum easy` + screenshot, as a **reply in the daily thread** | Logs the solve and reacts ✅ |
| `leet board` | This week's leaderboard (Mon–Sun, Pacific): rank, name, points, current streak 🔥 |
| `leet board all` | All-time leaderboard |
| `leet me` | Your weekly and all-time points, problems by difficulty, current and best streak |
| `leet help` | Usage reminder |
| `leet add @person 2 forgot to log` | **Admins only.** Gives points, with a reason |
| `leet remove @person 3 fake screenshot` | **Admins only.** Takes points away, with a reason |

Typos like `leet bord` or `leet borad` still work, and so do aliases: `leet lb`, `leet leaderboard`, `leet stats`.

**Logging solves**
- **Points:** Easy = 1, Medium = 2, Hard = 3. Short forms work: `e`/`ez`, `m`/`med`/`mid`, `h`.
- **No difficulty given:** counts as Easy, and the bot replies with a reminder.
- **Screenshot required:** an image must be attached. Without one there are no points and the bot asks for it.
- **Daily threads only:** a solve only counts as a reply in the bot's morning post. Before the 9am ping you can reply
  in yesterday's thread, and it counts for today. Threads older than that don't count.
- **Any problem from any site counts**, and you can log several per day.
- **No double-dipping:** the same person can't score the same problem twice. Duplicates get a 🔁 reaction and no
  points. Names are compared ignoring case, spacing, punctuation and leading numbers, so `1. Two Sum` = `two sum`.
  Spelling still has to match: `Two Sums` counts as a different problem.

**Scheduled posts** (times are set in cron-job.org, see [setup](#5-cron-joborg-scheduled-posts))
- **9:00am Pacific:** `@channel` ping with LeetCode's daily problem. This post is the day's thread. If LeetCode can't be
  reached, it posts the ping without the problem.
- **10:00pm Pacific:** names of people who didn't log a solve today (plain names, no @-mentions). Only people who have
  logged at least one solve ever are included, so lurkers aren't called out. If everyone solved, it celebrates instead.
- **Sunday 9:00pm Pacific:** top 3 by points this week, plus the longest active streak.

**Streaks** count consecutive Pacific days with at least one logged solve. A streak isn't broken until a whole day
passes with no solve.

---

## One-time setup

You need accounts on Slack (permission to add apps to the Codebase workspace), GitHub (the Codebase org),
[Neon](https://neon.tech), [Render](https://render.com) and [cron-job.org](https://cron-job.org). All are free.

Do the steps in order. Keep the values you collect somewhere private, such as a password manager. Never paste tokens
into Slack or commit them to GitHub.

### 1. Neon (database)

1. In Neon, create a project named `codeleet`. Pick region **US West (Oregon)**, the same region as Render.
2. Click **Connect** and copy the connection string (`postgresql://…?sslmode=require`). This is `DATABASE_URL`.

The bot creates its tables automatically the first time it starts.

### 2. Slack app

1. Go to <https://api.slack.com/apps> → **Create New App** → **From a manifest** → pick the Codebase workspace.
2. Paste the contents of [`manifest.json`](manifest.json) (JSON tab) → **Next** → **Create**.
3. Click **Install to Workspace** → **Allow**. If your workspace needs admin approval, ask a workspace admin.
4. **OAuth & Permissions** → copy the **Bot User OAuth Token** (`xoxb-…`). This is `SLACK_BOT_TOKEN`.
5. **Basic Information** → **App Credentials** → copy the **Signing Secret**. This is `SLACK_SIGNING_SECRET`.

The manifest grants these permissions:

| Scope | Why |
|---|---|
| `channels:history`, `groups:history` | Read messages in public/private channels the bot is in (private is for the test channel) |
| `chat:write` | Post and reply |
| `reactions:write` | React ✅ / 🔁 |
| `users:read` | Look up display names for boards and the boo list |

You also need:
- **Channel ID:** open the channel → click its name → the ID (`C…`) is at the bottom of the **About** tab. This is
  `LEET_CHANNEL_ID`. Use a **private test channel** first.
- **Admin IDs:** each admin's profile → **⋯** → **Copy member ID** (`U…`). Join them with commas for `ADMIN_SLACK_IDS`.

Invite the bot to the channel by typing `/invite @CodeLeet` there.

### 3. Render (hosting)

1. Push this repo to the Codebase GitHub org.
2. In Render: **New** → **Blueprint** → connect the repo. Render reads [`render.yaml`](render.yaml) and creates a free
   web service called `codeleet-bot`.
3. Fill in the environment variables it asks for: `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, `LEET_CHANNEL_ID`,
   `ADMIN_SLACK_IDS`, `DATABASE_URL`. `CRON_SECRET` is generated for you.
4. Click **Apply** and wait for the deploy to finish. The service URL is shown at the top, e.g.
   `https://codeleet-bot.onrender.com`. Open `<URL>/health` in a browser; it should say `ok`.
5. Open the service → **Environment** and copy the generated `CRON_SECRET`. You need it for cron-job.org.

### 4. Connect Slack to Render

1. Back in the Slack app settings: **Event Subscriptions** → toggle **Enable Events** on.
2. **Request URL:** `https://<your-render-url>/slack/events`. Wait for **Verified ✓**. If it times out, Render was
   asleep; click **Retry** after a minute.
3. Under **Subscribe to bot events**, check that `message.channels` and `message.groups` are listed (add them if
   not), then click **Save Changes**.
4. If Slack shows a banner asking you to reinstall the app, do it.

### 5. cron-job.org (scheduled posts)

Render's free tier sleeps when idle, so it can't keep its own schedule. cron-job.org calls the bot at the right times
instead.

Create three cron jobs. For each one:
- **URL:** as in the table below.
- **Advanced** → **Request method:** `POST`.
- **Advanced** → **Headers:** add `X-Cron-Secret` with the `CRON_SECRET` value from Render.
- **Schedule:** custom, as in the table, with **time zone America/Los_Angeles**. That zone handles daylight saving
  for you.

| Job | URL | Schedule |
|---|---|---|
| Morning ping | `https://<your-render-url>/cron/morning` | Every day, hour 9, **minutes 0 and 5** |
| Boo list | `https://<your-render-url>/cron/evening` | Every day, hour 22, **minutes 0 and 5** |
| Weekly recap | `https://<your-render-url>/cron/weekly` | Sunday only, hour 21, **minutes 0 and 5** |

Why run each one twice? A sleeping Render service takes 30–60 seconds to wake, and cron-job.org gives up after 30. The
:05 run is a backup. Each post goes out **at most once per day**, so when the :00 run worked, the :05 run just replies
`skipped: already posted today`.

Test it now: on each job, click **Test run** (or use the `curl` command in [Troubleshooting](#morning-post-missing)).
You should see `{"ok": true, ...}` and a post in the channel.

### 6. Try it in the test channel, then go live

1. In the test channel: reply to the morning post with `leet Two Sum easy` plus any screenshot, then try
   `leet board` and `leet me`.
2. When you're happy, **wipe the test data**. In Neon → **SQL Editor**, run:
   ```sql
   TRUNCATE solves, adjustments, daily_posts, processed_events;
   ```
3. In Render → **Environment**, set `LEET_CHANNEL_ID` to #codeleet's ID → **Save**. Render redeploys automatically.
4. Invite the bot to #codeleet (`/invite @CodeLeet`). The next 9am cron starts the first real thread. To start one
   right away, run the morning job manually ([how](#morning-post-missing)).

---

## Changing settings

Nothing here requires editing code.

| To change… | Do this |
|---|---|
| **Channel** | Render → Environment → `LEET_CHANNEL_ID` → Save. Invite the bot to the new channel. |
| **Admins** | Render → Environment → `ADMIN_SLACK_IDS` (comma-separated member IDs) → Save. |
| **Post times** | Edit the schedules in cron-job.org. No redeploy needed. Keep the weekly recap on a **Sunday**: it reports the Mon–Sun week of the day it runs. |
| **Cron secret** | Change `CRON_SECRET` in Render (16+ characters; `openssl rand -hex 24` makes one), then update the header on all three cron-job.org jobs. |
| **Database** | Render → Environment → `DATABASE_URL`. |
| **Slack token / signing secret** | Render → Environment → `SLACK_BOT_TOKEN` / `SLACK_SIGNING_SECRET`. |

Saving an environment variable on Render redeploys the bot, which takes about a minute.

Message wording lives in [`leetbot/formatting.py`](leetbot/formatting.py). Points per difficulty and the accepted
short forms live at the top of [`leetbot/parsing.py`](leetbot/parsing.py). Those are code changes: edit, run the
tests, push.

| Environment variable | Required | What it is |
|---|---|---|
| `SLACK_BOT_TOKEN` | yes | Slack bot token (`xoxb-…`) |
| `SLACK_SIGNING_SECRET` | yes | Lets the bot verify requests really come from Slack |
| `LEET_CHANNEL_ID` | yes | The only channel the bot reads and posts in |
| `ADMIN_SLACK_IDS` | no | Comma-separated member IDs allowed to use `leet add` / `leet remove` |
| `DATABASE_URL` | yes | Neon Postgres connection string |
| `CRON_SECRET` | yes | Shared secret cron-job.org sends in the `X-Cron-Secret` header (16+ characters) |

If a required variable is missing, the bot refuses to start and the Render logs say which one.

---

## Troubleshooting

First stop for anything: **Render → codeleet-bot → Logs.** Every error is logged there.

### Bot not responding

1. **Wait a minute.** If nobody has used the bot for 15+ minutes, Render is asleep and the first message takes 30–60
   seconds to wake it. Slack retries automatically, and the bot ignores the duplicates.
2. **Is it running?** Open `<render-url>/health`. If it doesn't say `ok`, check the Render logs. A failed deploy or
   `Missing required environment variables: …` will show there. `invalid_auth` at startup means `SLACK_BOT_TOKEN`
   is wrong, or the app was reinstalled and the token changed. Copy the current token from Slack.
3. **Right channel?** The bot silently ignores every channel except `LEET_CHANNEL_ID`. Check the ID, and check the
   bot is in the channel (`/invite @CodeLeet`).
4. **Is Slack sending events?** Slack app → **Event Subscriptions** should show the Request URL as verified, with
   `message.channels` and `message.groups` subscribed. If you changed scopes or events, **reinstall the app**.
5. **Right message format?** It must start with `leet`. Solves must be replies in the daily thread.

### Morning post missing

1. Check the job's **history** in cron-job.org:
   - **403:** `X-Cron-Secret` doesn't match Render's `CRON_SECRET`.
   - **500:** the bot hit an error. Check the Render logs. `not_in_channel` means invite the bot;
     `channel_not_found` means `LEET_CHANNEL_ID` is wrong.
   - **Timeout:** Render was waking up. The :05 backup run should have posted; check its history too.
2. Post it manually. This is safe to run any number of times; it posts at most once per day:
   ```sh
   curl -X POST -H "X-Cron-Secret: <CRON_SECRET>" https://<your-render-url>/cron/morning
   ```
   It may take a minute if Render is asleep. Replace `morning` with `evening` or `weekly` for the other posts.
   `"result": "skipped: already posted today"` means it already went out; look further up in the channel.
3. **No LeetCode problem in the post?** LeetCode couldn't be reached. The ping still goes out by design; nothing to fix.
4. **Boo list didn't post?** It's skipped until someone has logged at least one solve ever.

Without a morning post, members have no thread to log in. Post it manually and they can reply there.

### Wrong points

- **Fix it with admin commands:** `leet add @person <points> <reason>` or `leet remove @person <points> <reason>`.
  Use this for fake screenshots, wrong difficulties ("said easy, was medium" → `leet add @person 1 was medium`), or
  solves that should have counted. Adjustments change points only, not streaks or problem counts.
- **"My solve didn't count."** It needs all of these: starts with `leet`, an **image** attached (not a PDF or link),
  posted as a **reply in today's or yesterday's** daily thread, and a problem name.
- **Got 🔁 but it wasn't a duplicate.** The names matched after normalizing (e.g. they logged "Two Sum" earlier).
  An admin can `leet add` the points.
- **Look at the raw records.** In Neon → SQL Editor, for example:
  ```sql
  SELECT user_name, problem, difficulty, points, solve_date, created_at
  FROM solves WHERE user_name ILIKE '%alex%' ORDER BY created_at DESC;

  SELECT * FROM adjustments ORDER BY created_at DESC;
  ```
  Prefer admin commands over editing rows by hand, so every change keeps a reason.

---

## Developing locally

You need Python 3.12+ and a Slack app pointed at your machine. A second "CodeLeet (dev)" app with your own test
channel is safest.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env        # fill in values; never commit .env
set -a; source .env; set +a
python app.py               # http://localhost:3000

ngrok http 3000             # in another terminal; use the https URL + /slack/events as the Request URL
```

**Tests**

```sh
pytest                                                  # logic tests only; database tests are skipped
TEST_DATABASE_URL=postgresql://localhost/leetbot_test pytest   # everything
```

`TEST_DATABASE_URL` **wipes its tables on every test**. Point it at a throwaway local database or a Neon branch made
for testing, **never** at the live `DATABASE_URL`.

---

## How the code is organized

| File | What it does |
|---|---|
| `app.py` | Entry point (`gunicorn app:flask_app`) |
| `leetbot/config.py` | Reads and checks environment variables |
| `leetbot/web.py` | HTTP routes: `/slack/events`, `/cron/<job>` (checks the secret), `/health` |
| `leetbot/handlers.py` | Handles `leet …` messages: solves, boards, stats, admin adjustments |
| `leetbot/posts.py` | The morning, evening and weekly posts |
| `leetbot/parsing.py` | Understands message text: commands, difficulty words, problem-name normalizing |
| `leetbot/stats.py` | Streaks and ranking |
| `leetbot/store.py` | All database queries and the table definitions |
| `leetbot/formatting.py` | The wording of every message |
| `leetbot/leetcode.py` | Fetches LeetCode's daily problem |
| `leetbot/dates.py` | Pacific-time days and Mon–Sun weeks |

**Data.** Each solve is its own row in `solves` (person, problem, difficulty, points, Pacific date, Slack message).
Admin fixes go in `adjustments`. Boards add the two together. `daily_posts` records each day's scheduled posts: it
stops cron retries from double-posting and tells the bot which threads are daily threads. `processed_events` stops
Slack's retries from being handled twice. Its rows are cleared after 7 days.
