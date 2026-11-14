# Facebook and Instagram login for the viral-post sweep

Instagram shows a login wall to every visitor, and Facebook loads only the first post of a hashtag page without a login
(measured 13 Nov 2026). So the Sources sweep reads both with a **saved browser login** of a throwaway account, kept as the GitHub
secret `PW_STORAGE_STATE_B64` (the same secret name the KKM complaint scraper uses, in its own repo). One file holds both logins.

**Use accounts you can lose.** Meta can lock or ban an account that is used by a script. Never use ws.regulab, Valorith,
FACERINNA or your personal account (rule: those are never touched).

## 1. One-time setup on your own computer (Windows or Mac)

1. Install **Python 3.12** from python.org (tick "Add python.exe to PATH" on Windows).
2. Open a terminal (Windows: PowerShell) in the `backend` folder of the Semasa repo (Code, Download ZIP, or `git clone`), then:

   ```
   python -m venv .venv
   .venv\Scripts\activate          (Mac/Linux: source .venv/bin/activate)
   pip install playwright
   python -m playwright install chromium
   ```

## 2. Log in once, in a window Playwright records

```
python -m playwright codegen --save-storage=storage_state.json https://www.instagram.com/
```

A browser and a small inspector window open.

1. **Instagram**: log in to the throwaway Instagram account. Complete any "is this you", e-mail or SMS code prompt. Wait until
   you can see the home feed. If Instagram asks to "Save login info", say yes.
2. **Facebook**: in the same browser window, go to `https://www.facebook.com/`, log in to the throwaway Facebook account, complete
   any checkpoint, wait until the feed shows.
3. Visit nothing else. The checker keeps only the Facebook and Instagram cookies and drops the saved page data (Facebook's alone can be 80 KB), so the text it writes for the secret is usually well under GitHub's 48 KB limit.
4. **Close the browser window.** `storage_state.json` is written when it closes.

Use a throwaway Facebook account on its own: do **not** use "Log in with Facebook" on Instagram, so the two logins stay separate.

## 3. Check it works, before you upload anything

```
python -m semasa.social_check storage_state.json --b64 secret.txt
```

It opens the same pages the sweep opens, with your login, and prints one line per platform. It never prints a cookie.

| You see | Meaning | Do |
|---|---|---|
| `Facebook: OK, 6 post(s) read.` and `Instagram: OK, 5 post(s) read.` | Both work | Go to step 4 |
| `... LOGIN WALL ...` | Session expired, refused, or a security prompt is pending | Log in again in a fresh codegen window and finish every prompt |
| `... has no Instagram login (sessionid ...)` | You did not log in to that platform in the window | Log in to it, close, save again |
| `... logged in, but no posts came back` | The login works; that hashtag was empty | Run again with another hashtag: `python -m semasa.social_check storage_state.json sijilhalal` |
| `Base64 size ... STILL TOO LARGE` | Even the login cookies alone are over 48 KB (rare) | Delete `storage_state.json`, log in again in a fresh codegen window visiting only the two sites |

## 4. Save it as the secret

1. Open `secret.txt` (written by `--b64`), select **all** of it and copy. (Or: Mac `base64 -i storage_state.json | pbcopy`;
   PowerShell `[Convert]::ToBase64String([IO.File]::ReadAllBytes("storage_state.json")) | Set-Clipboard`.)
2. GitHub, repo `wanshah07/semasa`, **Settings, Secrets and variables, Actions, New repository secret**.
3. Name: `PW_STORAGE_STATE_B64`. Value: paste. Save.
4. Delete `storage_state.json` and `secret.txt` from your computer, or keep them somewhere private: they are the logins.

## 5. Prove it on the runner

Actions, **Sources**, **Run workflow**, only = `community`, dry = false. In the run's summary, `community: read={... 'facebook': N,
'instagram': N ...}` should show numbers above 0, and the Facebook and Instagram tabs in Isu semasa fill in. If a tab's problem
card says "asked for a login", the runner's session was refused (see below).

## What can still go wrong

- **A datacenter address.** The sweep runs on GitHub's servers, not your home connection. Instagram sometimes refuses a session it
  first saw at home when it suddenly appears from a datacenter (a "suspicious login" check). If step 3 passes but step 5 shows a
  login wall, that is why. The fix is to run the reader from a home or office computer on a schedule (the KKM scraper's "Option B"),
  which is a separate job: tell Claude.
- **Sessions expire.** Instagram and Facebook logins usually last weeks to months. When the tab says "asked for a login", repeat
  steps 2 to 4.
- **The accounts get flagged.** Expected sometimes. Make a new throwaway account and repeat.
- **Instagram changes its page.** The reader will then return zero posts while the login still passes. Tell Claude the line the
  checker printed.
- **Do not put the secret in chat, in the repo or in a screenshot.** It is a login.
