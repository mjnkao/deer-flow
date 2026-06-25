const DASHBOARD_URL =
  process.env.AICOS_DASHBOARD_URL ?? "/aicos-dashboard/index.html";

type AicosDashboardView = "facet" | "work-units" | "chat";

const DEFAULT_DASHBOARD_VIEW: AicosDashboardView = "facet";

export const dynamic = "force-dynamic";

function normalizeDashboardView(value?: string | string[]): AicosDashboardView {
  const raw = Array.isArray(value) ? value[0] : value;
  const normalized = raw?.trim().toLowerCase().replaceAll("_", "-");
  if (
    normalized === "work-unit-board" ||
    normalized === "work-units-board" ||
    normalized === "outcome-board" ||
    normalized === "outcomes" ||
    normalized === "trello" ||
    normalized === "board" ||
    normalized === "facet"
  ) {
    return "facet";
  }
  if (
    normalized === "control" ||
    normalized === "control-room" ||
    normalized === "work-units"
  ) {
    return "work-units";
  }
  if (normalized === "legacy") return "facet";
  if (normalized === "chat") return "chat";
  return DEFAULT_DASHBOARD_VIEW;
}

function getDashboardEmbedUrl(view: AicosDashboardView) {
  if (DASHBOARD_URL.startsWith("/")) {
    const params = new URLSearchParams({
      embed: "deerflow",
      scope: "aicos-x",
      view,
    });
    return `${DASHBOARD_URL}${DASHBOARD_URL.includes("?") ? "&" : "?"}${params.toString()}`;
  }
  const url = new URL(DASHBOARD_URL, "http://127.0.0.1:2026");
  url.searchParams.set("embed", "deerflow");
  url.searchParams.set("scope", "aicos-x");
  url.searchParams.set("view", view);
  return url.toString();
}

export default async function AicosWorkspacePage(props: {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  const searchParams = await props.searchParams;
  const activeView = normalizeDashboardView(searchParams?.view);
  const dashboardEmbedUrl = getDashboardEmbedUrl(activeView);

  return (
    <main className="bg-background h-screen min-h-0 overflow-hidden">
      <iframe
        className="h-full w-full border-0"
        src={dashboardEmbedUrl}
        title="AICOS-X Work Unit Board"
      />
    </main>
  );
}
