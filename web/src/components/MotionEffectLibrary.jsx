import { useState } from 'react';
import { ASSET_TYPES, effectGroups, effectPolicy, resolveEffects, toggleEffect } from '../lib/motionEffects';
import { uploadMotionAsset } from '../lib/motionAssetStorage';
import { Input, Select } from './ui/Field';
import { useLang } from '../lib/i18n';

const readiness = (t) => ({ready:t('Adaptasi asli','Native adaptation'),autoasset:t('Aset Semasa sedia','Semasa asset ready'),manualasset:t('Perlu tangkapan skrin bersumber','Needs sourced screenshot'),fallback:t('Konsep sahaja','Concept fallback only')});

/** Illustrations deliberately do not claim to be previews of source-video effects. */
function Thumbnail({ id, section }) {
  const { t } = useLang();
  return <div className="relative overflow-hidden rounded-tile bg-[#102422] p-3 text-[#c8efb7]">
    <svg viewBox="0 0 240 145" className="w-full" aria-hidden="true">
      <path d="M20 105H220M20 120H175" stroke="currentColor" opacity=".15" />
      {section === 'Sound' ? <path d="M20 75h12l5-20 8 45 8-65 8 80 8-55 8 15h18l8-35 8 65 8-40h20l8-18 8 42 8-60 8 75 8-35h30" stroke="currentColor" fill="none" strokeWidth="3" /> : <g stroke="currentColor" fill="none" strokeWidth="3"><path d="M55 70H185"/><circle cx="55" cy="70" r="25" fill="#264e42"/><rect x="100" y="45" width="45" height="50" rx="8" fill="#264e42"/><circle cx="185" cy="70" r="25" fill="#264e42"/></g>}
      <text x="16" y="24" fill="currentColor" fontSize="12">{id}</text>
    </svg>
    <span className="block text-[10px] opacity-90">{t('Ilustrasi · bukan demo kesan', 'Illustration · not an effect demo')}</span>
  </div>;
}

export default function MotionEffectLibrary({ brief, mode, effects, effectMode, onEffects, onEffectMode, assets, onAssets, client, user, onBusy }) {
  const { t } = useLang();
  const [query,setQuery] = useState('');
  const [category,setCategory] = useState('');
  const [rights,setRights] = useState('');
  const [role,setRole] = useState('reference');
  const [source,setSource] = useState('');
  const [attribution,setAttribution] = useState('');
  const [error,setError] = useState('');
  const [uploading,setUploading] = useState(false);
  const selected=resolveEffects({brief,mode,effects,effectMode,assets});
  const all=effectGroups();
  const groups=effectGroups(query).filter(g=>!category || g.title===category);
  const entries=Object.fromEntries(all.flatMap(g=>g.effects).map(e=>[e.id,e]));
  const toggle=id=>{onEffects(toggleEffect(selected,id));onEffectMode('manual');};
  const attach=async event=>{
    const file=event.target.files?.[0];
    event.target.value='';
    if(!file) return;
    if(assets.length>=8) return setError(t('Paling banyak lapan lampiran','At most eight attachments'));
    setError('');setUploading(true);onBusy?.(true);
    try {
      const ref=await uploadMotionAsset(client,user,file,{rights,role,source,attribution});
      onAssets([...assets,ref]);
    } catch(e) {setError(e.message);} finally {setUploading(false);onBusy?.(false);}
  };
  return <section aria-label={t('Pustaka kesan motion','Motion effect library')} className="space-y-4 rounded-card border border-line p-4" data-motion-effects>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h3 className="font-display text-lg">{t('Pustaka kesan','Effect library')}</h3>
      <div role="group" aria-label={t('Pilihan kesan','Effect selection')} className="flex gap-2">
        {['auto','manual'].map(v=><button type="button" key={v} aria-pressed={effectMode===v} onClick={()=>{if(v==='manual')onEffects(selected);onEffectMode(v);}} className={`rounded-pill border px-4 py-2 text-xs ${effectMode===v?'border-accent bg-accent/10':'border-line'}`}>{v==='auto'?t('Auto · disyorkan','Auto · recommended'):t('Manual','Manual')}</button>)}
      </div>
    </div>
    <p className="text-xs text-muted">{t('Auto: bila filem dibuat, Semasa pilih sekurang-kurangnya 15 daripada 99 gaya, babak demi babak, ikut apa yang setiap babak kata dan tunjuk (Hook → Fakta → Kenapa → Solusi), dan senaraikan yang dipakai pada video siap. Gaya yang perlukan rakaman, tangkapan skrin atau fail bunyi yang filem itu tiada ditinggalkan. Manual: hanya kad yang anda tambah. Pilihan reka bentuk dan gaya lampiran kekal berasingan.','Auto: when the film is made, Semasa picks at least 15 of the 99 styles, scene by scene, for what each scene says and shows (Hook → Fact → Why → Solution), and lists the ones applied on the finished video. Styles that need footage, a screenshot or a sound file the film does not have are left out. Manual: only the cards you add. Design and attachment-style choices stay independent.')}</p>
    <div aria-label={t('Kesan dipilih','Selected effects')} aria-live="polite" className="rounded-tile bg-surface-2 p-3">
      <p className="mb-2 text-xs">{effectMode==='auto'?t('Auto · sekurang-kurangnya 15 dipilih bila filem dibuat','Auto · at least 15 chosen when the film is made'):t('Dipilih','Selected')}{effectMode==='auto'?'':` · ${selected.length} ${t('kesan','effects')}`}</p>
      <div className="flex flex-wrap gap-2">{effectMode==='auto'?null:selected.map(id=><button type="button" key={id} onClick={()=>toggle(id)} aria-label={`${t('Buang','Remove')} ${entries[id]?.name}`} className="rounded-pill border border-accent px-3 py-1 text-xs">{id} · {entries[id]?.name} ×</button>)}{effectMode!=='auto'&&!selected.length&&<span className="text-xs text-muted">{t('Tiada kesan tambahan; resipi video lengkap tetap dipakai.','No additional effects; the complete video recipe is still used.')}</span>}</div>
      {selected.some(id=>effectPolicy[id].readiness==='fallback')&&<p className="mt-2 text-xs text-warn">{t('Sebahagian pilihan ialah adaptasi konsep sahaja, bukan kesan sumber yang dilaksanakan. Lihat had pada setiap kad.','Some selections are concept-only adaptations, not implemented source effects. See each card\'s limitation.')}</p>}
    </div>
    <details className="rounded-tile border border-line p-3">
      <summary className="cursor-pointer text-sm">{t('Aset manual (pilihan)','Optional manual assets')} · {assets.length}/8</summary>
      <p className="my-3 text-xs text-muted">{t('Semasa mencipta vektor asli yang neutral tanpa muat naik. Lampirkan gambar, tangkapan skrin, video, audio, PDF atau teks anda sendiri (20 MB setiap satu). Gambar boleh dipakai dalam penyesuai tangkapan skrin yang disokong; video, audio dan dokumen disimpan sebagai rujukan sahaja, tidak disunting atau dipaparkan sebagai bukti. Muat naik memerlukan migrasi baldi motion-assets peribadi; tiada sandaran ke baldi rujukan awam.','Semasa creates a neutral original vector without uploads. Attach your own image, screenshot, video, audio, PDF or text (20 MB each). Images can be used in supported screenshot adapters; video/audio/documents are retained as references only, not edited or presented as proof. Uploads require the private motion-assets bucket migration; no public reference bucket fallback.')}</p>
      <div className="grid gap-2 sm:grid-cols-2">
        <Select aria-label={t('Peranan aset','Asset role')} value={role} onChange={setRole} options={[["reference",t('Rujukan','Reference')],["screenshot",t('Tangkapan skrin tulen','Authentic screenshot')]]} />
        <Select aria-label={t('Hak aset','Asset rights')} value={rights} onChange={setRights} options={[["",t('Sahkan hak…','Confirm rights…')],["self-owned",t('Aset ini milik saya','I own this asset')],["licensed",t('Saya ada lesen','I hold a licence')]]} />
        <Input aria-label={t('Sumber aset','Asset source')} placeholder={t('Sumber / URL asal (wajib untuk tangkapan skrin)','Source / original URL (required for screenshots)')} value={source} onChange={e=>setSource(e.target.value)} />
        <Input aria-label={t('Atribusi aset','Asset attribution')} placeholder={t('Atribusi / pencipta','Attribution / creator')} value={attribution} onChange={e=>setAttribution(e.target.value)} />
      </div>
      <label className="mt-3 block text-xs">{uploading?t('Memuat naik…','Uploading…'):t('Lampirkan fail','Attach file')}<input aria-label={t('Lampirkan aset motion','Attach motion asset')} type="file" accept={Object.keys(ASSET_TYPES).join(',')} onChange={attach} disabled={uploading||!user?.id||!rights||assets.length>=8} className="mt-2 block max-w-full" /></label>
      {error&&<p role="alert" className="mt-2 text-xs text-danger">{error}</p>}
      <ul className="mt-2 space-y-2 text-xs">{assets.map(a=><li key={a.path} className="flex justify-between gap-2"><span className="break-all">{a.path.split('/').pop()} · {a.mime} · {a.role}</span><button type="button" disabled={uploading} onClick={()=>onAssets(assets.filter(v=>v.path!==a.path))}>{t('Tanggalkan','Detach')}</button></li>)}</ul>
    </details>
    <div className="flex flex-wrap gap-2">
      <Input aria-label={t('Cari kesan','Search effects')} placeholder={t('Cari nama, ID atau huraian…','Search name, ID or description…')} value={query} onChange={e=>setQuery(e.target.value)} className="min-w-0 flex-1" />
      <Select aria-label={t('Kategori kesan','Effect category')} value={category} onChange={setCategory} options={[["",t('Semua bahagian asal','All original sections')],...all.map(g=>[g.title,g.title])]} />
    </div>
    <div className="max-h-[44rem] space-y-6 overflow-y-auto pr-1">
      {!groups.length&&<p className="text-sm text-muted">{t('Tiada kesan sepadan dengan carian ini.','No effects match this search.')}</p>}
      {groups.map(group=><section key={group.title} aria-label={group.title}>
        <h4 className="mb-3 border-b border-line pb-2 text-sm font-semibold">{group.title} <span className="text-xs font-normal text-muted">· {group.effects.length}</span></h4>
        <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 md:grid-cols-3 xl:grid-cols-5">
          {group.effects.map(e=><article key={e.occurrence} className={`flex flex-col gap-2 rounded-tile border p-2 ${selected.includes(e.id)?'border-accent bg-accent/5':'border-line bg-surface'}`}>
            <Thumbnail id={e.id} section={group.title}/>
            <h5 className="text-sm font-semibold">{e.name}</h5>
            <p className="text-xs text-muted">{e.description}</p>
            <span className={`text-[10px] ${e.readiness==='fallback'?'text-warn':'text-accent'}`}>{readiness(t)[e.readiness]}</span>
            <details className="text-[10px] text-muted"><summary className="cursor-pointer">{t('Aset diperlukan & had','Required assets & limitations')}</summary><p className="mt-1">{Array.isArray(e.required_assets)?e.required_assets.join(' · '):e.required_assets}</p><p className="mt-1">{e.reason}</p></details>
            <button type="button" aria-pressed={selected.includes(e.id)} aria-label={`${selected.includes(e.id)?t('Buang','Remove'):t('Tambah','Add')} ${e.name}`} onClick={()=>toggle(e.id)} className="mt-auto rounded-pill border border-line px-3 py-1.5 text-xs">{selected.includes(e.id)?t('✓ Ditambah','✓ Added'):t('＋ Tambah','＋ Add')}</button>
          </article>)}
        </div>
      </section>)}
    </div>
    <p className="text-[10px] text-muted">{t('Susunan dan nama bahagian dokumen asal dikekalkan: 99 kesan unik, 106 kemunculan (termasuk Featured Effects dan pendua H06 asal). Ilustrasi bukan demo rakaman. Kebanyakan kesan penyuntingan sumber kini memakai konsep sahaja, dan dilaporkan begitu.','Original document order and section names preserved: 99 unique effects, 106 occurrences (including Featured Effects and the original H06 duplicate). Thumbnails are illustrative, not recorded demos. Most source-editing effects currently use an explicitly reported concept fallback.')}</p>
  </section>;
}
