/* Picture sizes, as Canva lists them for social media (Wan, 26 Sep 2026, with Canva's resize panel attached: "add
   ratio layout option as attachment"). Stills only: the animated and video entries are left out, since everything
   here is drawn as one picture. The worker takes any size between MIN and MAX, so a size added here needs no
   backend change (backend/semasa/design.py and fragrance.py read meta.size). */

export const SIZE_MIN = 200;
export const SIZE_MAX = 4096;

export const PLATFORMS = [
  ["all", "Semua", "All"], ["studio", "Studio", "Studio"], ["instagram", "Instagram", "Instagram"],
  ["tiktok", "TikTok", "TikTok"], ["facebook", "Facebook", "Facebook"], ["youtube", "YouTube", "YouTube"],
  ["linkedin", "LinkedIn", "LinkedIn"], ["pinterest", "Pinterest", "Pinterest"], ["x", "X", "X"],
];

// id: [platform, name, width, height]. The first three keep the ids the Design tab has always stored.
export const SIZES = {
  square: ["studio", "Segi empat 1:1", 1080, 1080],
  portrait: ["studio", "Potret 4:5", 1080, 1350],
  story: ["studio", "Cerita 9:16", 1080, 1920],
  ig_post_45: ["instagram", "Instagram Post (4:5)", 1080, 1350],
  ig_post_11: ["instagram", "Instagram Post (1:1)", 1080, 1080],
  ig_post_34: ["instagram", "Instagram Post (3:4)", 1080, 1440],
  ig_story: ["instagram", "Instagram Story", 1080, 1920],
  ig_reel: ["instagram", "Instagram Reel cover", 1080, 1920],
  ig_ad_45: ["instagram", "Instagram Ad (4:5)", 1080, 1350],
  tiktok: ["tiktok", "TikTok cover", 1080, 1920],
  fb_post: ["facebook", "Facebook Post", 940, 788],
  fb_square: ["facebook", "Facebook Post (1:1)", 1080, 1080],
  fb_story: ["facebook", "Facebook Story", 1080, 1920],
  fb_cover: ["facebook", "Facebook Cover", 851, 315],
  fb_event: ["facebook", "Facebook Event Cover", 1920, 1080],
  fb_ad: ["facebook", "Facebook Ad", 1200, 628],
  fb_app_ad: ["facebook", "Facebook App Ad", 810, 450],
  fb_shops: ["facebook", "Facebook Shops", 1024, 1024],
  yt_thumb: ["youtube", "YouTube Thumbnail", 1280, 720],
  yt_banner: ["youtube", "YouTube Banner", 2560, 1440],
  li_post: ["linkedin", "LinkedIn Post", 1200, 1200],
  li_portrait: ["linkedin", "LinkedIn Post (4:5)", 1080, 1350],
  li_ad: ["linkedin", "LinkedIn Single Image Ad", 1200, 627],
  li_bg: ["linkedin", "LinkedIn Background", 1584, 396],
  pin: ["pinterest", "Pinterest Pin (2:3)", 1000, 1500],
  x_post: ["x", "X Post", 1600, 900],
};

export function sizeOf(id) {
  const s = SIZES[id];
  return s ? { id, platform: s[0], name: s[1], w: s[2], h: s[3] } : null;
}

export function ratioLabel(w, h) {
  const g = (a, b) => (b ? g(b, a % b) : a);
  const d = g(w, h);
  const [a, b] = [w / d, h / d];
  return a <= 32 && b <= 32 ? `${a}:${b}` : (w / h).toFixed(2);
}

export function sizeLabel(id, fallback) {
  const s = sizeOf(id);
  if (s) return `${s.name} · ${s.w}×${s.h}`;
  if (fallback?.length === 2) return `${fallback[0]}×${fallback[1]}`;
  return "—";
}

/** What a job stores: the preset id, the pixels, and the name shown on its card. */
export function sizeMeta(id) {
  const s = sizeOf(id);
  return s ? { format: id, size: [s.w, s.h], size_name: s.name } : {};
}
