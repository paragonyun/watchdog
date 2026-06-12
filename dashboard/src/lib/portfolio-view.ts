import type { DashboardView } from "./dashboard-view";

export type PortfolioSection = DashboardView["groups"][number] & {
  assets: DashboardView["assets"];
};

export function buildPortfolioSections(view: DashboardView): PortfolioSection[] {
  return view.groups.map((group) => ({
    ...group,
    assets: view.assets
      .filter((asset) => asset.assetType === group.key)
      .sort((left, right) => right.valueKrw - left.valueKrw),
  }));
}
