/**
 * Proxy route: forwards /api/openapi-spec → http://localhost:9000/openapi.json
 * Required by the API reference page to avoid CORS issues.
 */
export async function GET() {
  try {
    const res = await fetch('http://localhost:9000/openapi.json', {
      next: { revalidate: 30 },
    });
    if (!res.ok) throw new Error('upstream error');
    const spec = await res.json();
    return Response.json(spec);
  } catch {
    return new Response(
      JSON.stringify({
        error: 'FastAPI server not reachable. Start it with: python3 -m uvicorn app.main:app --reload --port 8000',
      }),
      { status: 503, headers: { 'Content-Type': 'application/json' } },
    );
  }
}
