import { useState } from 'react';
import { ASSET_TYPES, effectGroups, effectPolicy, resolveEffects, toggleEffect } from '../lib/motionEffects';
import { uploadMotionAsset } from '../lib/motionAssetStorage';
import { Input, Select } from './ui/Field';

const readiness = {ready:'Native adaptation',autoasset:'Bot asset ready',manualasset:'Needs sourced screenshot',fallback:'Concept fallback only'};

/** Illustrations deliberately do not claim to be previews of source-video effects. */
function Thumbnail({ id, section }) {
  return <div className="relative overflow-hidden rounded-tile bg-[#102422] p-3 text-[#c8efb7]">
    <svg viewBox="0 0 240 145" className="w-full" aria-hidden="true">
      <path d="M20 105H220M20 120H175" stroke="currentColor" opacity=".15" />
      {section === 'Sound' ? <path d="M20 75h12l5-20 8 45 8-65 8 80 8-55 8 15h18l8-35 8 65 8-40h20l8-18 8 42 8-60 8 75 8-35h30" stroke="currentColor" fill="none" strokeWidth="3" /> : <g stroke="currentColor" fill="none" strokeWidth="3"><path d="M55 70H185"/><circle cx="55" cy="70" r="25" fill="#264e42"/><rect x="100" y="45" width="45" height="50" rx="8" fill="#264e42"/><circle cx="185" cy="70" r="25" fill="#264e42"/></g>}
      <text x="16" y="24" fill="currentColor" fontSize="12">{id}</text>
    </svg>
    <span className="block text-[10px] opacity-70">Illustrative thumbnail · not an effect demo</span>
  </div>;
}

export default function MotionEffectLibrary({ brief, mode, effects, effectMode, onEffects, onEffectMode, assets, onAssets, client, user, onBusy }) {
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
    if(assets.length>=8) return setError('At most eight attachments');
    setError('');setUploading(true);onBusy?.(true);
    try {
      const ref=await uploadMotionAsset(client,user,file,{rights,role,source,attribution});
      onAssets([...assets,ref]);
    } catch(e) {setError(e.message);} finally {setUploading(false);onBusy?.(false);}
  };
  return <section aria-label="Motion effect library" className="space-y-4 rounded-card border border-line p-4" data-motion-effects>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h3 className="font-display text-lg">Effect library</h3>
      <div role="group" aria-label="Effect selection" className="flex gap-2">
        {['auto','manual'].map(v=><button type="button" key={v} aria-pressed={effectMode===v} onClick={()=>{if(v==='manual')onEffects(selected);onEffectMode(v);}} className={`rounded-pill border px-4 py-2 text-xs ${effectMode===v?'border-accent bg-accent/10':'border-line'}`}>{v==='auto'?'Auto · recommended':'Manual'}</button>)}
      </div>
    </div>
    <p className="text-xs text-muted">Auto assembles a small compatible effect recipe from your idea, video mode and available assets, within the complete Hook → Fact → Why → Solution video. Manual lets you add/remove any card. It never stacks all 99 effects. Existing design and attachment-style choices remain independent.</p>
    <div aria-label="Selected effects" aria-live="polite" className="rounded-tile bg-surface-2 p-3">
      <p className="mb-2 text-xs">{effectMode==='auto'?'Recommended':'Selected'} · {selected.length} effects</p>
      <div className="flex flex-wrap gap-2">{selected.map(id=><button type="button" key={id} onClick={()=>toggle(id)} aria-label={`Remove ${entries[id]?.name}`} className="rounded-pill border border-accent px-3 py-1 text-xs">{id} · {entries[id]?.name} ×</button>)}{!selected.length&&<span className="text-xs text-muted">No additional effects; the complete video recipe is still used.</span>}</div>
      {selected.some(id=>effectPolicy[id].readiness==='fallback')&&<p className="mt-2 text-xs text-warn">Some selections are concept-only adaptations, not implemented source effects. See each card's limitation.</p>}
    </div>
    <details className="rounded-tile border border-line p-3">
      <summary className="cursor-pointer text-sm">Optional manual assets · {assets.length}/8</summary>
      <p className="my-3 text-xs text-muted">The bot creates a neutral original vector without uploads. Attach your own image, screenshot, video, audio, PDF or text (20 MB each). Images can be used in supported screenshot adapters; video/audio/documents are retained as references only, not edited or presented as proof. Uploads require the private motion-assets bucket migration; no public reference bucket fallback.</p>
      <div className="grid gap-2 sm:grid-cols-2">
        <Select aria-label="Asset role" value={role} onChange={setRole} options={[["reference","Reference"],["screenshot","Authentic screenshot"]]} />
        <Select aria-label="Asset rights" value={rights} onChange={setRights} options={[["","Confirm rights…"],["self-owned","I own this asset"],["licensed","I hold a license"]]} />
        <Input aria-label="Asset source" placeholder="Source / original URL (required for screenshots)" value={source} onChange={e=>setSource(e.target.value)} />
        <Input aria-label="Asset attribution" placeholder="Attribution / creator" value={attribution} onChange={e=>setAttribution(e.target.value)} />
      </div>
      <label className="mt-3 block text-xs">{uploading?'Uploading…':'Attach file'}<input aria-label="Attach motion asset" type="file" accept={Object.keys(ASSET_TYPES).join(',')} onChange={attach} disabled={uploading||!user?.id||!rights||assets.length>=8} className="mt-2 block max-w-full" /></label>
      {error&&<p role="alert" className="mt-2 text-xs text-danger">{error}</p>}
      <ul className="mt-2 space-y-2 text-xs">{assets.map(a=><li key={a.path} className="flex justify-between gap-2"><span className="break-all">{a.path.split('/').pop()} · {a.mime} · {a.role}</span><button type="button" disabled={uploading} onClick={()=>onAssets(assets.filter(v=>v.path!==a.path))}>Detach</button></li>)}</ul>
    </details>
    <div className="flex flex-wrap gap-2">
      <Input aria-label="Search effects" placeholder="Search name, ID or description…" value={query} onChange={e=>setQuery(e.target.value)} className="min-w-0 flex-1" />
      <Select aria-label="Effect category" value={category} onChange={setCategory} options={[["","All original sections"],...all.map(g=>[g.title,g.title])]} />
    </div>
    <div className="max-h-[44rem] space-y-6 overflow-y-auto pr-1">
      {!groups.length&&<p className="text-sm text-muted">No effects match this search.</p>}
      {groups.map(group=><section key={group.title} aria-label={group.title}>
        <h4 className="mb-3 border-b border-line pb-2 text-sm font-semibold">{group.title} <span className="text-xs font-normal text-muted">· {group.effects.length}</span></h4>
        <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 md:grid-cols-3 xl:grid-cols-5">
          {group.effects.map(e=><article key={e.occurrence} className={`flex flex-col gap-2 rounded-tile border p-2 ${selected.includes(e.id)?'border-accent bg-accent/5':'border-line bg-surface'}`}>
            <Thumbnail id={e.id} section={group.title}/>
            <h5 className="text-sm font-semibold">{e.name}</h5>
            <p className="text-xs text-muted">{e.description}</p>
            <span className={`text-[10px] ${e.readiness==='fallback'?'text-warn':'text-accent'}`}>{readiness[e.readiness]}</span>
            <details className="text-[10px] text-muted"><summary className="cursor-pointer">Required assets & limitations</summary><p className="mt-1">{Array.isArray(e.required_assets)?e.required_assets.join(' · '):e.required_assets}</p><p className="mt-1">{e.reason}</p></details>
            <button type="button" aria-pressed={selected.includes(e.id)} aria-label={`${selected.includes(e.id)?'Remove':'Add'} ${e.name}`} onClick={()=>toggle(e.id)} className="mt-auto rounded-pill border border-line px-3 py-1.5 text-xs">{selected.includes(e.id)?'✓ Added':'＋ Add'}</button>
          </article>)}
        </div>
      </section>)}
    </div>
    <p className="text-[10px] text-muted">Original document order and section names preserved: 99 unique effects, 106 occurrences (including Featured Effects and the original H06 duplicate). Thumbnails are illustrative, not recorded demos. Most source-editing effects currently use an explicitly reported concept fallback.</p>
  </section>;
}
