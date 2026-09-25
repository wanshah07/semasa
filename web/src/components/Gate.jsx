import { useLang } from "../lib/i18n";
import AuthPanel from "./AuthPanel";

/* Everything except the headlines is private to accounts on semasa_uploaders. */
export default function Gate({ user, ready, canUpload, onToast, children }) {
  const { lang, t } = useLang();
  if (!ready) return null;
  if (!user) return <AuthPanel onToast={onToast} />;
  if (canUpload === null) return null;
  if (!canUpload) {
    return (
      <div className="mx-auto max-w-md rounded-card border border-line bg-surface p-6 shadow-card">
        <h3 className="text-lg">{t("Akaun ini belum dibenarkan", "This account is not allowed yet")}</h3>
        <p className="mt-2 text-sm text-muted">
          {lang === "en" ? (
            <>
              {user.email} is signed in, but is not on the <code>semasa_uploaders</code> list. Add this account
              in the Supabase SQL editor (README, step 3).
            </>
          ) : (
            <>
              {user.email} sudah log masuk, tetapi tiada dalam senarai <code>semasa_uploaders</code>. Tambah akaun ini
              dalam Supabase SQL editor (README, langkah 3).
            </>
          )}
        </p>
      </div>
    );
  }
  return children;
}
