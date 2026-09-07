export function GET(): Response {
  return Response.json(
    { status: "ok", component: "frontend" },
    { headers: { "cache-control": "no-store" } },
  );
}
