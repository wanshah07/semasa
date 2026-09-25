import AuthPanel from "./AuthPanel";

/* Everything except the headlines is private to accounts on semasa_uploaders. */
export default function Gate({ user, ready, canUpload, onToast, children }) {
  if (!ready) return null;
  if (!user) return <AuthPanel onToast={onToast} />;
  if (canUpload === null) return null;
  if (!canUpload) {
    return (
      <div className="mx-auto max-w-md rounded-card border border-line bg-surface p-6 shadow-card">
        <h3 className="text-lg">Akaun ini belum dibenarkan</h3>
        <p className="mt-2 text-sm text-muted">
          {user.email} sudah log masuk, tetapi tiada dalam senarai <code>semasa_uploaders</code>. Tambah akaun ini
          dalam Supabase SQL editor (README, langkah 3).
        </p>
      </div>
    );
  }
  return children;
}
