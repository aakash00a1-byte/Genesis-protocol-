# Hugging Face Spaces Deployment — Genesis Protocol

Lifetime free, full power (web + Telegram bot + auto-updater together).
No credit card required. Only a Hugging Face account (sign up with GitHub).

## Why HF Spaces?

On Render (native Python runtime) only the web server ran — the Telegram bot was not started, so the agent lost its "power". HF Spaces uses the Docker SDK, so `supervisord` runs the **web server + Telegram bot + auto-updater** together, exactly like Railway did.

## Step 1 — Create a HF Space

1. Go to https://huggingface.co/login and sign up with your GitHub account.
2. Click your avatar (top right) → **New Space**.
3. Settings:
   - **Space name:** `genesis-protocol`
   - **License:** MIT
   - **SDK:** **Docker** (this is critical — not Gradio/Streamlit)
   - **Visibility:** Public (Private requires a paid plan for always-on)
4. Click **Create Space**.

## Step 2 — Push your code to the Space

HF Spaces use Git, just like GitHub. Your HF Space is a separate Git repo. Two options:

### Option A: Mirror from GitHub (recommended)

Clone your GitHub repo (with the clean history) and push it to the HF Space:

```bash
# Clone your GitHub repo
git clone https://github.com/aakash00a1-byte/Genesis-protocol-.git
cd Genesis-protocol-

# Add HF Space as a second remote
git remote add hf https://huggingface.co/spaces/YOUR_HF_USERNAME/genesis-protocol

# Tell HF Spaces to use the HF Dockerfile
cp Dockerfile.hf Dockerfile

# Commit and push to HF
git add -A
git commit -m "Configure Hugging Face Spaces deployment"
git push hf main
```

When prompted for credentials, use:
- **Username:** your Hugging Face username
- **Password:** a Hugging Face access token (create one at https://huggingface.co/settings/tokens → "New token" → role: **Write**)

### Option B: Upload files via the HF web UI

In your Space, click **Files** → **Add file** → upload each file. Slower but works without git.

## Step 3 — Add your secrets (API keys)

In your HF Space, go to **Settings** → **Variables and secrets** → **New secret**. Add:

| Secret name | Value | Required? |
|-------------|-------|-----------|
| `GROQ_API_KEY` | Your Groq API key | ✅ Yes (free tier works) |
| `TELEGRAM_BOT_TOKEN` | From @BotFather | ✅ Yes (for the bot) |
| `SECRET_KEY` | Any random string | ✅ Yes |
| `TAVILY_API_KEY` | From https://tavily.com | Optional (web search) |
| `OPENAI_API_KEY` | OpenAI key | Optional |
| `GEMINI_API_KEY` | Gemini key | Optional |
| `ADMIN_PASSWORD` | Admin dashboard password | Optional |

## Step 4 — Wait for build & verify

1. After pushing, HF builds the Docker image (~3-5 minutes).
2. Watch the **Logs** tab in your Space for build progress.
3. When done, your app is live at:
   ```
   https://YOUR_HF_USERNAME-genesis-protocol.hf.space
   ```

## Step 5 — Verify everything is running

- **Web UI:** Open the Space URL → you should see the Genesis login page.
- **Telegram bot:** Send `/start` to your bot on Telegram → it should reply.
- **Logs:** In HF Space → **Logs** → check `web.out.log`, `telegram.out.log`.

## Keeping it always-on

HF Spaces sleep after 48 hours of inactivity on the free tier. Since the Telegram bot polls continuously, the Space stays alive as long as the bot is active. If it does sleep, sending any Telegram message wakes it back up (webhook) or you can ping the URL.

## Troubleshooting

### Build fails with "permission denied"
The Dockerfile creates a non-root `user` (uid 1000) for HF Spaces. Make sure no code writes to root-only paths. Database files use relative paths (`genesis.db`, `./data/`) which resolve to `/app/`.

### Telegram bot not responding
1. Check `TELEGRAM_BOT_TOKEN` is set in HF Space secrets.
2. Check **Logs** → `telegram.err.log` for errors.
3. If you previously set a webhook on Render, clear it:
   ```
   https://api.telegram.org/bot<TOKEN>/deleteWebhook
   ```

### Out of memory
The free tier gives 16 GB RAM. If Telegram + Discord + web + updater is too much, disable Discord (it's already skipped in `supervisord.hf.conf` unless you set `DISCORD_TOKEN`).

### Port issues
HF Spaces requires the app on port **7860**. The `Dockerfile.hf` sets `PORT=7860` and `supervisord.hf.conf` passes it to the web app.
