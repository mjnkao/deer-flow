const AICOS_X_MCP_URL =
  process.env.AICOS_X_MCP_URL ?? "http://127.0.0.1:37031/mcp";

function healthUrl() {
  const url = new URL(AICOS_X_MCP_URL);
  url.pathname = url.pathname.replace(/\/mcp\/?$/, "/health");
  return url;
}

export async function GET() {
  try {
    const response = await fetch(healthUrl(), {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const text = await response.text();
    return new Response(text, {
      status: response.status,
      headers: {
        "content-type":
          response.headers.get("content-type") ?? "application/json",
      },
    });
  } catch (error) {
    return Response.json(
      {
        ok: false,
        error_code: "aicos_x_unavailable",
        message: error instanceof Error ? error.message : "AICOS-X unavailable",
      },
      { status: 503 },
    );
  }
}
