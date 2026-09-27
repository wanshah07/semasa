import { tr } from "./i18n";

/* One page at a time may hold unsaved work (Kanvas). It registers a check here, and the app asks before a tab switch
   or the browser's Back takes the page away: switching tabs used to unmount the editor and lose every unsaved edit. */
let guard = null;

export function setLeaveGuard(fn) {
  guard = fn;
  return () => { if (guard === fn) guard = null; };
}

/** true when it is safe to leave (nothing unsaved, or the person agreed to lose it) */
export function canLeave() {
  if (!guard || !guard()) return true;
  return window.confirm(tr("Tinggalkan Kanvas tanpa simpan? Perubahan terakhir hilang.",
    "Leave Kanvas without saving? The last changes are lost."));
}
