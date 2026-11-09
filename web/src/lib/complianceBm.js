/* The compliance scan's words in Bahasa Malaysia, for the page only.
   lib/compliance.js (and the Python publisher it mirrors) writes every flag in English: `where` names the field and `msg` the
   rule, and both are compared as they are (PostEditor's Fix → reads `where`; the tests read `msg`). This file never touches a
   flag. It only finds the Malay for the words a flag already carries, at the moment a BM page draws it, so which checks run,
   which ones block and what they are called stays exactly where it was. A message it does not know is shown in English, as
   before: a new rule is never hidden, only untranslated until a line is added here (complianceBm.test.mjs lists every
   label in rules/compliance.json and every fixed message in compliance.js, so a missing one fails the test). */

const DAYS_BM = { Sunday: "Ahad", Monday: "Isnin", Tuesday: "Selasa", Wednesday: "Rabu", Thursday: "Khamis", Friday: "Jumaat", Saturday: "Sabtu" };

/** Exact English message → Malay. The labels in rules/compliance.json first, then the fixed messages in compliance.js. */
export const MSG_BM = {
  // rules/compliance.json: hard
  "old brand name 'KKM Halal Consultant'": "nama jenama lama 'KKM Halal Consultant'",
  "promises approval ('dijamin lulus')": "menjanjikan kelulusan ('dijamin lulus')",
  "promises approval": "menjanjikan kelulusan",
  "implies an inside contact ('orang dalam')": "membayangkan ada kenalan dalaman ('orang dalam')",
  "absolute safety claim": "dakwaan keselamatan mutlak",
  "halal claim without certificate": "dakwaan halal tanpa sijil",
  "shariah claim without certificate": "dakwaan patuh syariah tanpa sijil",
  "superlative claim": "dakwaan superlatif",
  "em dash": "sengkang em (—)",
  // rules/compliance.json: cta
  "CTA: 'semak kelayakan'": "CTA: 'semak kelayakan'",
  "CTA: asks for a keyword comment": "CTA: minta komen kata kunci",
  "CTA: asks for a DM": "CTA: minta mesej peribadi (DM)",
  "CTA: asks for a follow": "CTA: minta diikuti (follow)",
  "CTA: asks for a share": "CTA: minta dikongsi",
  "CTA: 'click the link'": "CTA: 'click the link'",
  "CTA: 'comment below'": "CTA: 'comment below'",
  "CTA: 'contact us'": "CTA: 'contact us'",
  "CTA: 'hubungi kami'": "CTA: 'hubungi kami'",
  "CTA: 'klik link'": "CTA: 'klik link'",
  "CTA: 'komen di bawah'": "CTA: 'komen di bawah'",
  "CTA: 'link in bio'": "CTA: 'link in bio'",
  "CTA: 'pautan di bio'": "CTA: 'pautan di bio'",
  "CTA: 'save this post'": "CTA: 'save this post'",
  "CTA: 'share this'": "CTA: 'share this'",
  "CTA: 'simpan post'": "CTA: 'simpan post'",
  "CTA: 'tanya di komen'": "CTA: 'tanya di komen'",
  "CTA: 'whatsapp kami'": "CTA: 'whatsapp kami'",
  // rules/compliance.json: soft
  "opens with 'Tahukah anda'": "dibuka dengan 'Tahukah anda'",
  "AI cliché opener": "pembuka klise AI",
  "government-memo BM": "BM gaya memo kerajaan",
  "AI tell: 'bukan sekadar X, malah Y'": "tanda AI: 'bukan sekadar X, malah Y'",
  "AI tell: 'not just X, it's Y'": "tanda AI: 'not just X, it's Y'",
  "AI tell: a chatbot closer": "tanda AI: penutup gaya chatbot",
  "AI tell: a clause in ALL CAPS": "tanda AI: satu klausa dalam HURUF BESAR",
  "AI tell: a fake-candid opener": "tanda AI: pembuka pura-pura jujur",
  "AI tell: a generic upbeat ending": "tanda AI: penutup ceria yang umum",
  "AI tell: an unnamed authority": "tanda AI: pihak berkuasa yang tidak dinamakan",
  "AI tell: announcing instead of saying": "tanda AI: mengumumkan, bukan terus berkata",
  "AI tell: empty AI vocabulary. Say what it does.": "tanda AI: kosa kata AI yang kosong. Katakan apa yang ia buat.",
  "AI tell: empty marketing words (BM)": "tanda AI: kata pemasaran yang kosong (BM)",
  "AI tell: significance inflation": "tanda AI: membesar-besarkan kepentingan",
  // rules/compliance.json: the single-pattern rules
  "names a social source": "menyebut sumber media sosial",
  "a blog or news aggregator": "blog atau pengagregat berita",
  "reads as Bahasa Malaysia": "berbunyi Bahasa Malaysia",
  "a link": "pautan",
  // rules/compliance.json: indo_soft
  "\"bisa\" is venom in BM; if you mean \"can\", write boleh": "\"bisa\" bermaksud racun dalam BM; jika maksudnya \"can\", tulis boleh",
  "\"kalian\" reads Indonesian here; anda or kamu semua is safer": "\"kalian\" berbunyi Indonesia di sini; anda atau kamu semua lebih selamat",
  "\"izin\" is valid BM but kebenaran is the regulatory term": "\"izin\" sah dalam BM tetapi kebenaran ialah istilah regulatori",
  // compliance.js: fixed messages
  "empty": "kosong",
  "names a social source. Never say the idea came from Reddit, YouTube, a forum or a post.":
    "menyebut sumber media sosial. Jangan sekali-kali kata idea datang dari Reddit, YouTube, forum atau sesuatu post.",
  "names a social source. A post stands on the instrument, never on where the idea was spotted.":
    "menyebut sumber media sosial. Post bersandar pada instrumen, bukan pada tempat idea itu ditemui.",
  "the ws.regulab website. The artwork footer already carries it.": "laman web ws.regulab. Kaki artwork sudah membawanya.",
  "the ws.regulab website. Only the artwork footer carries it.": "laman web ws.regulab. Hanya kaki artwork yang membawanya.",
  "the ws.regulab website": "laman web ws.regulab",
  "a link. Naming the instrument usually reads better than pasting a URL.": "pautan. Menamakan instrumen biasanya lebih baik daripada menampal URL.",
  "\"kepada bapak\" reads as Bahasa Indonesia": "\"kepada bapak\" berbunyi Bahasa Indonesia",
  "ends with a question": "berakhir dengan soalan",
  "a ws.regulab mark on LinkedIn. That stream is Wan's own byline.": "tanda ws.regulab di LinkedIn. Aliran itu ialah nama Wan sendiri.",
  "a ws.regulab mark on LinkedIn": "tanda ws.regulab di LinkedIn",
  "reads as Bahasa Malaysia. The LinkedIn stream is English: write the caption in English.":
    "berbunyi Bahasa Malaysia. Aliran LinkedIn dalam bahasa Inggeris: tulis kapsyen dalam bahasa Inggeris.",
  "write the closing line: one statement that leaves them curious. Not a question, not an ask.":
    "tulis baris penutup: satu kenyataan yang membuat mereka ingin tahu. Bukan soalan, bukan permintaan.",
  "the slide pictures carry different words from the slides written here. Draw them again (Jana slaid) so what is sent is what was checked.":
    "gambar slaid membawa perkataan yang berbeza daripada slaid yang ditulis di sini. Lukis semula (Jana slaid) supaya yang dihantar ialah yang disemak.",
  "written but not drawn yet. Only drawn slides are sent.": "sudah ditulis tetapi belum dilukis. Hanya slaid yang dilukis dihantar.",
  "fatwa: gazette warning missing (diwartakan)": "fatwa: amaran pewartaan tiada (diwartakan)",
  "instagram needs an image": "instagram perlukan gambar",
};

/** Messages with a number or a word in them: [pattern, (match) → Malay]. */
const MSG_PATTERNS = [
  [/^(\d+) chars, over the (\d+) limit$/, (m) => `${m[1]} aksara, melebihi had ${m[2]}`],
  [/^(\d+) hashtags, over the (\d+) limit$/, (m) => `${m[1]} hashtag, melebihi had ${m[2]}`],
  [/^cites "(.+)", a blog or news aggregator\. On LinkedIn cite the instrument, not where you read it\.$/,
    (m) => `memetik "${m[1]}", blog atau pengagregat berita. Di LinkedIn, petik instrumennya, bukan tempat anda membacanya.`],
  [/^cites "(.+)", a blog or news aggregator\. Cite the instrument\.$/, (m) => `memetik "${m[1]}", blog atau pengagregat berita. Petik instrumennya.`],
  [/^Bahasa Indonesia word "([^"]+)" \(tabung: write "([^"]+)"\)$/, (m) => `perkataan Bahasa Indonesia "${m[1]}" (tabung: tulis "${m[2]}")`],
  [/^Bahasa Indonesia word "([^"]+)" \(tabung\)$/, (m) => `perkataan Bahasa Indonesia "${m[1]}" (tabung)`],
  [/^Bahasa Indonesia word "([^"]+)"$/, (m) => `perkataan Bahasa Indonesia "${m[1]}"`],
  [/^(\w+) carries (.+), and this is (\S+)\. A note, not a block\.$/,
    (m) => `${DAYS_BM[m[1]] || m[1]} membawa ${m[2].replace(/ and /g, " dan ")}, dan ini ${m[3]}. Nota, bukan sekatan.`],
];

/** Field names: [pattern, (match) → Malay]; anything else (already Malay, or a name such as Rota) is kept. */
const WHERE_PATTERNS = [
  [/^Caption \((\w+)\)$/, (m) => `Kapsyen (${m[1]})`],
  [/^(BM|EN) variant \((\w+)\)$/, (m) => `Varian ${m[1]} (${m[2]})`],
  [/^Picture (\d+) alt text$/, (m) => `Teks alt gambar ${m[1]}`],
  [/^Design (\d+), slide (\d+)$/, (m) => `Reka bentuk ${m[1]}, slaid ${m[2]}`],
  [/^Slide (\d+)$/, (m) => `Slaid ${m[1]}`],
  [/^Source$/, () => "Sumber"],
  [/^Carousel$/, () => "Karusel"],
  [/^Slides$/, () => "Slaid"],
];

const viaPatterns = (s, list) => {
  for (const [re, fn] of list) { const m = re.exec(s); if (m) return fn(m); }
  return null;
};

/** A flag's message in Malay, or the message itself when no translation is known. */
export const msgBm = (msg) => {
  const s = String(msg ?? "");
  return MSG_BM[s] ?? viaPatterns(s, MSG_PATTERNS) ?? s;
};

/** A flag's field name in Malay, or the name itself. */
export const whereBm = (where) => {
  const s = String(where ?? "");
  return viaPatterns(s, WHERE_PATTERNS) ?? s;
};

/** { where, msg } to draw for a flag in the page's language; the flag itself is not changed. */
export const flagWords = (f, lang) => (lang === "en" ? { where: f.where, msg: f.msg } : { where: whereBm(f.where), msg: msgBm(f.msg) });
