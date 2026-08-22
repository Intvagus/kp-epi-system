# Deploying the web app to Render.com

Everything code-side is done and tested locally (see "Web app / hosting" in
`CLAUDE.md`). What's left needs your own accounts — creating accounts for
you isn't something I can do. This should take about 10 minutes.

## 1. Push this project to GitHub

A local git repo has already been created here with everything committed
(health-data Excel files are excluded via `.gitignore` — only code is
tracked). You just need to give it a home on GitHub:

1. Go to [github.com/new](https://github.com/new) and create a new repository
   (any name, e.g. `kp-epi-system`). **Private** is fine and recommended —
   Render can deploy from a private repo too.
2. Do **not** check "Add a README" — this project already has one.
3. Copy the repository URL GitHub shows you (looks like
   `https://github.com/<your-username>/kp-epi-system.git`).
4. Run these commands in this project folder:
   ```bash
   git remote add origin https://github.com/<your-username>/kp-epi-system.git
   git branch -M main
   git push -u origin main
   ```
   (GitHub will prompt you to sign in the first time.)

## 2. Create a Render account and connect the repo

1. Go to [render.com](https://render.com) and sign up (free — you can use
   your GitHub account to sign in, which also makes step 3 easier).
2. From the Render dashboard, click **New +** → **Blueprint**.
3. Connect your GitHub account if prompted, then select the repository you
   just pushed.
4. Render will detect `render.yaml` in the repo root automatically and show
   you a preview of the service it's about to create (`kp-epi-generator`,
   Docker runtime, free plan). Click **Apply**.
5. Render will build the Docker image and deploy it — this takes 5-10
   minutes the first time (installing Chromium is the slow part). Watch the
   build logs on the Render dashboard; if it fails, the log will show why.

## 3. Get your link

Once deployed, Render shows a URL like
`https://kp-epi-generator.onrender.com` — that's the link to share with the
team. Open it and confirm the upload page loads.

## Notes

- **Free plan**: costs nothing, but the service goes to sleep after 15
  minutes of no traffic. The next visitor waits ~30-60 seconds for it to wake
  up, then it's normal speed. If that's annoying in practice, switch the
  plan to "Starter" (~$7/month, always-on) in the Render dashboard — no code
  or redeploy needed, just a settings change.
- **Updating the app later**: any time you (or I) change the code, run
  `git add -A && git commit -m "..." && git push` — Render redeploys
  automatically on every push to `main`.
- **No password protection**: this was an explicit choice (see
  `CLAUDE.md` → "Confirmed VPD decisions" history) — anyone with the link can
  upload files and generate a dashboard/bulletin. If you change your mind
  later, adding a simple shared-password gate to `webapp/app.py` is a small
  change, not a rebuild — just ask.
- **First real test of the Dockerfile**: I tested the Flask app itself
  thoroughly on this machine (upload → dashboard + bulletin, full run in
  ~15 seconds), but this machine doesn't have Docker installed, so the
  container build has not been tested locally. If Render's build fails,
  send me the build log and I'll fix it.
