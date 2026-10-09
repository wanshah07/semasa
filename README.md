# Bernard Tan · bernardtan.kkmhalalconsultant.com

Bernard's own app: his Google Drive, his Google Sheets and games, installable on phone, tablet and desktop. React 18 +
Tailwind 3 + TypeScript, built with Vite into plain HTML/CSS/JS, served by GitHub Pages. Plain CSS and plain JS are
welcome: `src/theme.css` is ordinary CSS with Tailwind layered on, and `src/lib/sheet.js` is plain JavaScript.

## What is in it
- **Home**: greeting, the three doors, and the install card (Add to Home Screen on iPhone/iPad; Install app on Android and desktop).
- **Drive**: Bernard's newest files, a name search, open in Google. Read only.
- **Sheet**: pick one of his spreadsheets (or paste a link), read any tab as a table with column sums, add a row.
- **Games**: Burger Tap (canvas + JS) is in; three placeholders for the ones to come.
- **Settings**: day / night, the Google client id, disconnect.

Everything Google runs in **Bernard's own account**, in the browser: Google Identity Services hands the page a one-hour
token, the page calls Drive and Sheets with it, and nothing is stored on any server. The look is a diner cartoon
(ketchup, mustard, lettuce, bun cream, chocolate outlines) inspired by the Bob's Burgers title card's colours and mood;
no character, logo or artwork from the show is used, which keeps it clear of their copyright.

## Set up once (Wan, about 20 minutes)
1. **The repository.** Create `wanshah07/bernardtan` on GitHub (public, empty, no README). Upload this tree. The web
   uploader **silently drops dot-files**: after uploading, check that `.github/workflows/pages.yml`, `.gitignore` and
   `.env.example` are there (upload them in a second pass if not), and that the file count matches.
2. **Pages.** Settings → Pages → Source: *GitHub Actions*. The first push to `main` builds and deploys.
3. **The domain.** At the DNS of `kkmhalalconsultant.com` add `CNAME  bernardtan  →  wanshah07.github.io`. Then
   Settings → Pages → Custom domain: `bernardtan.kkmhalalconsultant.com` → tick *Enforce HTTPS* once the check passes
   (a few minutes to an hour). `public/CNAME` already carries the name so a redeploy never loses it.
4. **Google sign-in (the 5-minute part).** console.cloud.google.com → a project (any) → *APIs & Services*:
   - *Enabled APIs*: enable **Google Drive API** and **Google Sheets API**;
   - *OAuth consent screen*: External, app name "Bernard Tan", your e-mail; add Bernard's Gmail under **Test users**
     (while the app is in "Testing", only test users can sign in; that is fine for one person);
   - *Credentials* → Create → **OAuth client ID** → Web application; *Authorised JavaScript origins*:
     `https://bernardtan.kkmhalalconsultant.com` and `http://localhost:5173`; no redirect URI is needed (token flow);
   - copy the **Client ID** (ends in `.apps.googleusercontent.com`). Either paste it in the app under Settings on each
     device, or put it in GitHub → Settings → Secrets and variables → Actions → **Variables** → `VITE_GOOGLE_CLIENT_ID`
     and redeploy, so it is baked in.
5. Open the site on Bernard's phone, Connect Google, choose his account, allow Drive (read) and Sheets. Add to Home
   Screen. Done.

## Running it locally
```
npm install
npm run dev        # http://localhost:5173
npm test           # the Sheets helpers
npm run build      # type-check + production build into dist/
```

## Where things are
```
index.html                the shell: fonts, manifest, theme before first paint
public/manifest.webmanifest, sw.js, icon*.png, CNAME
src/theme.css             the palette (day + night) and the cartoon card / button / stripe classes — plain CSS
src/App.tsx               hash tabs, header nav (wide) and the thumb bar (phone)
src/lib/google.ts         sign-in, Drive list, Sheets read/append
src/lib/sheet.js          A1 ranges, header rows ↔ objects (plain JS, tested)
src/pages/*.tsx           Home, Drive, Sheet, Games, Settings
.github/workflows/pages.yml
```

## Not done, said plainly
- Writing to Drive (upload) is not in: the scope is read-only on purpose; add `drive.file` when a feature needs it.
- The token lasts an hour and lives in the tab; closing the app means Connect again (one tap, no password when the
  Google session is live). A refresh token would need a server, which this app deliberately does not have.
- The three other games are placeholders.
