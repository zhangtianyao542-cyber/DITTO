# DITTO! — Wait, Me Too!

Campus campaign prototype: put up to three interest words on a wall, get matched with **one** other person who picked the same word, send one short note, and only exchange contact details after **both** sides submit.

Live demo: https://belle-travelers-felt-broken.trycloudflare.com/ (temporary tunnel)

---

## What is in here

| File | What it is |
|---|---|
| `server.py` | The whole backend — **pure Python standard library**, no dependencies |
| `test.html` | The app, Chinese |
| `test-en.html` | The app, English (`/en`) |
| `static/collision-animation.html` | Standalone storyboard animation (design exploration, not served by the app) |

Data lives in `data.json` next to `server.py` (created on first write, git-ignored).

## Run it locally

```bash
python server.py 8099
```

- Chinese: http://127.0.0.1:8099/
- English: http://127.0.0.1:8099/en
- On a phone in the same Wi-Fi: `http://<your-lan-ip>:8099/`

The port can also come from the `PORT` environment variable (that is what hosting platforms set).

## How matching works

1. You post up to 3 words → you get a card number (`#1001`). There is no name, no photo, no profile.
2. The wall shows how many cards carry each word.
3. Tapping one of your words opens **that word's space** — only that word's conversations.
4. Sending a note picks **one** other real person who has that word. They see one prompt and can accept or stay silent.
5. Accepting opens a chat. Contact details are exchanged **per conversation, symmetrically**: neither side sees the other's handle until both have submitted.
6. Declining is silent — the other person is never told.

Design rules that are enforced in code:

- a conversation is unique per **(pair, word)** — matching on a new word opens a new conversation
- a note is never routed to somebody you already matched with on that word
- a card is never matched with itself (all of the browser's own cards are excluded)
- only cards seen in the last 5 minutes are matched (no "ghost" cards)
- contact handles are scoped to a conversation, never to a person

## Deploy to Render (free, permanent URL)

1. Push this folder to GitHub (see below).
2. On [render.com](https://render.com) → **New** → **Web Service** → connect the repo.
3. Settings:
   - Runtime: **Python**
   - Build command: `echo no build`
   - Start command: `python server.py $PORT`
   - Instance type: **Free**
4. Deploy. You get `https://<name>.onrender.com/`.

Notes:

- The free instance sleeps after ~15 minutes without traffic; the first request afterwards takes ~40 s to wake. Open the site once before an event.
- `data.json` survives restarts but **not** a redeploy (the disk is ephemeral). For a longer pilot, add a Render disk or a Postgres instance.

## Push to GitHub

```bash
cd DITTO-repo
git init
git add .
git commit -m "DITTO! campaign prototype"
git branch -M main
git remote add origin https://github.com/<your-username>/ditto.git
git push -u origin main
```

Create the empty repository on GitHub first (no README, no .gitignore — this folder already has them).

If Git asks for a password, paste a **Personal Access Token** instead (GitHub → Settings → Developer settings → Personal access tokens → `repo` scope).

## Privacy

- no accounts, no emails, no analytics, no cookies
- the only identifier is a random card number
- contact details are stored per conversation and only released when both sides submit
- delete `data.json` to wipe everything

## Licence

Coursework prototype — Taylor's University Major Project.
