# Facebook and Instagram login for the viral-post sweep

Instagram shows a login wall to every visitor, and Facebook loads only the first post of a hashtag page without a login
(measured 13 Nov 2026). So the Sources sweep reads both with a **saved browser login** of a throwaway account, kept as the GitHub
secret `PW_STORAGE_STATE_B64` (the same secret name the KKM complaint scraper uses, in its own repo). One file holds both logins.

**Use accounts you can lose.** Meta can lock or ban an account that is used by a script. Never use ws.regulab, Valorith,
FACERINNA or your personal account (rule: those are never touched).

## 1. Easiest: one file, from any folder (Windows PowerShell or Mac)

Download `ops/instagram_login.py` from the repo (Code, Download ZIP, or open the file, Raw, Save as) into any folder. Then, in a
terminal in that folder, **one line at a time**:

```
python -m pip install playwright
python -m playwright install chromium
python instagram_login.py
```

(`python -m pip` and not `pip`: on Windows `pip` is often not on the PATH. No virtual environment is needed. If `python` is not
found, install **Python 3.12** from python.org and tick "Add python.exe to PATH". **On a Mac the command is `python3`**
(`python3 -m pip install playwright`, `python3 -m playwright install chromium`, `python3 instagram_login.py`), because the
python.org installer does not create a `python` command; use `python3` for the repo route in step 2 too.)

A browser opens. Log in to the throwaway **Instagram** account (finish any code or "is this you" prompt, wait for the feed), press
Enter in the terminal, log in to the throwaway **Facebook** account the same way (not "Log in with Facebook"), press Enter. The
script prints whether each login cookie was found and writes `secret.txt`. Go to step 4. It needs nothing else from the repo.

## 2. Or, with the whole repo: Playwright's recorder, then the checker

Use this only if you have the repo on your computer (Code, Download ZIP, or `git clone`) and want the checker to open the same
pages the sweep opens. In a terminal **inside the repo's `backend` folder** (the checker is `semasa/social_check.py`, so it does
not exist anywhere else):

```
python -m venv .venv
.venv\Scripts\activate          (Mac/Linux: source .venv/bin/activate)
python -m pip install playwright
python -m playwright install chromium
python -m playwright codegen --save-storage=storage_state.json https://www.instagram.com/
```

Log in to Instagram, then Facebook in the same window, close the window (`storage_state.json` is written when it closes), then:

```
python -m semasa.social_check storage_state.json --b64 secret.txt
```

On Windows PowerShell, if `activate` is refused, run `Set-ExecutionPolicy -Scope Process Bypass` once in that window first. It
prints one line per platform and never a cookie:

| You see | Meaning | Do |
|---|---|---|
| `Facebook: OK, 6 post(s) read.` and `Instagram: OK, 5 post(s) read.` | Both work | Go to step 4 |
| `... LOGIN WALL ...` | Session expired, refused, or a security prompt is pending | Log in again in a fresh window and finish every prompt |
| `... has no Instagram login (sessionid ...)` | You did not log in to that platform in the window | Log in to it, close, save again |
| `... logged in, but no posts came back` | The login works; that hashtag was empty | Run again with another hashtag: `python -m semasa.social_check storage_state.json sijilhalal` |
| `Base64 size ... STILL TOO LARGE` | Even the login cookies alone are over 48 KB (rare) | Delete `storage_state.json`, log in again visiting only the two sites |

## 4. Save it as the secret

1. Open `secret.txt` (written by `instagram_login.py` or by `--b64`), select **all** of it and copy. (Or: Mac `base64 -i storage_state.json | pbcopy`;
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
