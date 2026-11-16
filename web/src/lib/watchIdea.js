/* A watch row (semasa_watch) as the idea composer's "trend". Lives apart from components/WatchSegment.jsx so App.jsx can
   turn a row into an idea without loading that segment's page code on the sign-in screen (the segment is lazy). */

/** The paper's citation in one line: authors, journal, year, DOI (what the writer must cite, and Wan checks). */
export function paperLine(r) {
  const raw = r.raw || {};
  const au = Array.isArray(raw.authors) ? raw.authors : [];
  const who = au.length ? au.slice(0, 3).join(", ") + (au.length > 3 ? " et al." : "") : "";
  const year = r.published_at ? String(r.published_at).slice(0, 4) : "";
  return [who && (raw.n_authors > 3 && !who.endsWith("et al.") ? `${who} et al.` : who), raw.journal, year, raw.doi ? `DOI ${raw.doi}` : "", raw.pmid ? `PMID ${raw.pmid}` : ""].filter(Boolean).join(" · ");
}

/** A watch row as the idea composer's "trend": the summary carries everything the writer needs to cite it. */
export function watchIdea(r, brand) {
  const raw = r.raw || {};
  const pub = r.section === "publication";
  const domains = (brand && brand.regulab && brand.regulab.domains) || {};
  const summary = [
    r.summary,
    r.why ? `Kenapa penting: ${r.why}` : "",
    r.kind ? `Jenis: ${r.kind}${raw.ref ? ` (${raw.ref})` : ""}` : "",
    pub ? `Kertas: ${paperLine(r)}` : "",
    pub && raw.abstract ? `Abstrak: ${raw.abstract}` : "",
    r.section === "folder" && raw.cite ? `Rujukan dalam dokumen: ${raw.cite}` : "",
    r.section === "myra" && raw.ref_no ? `Rujukan: ${raw.ref_no}${raw.markets ? ` (${raw.markets})` : ""}` : "",
    (r.section === "reddit" || r.section === "youtube") ? "Ini hujah orang ramai: betulkan kepercayaannya, jangan sebut platform atau pautannya." : "",
    // Expert content: the expert's own words go to the writer beside the summary, as a reference to build on, never to copy
    r.section === "expert" && raw.original ? `Catatan asal pakar (rujukan sahaja):\n${raw.original}` : "",
    // LinkedIn (16 Nov 2026): someone else's post is a lead on what peers are talking about, with the numbers it carried
    r.section === "linkedin" && raw.metrics ? `Sambutan di LinkedIn: ${raw.metrics}` : "",
    r.section === "linkedin" && raw.original ? `Teks asal post itu (rujukan sahaja):\n${raw.original}` : "",
    r.section === "linkedin" ? "Ini post LinkedIn orang lain: guna sebagai petunjuk isu sahaja. Tulis dari instrumen atau sumber rasmi dengan sudut sendiri, jangan salin ayatnya, dan jangan sebut nama akaun, platform atau pautannya." : "",
    r.section === "website" ? `Daripada laman yang anda senaraikan (${r.source}). Baca dokumen asalnya sebelum menulis dan petik instrumen itu sendiri.` : "",
    r.section === "expert" ? "Ini pandangan seorang pakar: guna sebagai rujukan dan tulis dengan sudut sendiri. Sahkan setiap fakta dengan sumber rasmi, jangan salin ayatnya, dan jangan sebut nama akaun, platform atau pautannya." : "",
  ].filter(Boolean).join("\n\n");
  return {
    watch: true, section: r.section, id: r.id, title: r.title, url: r.url, source: r.source, summary,
    domain: domains[r.domain] ? r.domain : "",
    // a paper speaks to peers (LinkedIn, angle F: cosmetic science; G: medicine or dermatology); a notice to SMEs
    // Wan's own websites and LinkedIn lists are kept for LinkedIn ideas (the page they are on is in that segment)
    stream: pub || r.section === "linkedin" || r.section === "website" ? "linkedin" : "regulab",
    angle: pub ? (r.domain === "farmaseutikal" ? "G" : "F") : "",
  };
}
