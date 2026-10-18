import { ModuleView } from "./ModuleView";

// /module/<repo>/<path...>?org=<org>  ->  module:<repo>:<path> (the repo root is module:<repo>:/).
export default async function ModulePage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string[] }>;
  searchParams: Promise<{ org?: string }>;
}) {
  const [{ id }, { org }] = await Promise.all([params, searchParams]);
  const [repo, ...path] = id.map(decodeURIComponent);
  return <ModuleView moduleId={`module:${repo}:${path.join("/") || "/"}`} org={org} />;
}
