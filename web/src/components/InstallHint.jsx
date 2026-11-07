import { useState } from "react";
import { Share, X } from "lucide-react";
import { browserFacts, readDismissed, shouldShowInstallHint, writeDismissed } from "../lib/pwa";

const store = () => { try { return window.localStorage; } catch { return null; } };

/* "Pasang di iPhone": shown only in Safari on an iPhone or iPad that has not added Semasa to its Home Screen yet. iOS has
   no install button a page can press, so the hint names the two taps. Malay first and English under it on purpose, in
   both languages at once: it is read before anyone has picked a language, often on the sign-in screen. Closing it is
   remembered on this phone. The words follow iOS's own menus in each language (Kongsi / Tambah ke Skrin Utama). */
export default function InstallHint() {
  const [show, setShow] = useState(() => shouldShowInstallHint({ ...browserFacts(), dismissed: readDismissed(store()) }));
  if (!show) return null;
  const close = () => { writeDismissed(store()); setShow(false); };
  return (
    <aside role="note" data-install-hint aria-label="Pasang Semasa di iPhone"
      className="install-hint fixed inset-x-3 z-[45] mx-auto max-w-md rounded-card border border-line bg-surface p-4 pr-14 shadow-lift">
      <p className="text-sm font-semibold text-ink">Pasang Semasa di iPhone</p>
      <p className="mt-1 text-sm text-ink">
        Tekan <Share size={15} className="inline align-[-2px]" aria-label="Kongsi" /> <b>Kongsi</b> di bar Safari, kemudian pilih <b>Tambah ke Skrin Utama</b>.
      </p>
      <p className="mt-2 text-xs text-muted">
        Install Semasa on your iPhone: tap <b>Share</b> in Safari&apos;s bar, then <b>Add to Home Screen</b>.
      </p>
      <button type="button" onClick={close} aria-label="Tutup / Close" data-install-hint-close
        className="absolute right-1 top-1 grid h-11 w-11 place-items-center rounded-full text-muted transition hover:bg-surface-2 hover:text-ink">
        <X size={18} />
      </button>
    </aside>
  );
}
