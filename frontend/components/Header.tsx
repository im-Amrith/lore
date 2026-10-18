"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { createUser, getUsers, type User } from "@/lib/api";

export type Org = { id: string; label: string };

const SCREENS = [
  { href: "/", label: "Ask" },
  { href: "/triage", label: "Triage" },
  { href: "/risk", label: "Risk" },
];

export function Header({
  orgs = [], org, onOrg, user, onUser,
}: {
  orgs?: Org[];
  org?: string;
  onOrg?: (id: string) => void;
  user: string | null;
  onUser: (id: string) => void;
}) {
  const pathname = usePathname();
  return (
    <header className="flex h-14 shrink-0 items-center gap-4 border-b border-line bg-surface/80 px-5 backdrop-blur md:gap-6">
      <div className="flex items-baseline gap-3">
        <span className="font-serif text-xl font-semibold tracking-tight text-ink">Lore</span>
        <span className="hidden text-xs text-muted xl:inline">who owns · who knows · why it was decided</span>
      </div>

      <nav aria-label="Screens" className="flex gap-1">
        {SCREENS.map((s) => {
          const here = s.href === "/" ? pathname === "/" : pathname?.startsWith(s.href);
          return (
            <Link
              key={s.href}
              href={s.href}
              aria-current={here ? "page" : undefined}
              className={`rounded-md px-2.5 py-1 text-sm transition-colors ${
                here ? "bg-sunk font-medium text-ink" : "text-muted hover:text-ink"
              }`}
            >
              {s.label}
            </Link>
          );
        })}
      </nav>

      <nav aria-label="Organisation" className={`ml-auto rounded-lg border border-line bg-sunk p-0.5 ${orgs.length ? "flex" : "hidden"}`}>
        {orgs.map((o) => (
          <button
            key={o.id}
            onClick={() => onOrg?.(o.id)}
            aria-pressed={o.id === org}
            className={`rounded-md px-3 py-1 text-sm transition-colors ${
              o.id === org ? "bg-surface font-medium text-ink shadow-sm" : "text-muted hover:text-ink"
            }`}
          >
            {o.label}
          </button>
        ))}
      </nav>

      <div className={orgs.length ? "" : "ml-auto"}>
        <UserPicker user={user} onUser={onUser} />
      </div>
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
