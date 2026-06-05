import type { AssetSummary, DashboardPayload } from "./dashboard-payload";

export type AssetSectionKey = "equity" | "coin" | "cash";

export type AssetSection = {
  key: AssetSectionKey;
  label: string;
  value_krw: number;
  weight_percent: number;
  assets: AssetSummary[];
};

const SECTION_META: Array<{ key: AssetSectionKey; label: string }> = [
  { key: "equity", label: "ISA" },
  { key: "coin", label: "코인" },
  { key: "cash", label: "현금" },
];

export function buildAssetSections(
  assets: AssetSummary[],
  groups: DashboardPayload["asset_groups"],
  totalValueKrw: number,
): AssetSection[] {
  return SECTION_META.map(({ key, label }) => {
    const value = groups[key] ?? 0;
    return {
      key,
      label,
      value_krw: value,
      weight_percent: roundPercent(totalValueKrw <= 0 ? 0 : (value / totalValueKrw) * 100),
      assets: assets.filter((asset) => asset.asset_type === key).sort((a, b) => b.value_krw - a.value_krw),
    };
  });
}

function roundPercent(value: number): number {
  return Math.round(value * 100) / 100;
}
