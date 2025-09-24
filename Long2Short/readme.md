# L2S Two-Pass Plugin Proxy (minimal)

What this does
- Provides a small FastAPI proxy the ChatGPT plugin can call.
- Orchestrates two calls to your existing /process:
  1) phase="overlay" (runs overlays-only and synthesizes SRTs)
  2) phase="burn" (burns subtitles on the produced overlaid clips)
- Serves the plugin manifest and openapi.yaml so you can install the plugin from your ngrok URL.

Files
- plugin_proxy.py   - the proxy server
- openapi.yaml      - OpenAPI spec (replace servers.url with your ngrok host)
- ai-plugin.json    - plugin manifest (replace URLs with ngrok host)

Quick setup
1. Put plugin_proxy.py, openapi.yaml, ai-plugin.json in the same folder.
2. Edit openapi.yaml and ai-plugin.json: replace `REPLACE_WITH_YOUR_NGROK_HOST` with your ngrok HTTPS domain (e.g. https://abcd-12-34-56.ngrok.io).
3. Set environment variables:
   - PROCESS_URL (default: http://localhost:8000/process)
   - PLUGIN_SECRET (must match ChatGPT plugin bearer token)
4. Install deps:
   pip install fastapi uvicorn requests
5. Start proxy:
   PLUGIN_SECRET="my-secret" PROCESS_URL="http://localhost:8000/process" uvicorn plugin_proxy:app --host 0.0.0.0 --port 3333
6. Expose via ngrok:
   ngrok http 3333
   Copy the HTTPS forwarding URL (e.g. https://abcd-12-34-56.ngrok.io)
7. Update ai-plugin.json and openapi.yaml (if not already) to use the ngrok URL (openapi.yaml server url must match).
8. In ChatGPT (Custom GPT / Plugins):
   - Install plugin using manifest URL:
     https://<your-ngrok-host>/.well-known/ai-plugin.json
   - When ChatGPT prompts for the plugin bearer token, supply the same value as PLUGIN_SECRET.
9. Use the plugin /submit_two_pass action from the assistant (the assistant will now call the proxy which will orchestrate overlay+burn).

Minimal system-prompt snippet (add to your Custom GPT/system instructions)
- "When you have produced a validated recipe JSON for two-pass processing, call the plugin operation l2s_two_pass.submit_two_pass with body {\"recipe\": <recipe>, \"two_pass\": true}. Wait for the operation to complete; the proxy will run the overlay phase then the burn phase and return combined results."

Notes and recommendations
- Timeout: default per-phase timeout is 900s (15m). Tune wait_timeout_seconds in the request if needed.
- Security: never publish PLUGIN_SECRET. Use ngrok's HTTPS for secure transport.
- Logging: the proxy logs to stdout. Watch it while testing.
- If your /process returns streaming NDJSON for overlays, the proxy will block until that POST completes. If you prefer streaming the logs through to ChatGPT, I can extend the proxy to forward NDJSON event-by-event (more complex).

If you want, I can:
- Provide an updated proxy that streams the overlays NDJSON back to ChatGPT (so the assistant receives logs as they happen).
- Or produce a one-line patch that modifies L2S-server.py to accept a "phase" hint if you prefer no double-posting (but proxy is safer).
