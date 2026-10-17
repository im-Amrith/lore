"use client";

import { useEffect, useState } from "react";
import { createUser, getUsers, type User } from "@/lib/api";

export type Org = { id: string; label: string };

export function Header({
  orgs, org, onOrg, user, onUser,
}: {
  orgs: Org[];
  org: string;
  onOrg: (id: string) => void;
  user: string | null;
  onUser: (id: string) => void;
}) {
  return (
    <header className="flex h-14 shrink-0 items-center gap-6 border-b border-line bg-surface/80 px-5 backdrop-blur">
      <div className="flex items-baseline gap-3">
        <span className="font-serif text-xl font-semibold tracking-tight text-ink">Lore</span>
        <span className="hidden text-xs text-muted md:inline">who owns · who knows · why it was decided</span>
      </div>

      <nav aria-label="Organisation" className="ml-auto flex rounded-lg border border-line bg-sunk p-0.5">
        {orgs.map((o) => (
          <button
            key={o.id}
            onClick={() => onOrg(o.id)}
            aria-pressed={o.id === org}
            className={`rounded-md px-3 py-1 text-sm transition-colors ${
              o.id === org ? "bg-surface font-medium text-ink shadow-sm" : "text-muted hover:text-ink"
            }`}
          >
            {o.label}
          </button>
        ))}
      </nav>

      <UserPicker user={user} onUser={onUser} />
    </header>
  );
}

function UserPicker({ user, onUser }: { user: string | null; onUser: (id: string) => void }) {
  const [users, setUsers] = useState<User[]>([]);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [login, setLogin] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refresh = () => getUsers().then(setUsers).catch(() => setUsers([]));
  useEffect(() => {
    refresh();
  }, []);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const u = await createUser(name.trim(), login.trim() || undefined);
      await refresh();
      onUser(u.id);
      setAdding(false);
      setName("");
      setLogin("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  if (adding || (!user && users.length === 0)) {
    return (
      <form onSubmit={add} className="relative flex items-center gap-2">
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="your name"
          aria-label="Username"
          className="w-28 rounded-md border border-line-strong bg-surface px-2 py-1 text-sm outline-none focus:border-accent"
        />
        <input
          value={login}
          onChange={(e) => setLogin(e.target.value)}
          placeholder="GitHub login (optional)"
          aria-label="GitHub login, optional"
          className="hidden w-44 rounded-md border border-line bg-surface px-2 py-1 text-sm outline-none focus:border-accent lg:block"
        />
        <button className="rounded-md bg-ink px-3 py-1 text-sm text-surface hover:bg-ink-2" disabled={!name.trim()}>
          Join
        </button>
        {users.length > 0 && (
          <button type="button" onClick={() => setAdding(false)} className="text-sm text-muted hover:text-ink">
            Cancel
          </button>
        )}
        {error && <span className="absolute right-0 top-9 w-72 text-right text-xs text-miss">{error}</span>}
      </form>
    );
  }

  return (
    <label className="flex items-center gap-2 text-sm text-muted">
      <span className="sr-only md:not-sr-only">Asking as</span>
      <select
        value={user ?? ""}
        onChange={(e) => (e.target.value === "__new" ? setAdding(true) : onUser(e.target.value))}
        className="rounded-md border border-line bg-surface px-2 py-1 text-sm text-ink outline-none focus:border-accent"
      >
        {!user && <option value="">pick a name</option>}
        {users.map((u) => (
          <option key={u.id} value={u.id}>
            {u.id}
            {u.github_login ? ` (@${u.github_login})` : ""}
          </option>
        ))}
        <option value="__new">+ New user…</option>
      </select>
    </label>
  );
}
