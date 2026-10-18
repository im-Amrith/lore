import { RiskView } from "./RiskView";

export default async function RiskPage({ searchParams }: { searchParams: Promise<{ org?: string }> }) {
  const { org } = await searchParams;
  return <RiskView initialOrg={org} />;
}
