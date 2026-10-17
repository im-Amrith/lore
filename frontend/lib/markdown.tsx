// Just enough Markdown for a triage draft, rendered as React elements (no raw HTML): paragraphs,
// "-"/"*" bullets, [text](url) links, **bold** and `code`. It previews what GitHub will show.

import type { ReactNode } from "react";

const INLINE = /(\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|\*\*([^*]+)\*\*|`([^`]+)`|(https?:\/\/[^\s)]+))/g;

function inline(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let n = 0;
  for (const m of text.matchAll(INLINE)) {
    if (m.index! > last) out.push(text.slice(last, m.index));
    const k = `${key}-${n++}`;
    if (m[2] && m[3]) {
      out.push(
        <a key={k} href={m[3]} target="_blank" rel="noreferrer" className="text-accent underline decoration-accent/30 underline-offset-2 hover:decoration-accent">
          {m[2]}
        </a>,
      );
    } else if (m[4]) {
      out.push(<strong key={k}>{m[4]}</strong>);
    } else if (m[5]) {
      out.push(
        <code key={k} className="rounded bg-sunk px-1 py-0.5 font-mono text-[0.85em]">
          {m[5]}
        </code>,
      );
    } else if (m[6]) {
      out.push(
        <a key={k} href={m[6]} target="_blank" rel="noreferrer" className="break-all text-accent underline underline-offset-2">
          {m[6]}
        </a>,
      );
    }
    last = m.index! + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let bullets: string[] = [];
  let para: string[] = [];
  const flush = () => {
    if (para.length) {
      blocks.push(<p key={`p${blocks.length}`}>{inline(para.join(" "), `p${blocks.length}`)}</p>);
      para = [];
    }
    if (bullets.length) {
      const k = `u${blocks.length}`;
      blocks.push(
        <ul key={k} className="list-disc space-y-1 pl-5 marker:text-muted">
          {bullets.map((b, i) => (
            <li key={i}>{inline(b, `${k}-${i}`)}</li>
          ))}
        </ul>,
      );
      bullets = [];
    }
  };
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    if (bullet) {
      if (para.length) flush();
      bullets.push(bullet[1]);
    } else if (!line.trim()) {
      flush();
    } else {
      if (bullets.length) flush();
      para.push(line.replace(/^#+\s*/, ""));
    }
  }
  flush();
  return <div className="space-y-2">{blocks}</div>;
}
