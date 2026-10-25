import policy from '../../../rules/motion/video-format-policy.json' with {type:'json'};
export const VIDEO_POLICY = policy;
export const VIDEO_FORMATS = policy.formats;
export function formatOf(d = {}) {
  if (VIDEO_FORMATS.some(f => f.id === d.format)) return d.format;
  if (d.mode === 'teaser') return 'gimmick';
  if (d.voice === 'off') return 'silent-first';
  return d.language === 'bm' || d.language === 'both' ? 'malay-voiced' : policy.default_format;
}
export function resolveFormat(d = {}, stream = 'regulab') {
  let format = formatOf(d);
  if (stream === 'linkedin' && format === 'malay-voiced') format = 'english-voiced';
  const selected = VIDEO_FORMATS.find(f => f.id === format);
  let language = selected.language || (['en','bm','both'].includes(d.language) ? d.language : 'en');
  if (format === 'malay-voiced' && d.language === 'both') language = 'both';
  const personal = stream === 'linkedin';
  if (personal) language = 'en';
  let voice = format === 'silent-first' ? 'off' : ['male','female','kitten'].includes(d.voice) ? d.voice : selected.voice || 'kitten';
  if (language !== 'en' && voice === 'kitten') voice = 'female';
  if (format === 'gimmick' && d.voice === 'off') voice = 'off';
  const seconds = format === 'gimmick' ? 10 : Number.isFinite(Number(d.seconds)) && Number(d.seconds) > 30 ? 60 : 30;
  return {format, mode:selected.mode, language, voice, seconds,
    resolution:personal ? 'portrait' : ['portrait','square','landscape'].includes(d.resolution) ? d.resolution : 'portrait',
    muteAll:d.muteAll === true, personalAvatar:d.personalAvatar || null};
}
export function applyFormat(row, d = {}) {
  const r = resolveFormat(d, row.stream);
  return {...row, language:r.language, voice:r.voice, seconds:r.seconds, resolution:r.resolution,
    options:{...row.options, format:r.format, mode:r.mode, policy_version:policy.version,
      mute_all:r.muteAll, personal_avatar:r.personalAvatar,
      brand_profile:row.stream === 'linkedin' ? 'linkedin-personal' : 'ws-regulab'}};
}
