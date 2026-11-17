# Log masuk Nexabot Creator Studio (Fasa A) / Nexabot Creator Studio login (Phase A)

Wan mahu Semasa membuat video dalam Creator Studio di https://nexabot.id/video-generator. Perkhidmatan itu tiada API awam dan
tiada dokumentasi: ia log masuk dengan ID Telegram dan kod sekali guna yang dihantar bot mereka (@aigeneratornexa_bot), atau kod
e-mel. Semasa tidak boleh log masuk untuk Wan dan tidak pernah memegang kod itu. Jadi Wan **merakam sesi pelayarnya sendiri** di
komputernya, dan sesi itu disimpan sebagai rahsia GitHub `NEXABOT_STORAGE_STATE_B64`, sama seperti log masuk Facebook/Instagram
(`ops/SOCIAL-LOGIN.md`).

Wan wants Semasa to make videos in the Creator Studio at https://nexabot.id/video-generator. The service has no public API and no
documentation: it signs in with a Telegram user ID and a one-time code its bot sends (@aigeneratornexa_bot), or an e-mail code.
Semasa cannot log in for Wan and never handles the code. So Wan **records his own browser session** on his own computer, and the
session is stored as the GitHub secret `NEXABOT_STORAGE_STATE_B64`, the same way the Facebook/Instagram login is
(`ops/SOCIAL-LOGIN.md`).

**Fasa A sahaja / Phase A only.** Dalam fasa ini tiada video dibuat. Alat ini hanya (1) merakam dan menyemak sesi, dan (2) membaca
struktur studio supaya Fasa B (menjana dan memuat turun video sebenar) ditulis daripada fakta, bukan tekaan. Probe tidak pernah
menekan Generate.
In this phase no video is made. The tools only (1) record and check the session, and (2) read the studio's structure so Phase B
(generate and download a real video) is written from facts, not guesses. The probe never presses Generate.

## Amaran / Read this first

- **Ini log masuk ke akaun berbayar.** Sesiapa yang memegang fail itu boleh menggunakan baki kredit Wan. Jangan tampal dalam chat,
  dalam repo, atau dalam tangkap layar. / **This is a login to a paid account.** Whoever holds the file can spend Wan's credits.
  Never paste it in chat, in the repo or in a screenshot.
- **Skrip mungkin ditolak, atau sesi mungkin tamat.** Nexabot tidak menjanjikan apa-apa untuk skrip ("No guarantees"). Jika sesi
  ditolak, rakam semula (langkah 2 hingga 4). / **A script may be refused, or the session may expire.** Nexabot promises nothing for
  scripts ("No guarantees"). If the session is refused, record it again (steps 2 to 4).
- **Setiap penjanaan sebenar membelanjakan kredit** (tiada langganan bulanan, kredit dibeli ikut keperluan). Fasa B akan menghadkan
  perbelanjaan: had setiap larian dan had setiap hari, yang Wan tetapkan. Fasa A tidak membelanjakan apa-apa. / **Every real
  generation spends credits** (no monthly plan, credits are bought as needed). Phase B will cap spend: a per-run limit and a
  per-day limit that Wan sets. Phase A spends nothing.
- **Probe hanya membaca.** Ia tidak menekan Generate, Buat, Hasilkan, Kirim, Bayar, Top up atau apa-apa yang boleh membelanjakan
  kredit, tidak menaip dalam kotak prompt, dan membatalkan setiap permintaan POST/PUT/PATCH/DELETE di rangkaian. / **The probe only
  reads.** It never presses Generate, Buat, Hasilkan, Kirim, Bayar, Top up or anything that could spend credits, never types in the
  prompt box, and aborts every POST/PUT/PATCH/DELETE at the network.
- Pakai **akaun Telegram/e-mel Wan sendiri** yang memang memiliki akaun Nexabot itu. Jangan kongsi kod sekali guna dengan sesiapa,
  termasuk Claude. / Use Wan's own Telegram or e-mail account that owns the Nexabot account. Never share the one-time code with
  anyone, Claude included.

## 1. Sekali sahaja: pasang alat di komputer sendiri / One-time setup on your own computer

1. Pasang **Python 3.12** dari python.org (Windows: tandakan "Add python.exe to PATH"). / Install **Python 3.12** from python.org
   (Windows: tick "Add python.exe to PATH").
2. Buka terminal (Windows: PowerShell) dalam folder `backend` repo Semasa, kemudian / Open a terminal (Windows: PowerShell) in the
   `backend` folder of the Semasa repo, then:

   ```
   python -m venv .venv
   .venv\Scripts\activate          (Mac/Linux: source .venv/bin/activate)
   pip install playwright
   python -m playwright install chromium
   ```

## 2. Log masuk sekali, dalam tetingkap yang Playwright rakam / Log in once, in a window Playwright records

```
python -m playwright codegen --save-storage=storage_state.json https://nexabot.id/login
```

Sebuah pelayar dan tetingkap inspektor kecil dibuka. / A browser and a small inspector window open.

1. Dalam pelayar itu, log masuk sendiri: masukkan **ID Telegram** Wan, kemudian kod yang bot hantar di Telegram (atau pilih kod
   e-mel dan masukkan kod dari e-mel). Taip kod itu sendiri, di situ sahaja. / In that browser, log in yourself: enter Wan's
   **Telegram user ID**, then the code the bot sends in Telegram (or choose the e-mail code and enter the code from the e-mail).
   Type the code yourself, there and nowhere else.
2. **Tunggu sehingga Creator Studio terbuka** (alamat `nexabot.id/video-generator`, anda nampak kotak prompt). Jangan tekan
   Generate. / **Wait until the Creator Studio opens** (the address `nexabot.id/video-generator`, you see the prompt box). Do not
   press Generate.
3. Jangan lawat laman lain. Penyemak hanya menyimpan kuki nexabot.id, dan data halaman nexabot.id jika kecil. / Visit no other
   site. The checker keeps only the nexabot.id cookies, and nexabot.id's saved page data if it is small.
4. **Tutup tetingkap pelayar.** `storage_state.json` ditulis apabila ia ditutup. / **Close the browser window.**
   `storage_state.json` is written when it closes.

## 3. Semak sebelum memuat naik / Check it before you upload anything

```
python -m semasa.nexabot_check storage_state.json --b64 secret.txt
```

Ia membuka `nexabot.id/video-generator` dengan sesi itu, hanya membukanya, dan mencetak **satu baris keputusan**. Ia mencetak nama
kuki sahaja, tidak pernah nilainya. / It opens `nexabot.id/video-generator` with that session, only opens it, and prints **one
verdict line**. It prints cookie names only, never a value.

| Anda nampak / You see | Maksud / Meaning | Buat / Do |
|---|---|---|
| `nexabot.id: LOGGED IN. The studio stayed open ...` | Sesi berfungsi / The session works | Pergi ke langkah 4 / Go to step 4 |
| `nexabot.id: LOGGED IN ... but no cookie whose name contains session, token or auth` | Studio terbuka, tetapi log masuk mungkin disimpan dalam data halaman / The studio opened, but the login may live in the saved page data | Pergi ke langkah 4; probe akan mengesahkan / Go to step 4; the probe will confirm |
| `nexabot.id: LOGIN WALL ...` | Sesi tamat, ditolak, atau kod baharu diminta / Expired, refused, or a new code is wanted | Rakam semula (langkah 2) dan tunggu sehingga studio terbuka / Record again (step 2) and wait until the studio opens |
| `nexabot.id: BLOCKED ...` | Laman menjawab dengan semakan bot atau 403/429 / The site answered with a bot check or 403/429 | Beritahu Claude baris itu / Tell Claude that line |
| `Base64 size ... STILL TOO LARGE` | Melebihi had 48,000 aksara GitHub (jarang) / Over GitHub's 48,000-character limit (rare) | Padam `storage_state.json`, rakam semula dan lawat nexabot.id sahaja / Delete it, record again and visit only nexabot.id |

Baris `Base64 size` menunjukkan saiz dan sama ada data halaman dikekalkan. Had rahsia GitHub ialah 48,000 aksara. / The `Base64
size` line shows the size and whether the page data was kept. GitHub's limit for a secret is 48,000 characters.

## 4. Simpan sebagai rahsia / Save it as the secret

1. Buka `secret.txt` (ditulis oleh `--b64`), pilih **semua** dan salin. (Atau: Mac `base64 -i storage_state.json | pbcopy`;
   PowerShell `[Convert]::ToBase64String([IO.File]::ReadAllBytes("storage_state.json")) | Set-Clipboard`.) / Open `secret.txt`
   (written by `--b64`), select **all** of it and copy. (Or use the Mac and PowerShell commands above.)
2. GitHub, repo `wanshah07/semasa`, **Settings, Secrets and variables, Actions, New repository secret**.
3. Nama / Name: `NEXABOT_STORAGE_STATE_B64`. Nilai / Value: tampal / paste. Simpan / Save.
4. Padam `storage_state.json` dan `secret.txt` dari komputer, atau simpan di tempat peribadi: itulah log masuk itu. / Delete
   `storage_state.json` and `secret.txt` from your computer, or keep them somewhere private: they are the login.

## 5. Jalankan probe / Run the probe

GitHub, repo `wanshah07/semasa`, tab **Actions**, **Nexabot probe**, **Run workflow**. / GitHub, repo `wanshah07/semasa`, tab
**Actions**, **Nexabot probe**, **Run workflow**.

- Larian hanya dengan tangan; ia tiada jadual. Ia mengambil beberapa minit. / The run is by hand only; it has no schedule. It
  takes a few minutes.
- Jika sesi ditolak, larian gagal dengan mesej **"the saved login was refused: record it again"**. Ulang langkah 2 hingga 4. / If
  the session is refused, the run fails with the message **"the saved login was refused: record it again"**. Repeat steps 2 to 4.
- Jika berjaya, lihat **artifact `nexabot-probe`** pada halaman larian: `report.md` (boleh dibaca), `report.json` dan tangkap
  layar. Ia disimpan **satu hari sahaja**. / If it works, open the **artifact `nexabot-probe`** on the run page: `report.md`
  (readable), `report.json` and the screenshots. It is kept **one day only**.
- **Tangkap layar boleh menunjukkan nama akaun dan baki kredit.** Repo ini peribadi, tetapi jangan kongsi artifact itu di luar
  repo. / **Screenshots can show the account name and the credit balance.** The repo is private, but do not share the artifact
  outside it.
- Beritahu Claude larian itu sudah siap. Claude membaca laporan, dan Fasa B ditulis daripadanya. / Tell Claude the run is done.
  Claude reads the report, and Phase B is written from it.

## Apa yang ada dalam laporan / What the report holds

- Alamat akhir, tajuk halaman, teks yang kelihatan di kawasan utama, dan teks kredit/baki jika ada. / The final address, the page
  title, the visible text of the main areas, and the credit or balance text if shown.
- Setiap butang, pautan, input, select, textarea, tab dan radio: peranan, nama boleh akses, placeholder, jenis, dan sama ada
  dilumpuhkan. Pilihan dalam menu (model, nisbah, tempoh, kualiti) dibaca dengan **membuka** menu sahaja, tiada yang dipilih. /
  Every button, link, input, select, textarea, tab and radio: role, accessible name, placeholder, type, and whether disabled. The
  options in menus (model, ratio, duration, quality) are read by **opening** the menu only, nothing is chosen.
- Panggilan XHR/fetch asal yang sama semasa halaman dimuat: **KAEDAH + LALUAN + status** sahaja. Tiada pengepala, kuki, badan
  permintaan atau jawapan, dan nilai query dibuang; segmen laluan seperti id dikaburkan. / The same-origin XHR/fetch calls made
  while the page loads: **METHOD + PATH + status** only. No headers, cookies, request or response bodies, query values are
  dropped, and id-like path segments are masked.
- Senarai kawalan yang **tidak** ditekan kerana namanya kelihatan membelanjakan atau menghantar, dan setiap permintaan tulis yang
  dibatalkan di rangkaian. / The controls that were **not** pressed because their names look like spending or sending, and every
  write request aborted at the network.

## Apa yang masih boleh tidak kena / What can still go wrong

- **Alamat pusat data.** Probe berjalan di pelayan GitHub, bukan sambungan rumah. Jika langkah 3 lulus tetapi probe melihat
  "LOGIN WALL", Nexabot mungkin menolak sesi yang tiba-tiba muncul dari pusat data. Beritahu Claude; jalan keluarnya ialah
  menjalankan pembaca dari komputer sendiri. / **A datacenter address.** The probe runs on GitHub's servers, not your home
  connection. If step 3 passes but the probe sees a login wall, Nexabot may refuse a session that suddenly appears from a
  datacenter. Tell Claude; the way out is to run the reader from your own computer.
- **Sesi tamat.** Ulang langkah 2 hingga 4. / **Sessions expire.** Repeat steps 2 to 4.
- **Studio berubah.** Laporan akan berbeza; Fasa B ditulis daripada laporan terkini. / **The studio changes.** The report will
  differ; Phase B is written from the latest report.
- **Halaman memuatkan data melalui POST.** Probe membatalkan setiap tulis, jadi halaman itu mungkin kosong; laporan menyenaraikan
  permintaan yang dibatalkan. Beritahu Claude. / **The page loads data through POST.** The probe aborts every write, so such a
  page may show blanks; the report lists what was aborted. Tell Claude.
- **Jangan letak rahsia dalam chat, repo atau tangkap layar.** Ia ialah log masuk. / **Do not put the secret in chat, in the repo
  or in a screenshot.** It is a login.
