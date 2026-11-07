import RepoLibrary from "../components/RepoLibrary";

/* Repo library: the GitHub links Wan pastes, read and filed by the AI (components/RepoLibrary.jsx, which draws its own title).
   It used to share a page with the office repos' health board; Wan asked for them apart (11 Oct 2026: "office repo macam di
   atas, kena asingkan"), and the board is now its own page, Office repos (pages/OfficeTab.jsx). */
export default function RepoTab({ settings, onToast, user }) {
  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <RepoLibrary settings={settings} user={user} onToast={onToast} />
    </main>
  );
}
