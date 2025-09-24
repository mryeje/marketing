```markdown
# Integrating ChatGPT plugin router into your existing L2S server (no extra ngrok)

What this gives you
- A tiny APIRouter (plugin_router.py) you include into your existing L2S-server FastAPI app.
- The router serves:
  - GET /.well-known/ai-plugin.json  (the plugin manifest)
  - GET /openapi.yaml               (OpenAPI spec)
  - POST /submit_two_pass           (orchestrates overlay -> burn by calling /process twice)
- Because it's included in the same server that your ngrok tunnel already exposes, you don't need a separate tunnel.

Files
- plugin_router.py
- ai-plugin.json (edit manifest URL below)
- openapi.yaml (edit server url below)

Steps to integrate
1. Put plugin_router.py, ai-plugin.json, openapi.yaml next to your L2S-server.py (same directory).
2. Edit ai-plugin.json and openapi.yaml: replace REPLACE_WITH_YOUR_NGROK_HOST with your HTTPS ngrok domain, e.g. https://abcd-12-34-56.ngrok.io
   - Example plugin manifest url will be: https://abcd-12-34-56.ngrok.io/.well-known/ai-plugin.json
3. In L2S-server.py, import and include the router. Near other router includes, add:
   ```python
   from plugin_router import router as plugin_router
   app.include_router(plugin_router)
   ```
   (Place after app = FastAPI(...) and before uvicorn.run if present.)
4. Set env vars (optional, defaults shown):
   - PROCESS_URL (default: http://localhost:8000/process) — adjust if /process listens on a different port
   - PLUGIN_SECRET (default: change-me-secret) — pick a secret and use it in ChatGPT plugin config
5. Restart your server so the new routes are available.
6. Install the plugin into ChatGPT:
   - In ChatGPT plugin install UI, provide the manifest URL:
     https://<your-ngrok-host>/.well-known/ai-plugin.json
   - When prompted, enter the Bearer token equal to PLUGIN_SECRET.
7. Test the proxy locally (optional):
   curl -v -X POST "http://localhost:8000/submit_two_pass" \
     -H "Authorization: Bearer my-secret" \
     -H "Content-Type: application/json" \
     -d '{"recipe":{"src":"file:///C:/path/to/video.mp4","clips":[{"id":"01","start":10,"end":20}]}}'
8. Use the plugin from your Custom GPT or assistant. The assistant calls /submit_two_pass and the router will:
   - POST {"recipe":..., "phase":"overlay"} to /process and wait
   - If overlay succeeds, POST {"recipe":..., "phase":"burn"} to /process and wait
   - Return combined results to ChatGPT

Notes & tips
- If your /process returns NDJSON streaming logs, the router will block until the POST returns or times out. The router uses a default per-phase timeout of 900s; change using wait_timeout_seconds in the request.
- Keep PLUGIN_SECRET secret. Do NOT check it into public repos.
- If you want to stream overlay logs back through the plugin (so ChatGPT sees logs as they happen), I can extend the router to proxy NDJSON streaming — that’s a small extra change.
```