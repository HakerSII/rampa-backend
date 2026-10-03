# F41 — Remote MCP: public MCP server as a separate Render service

Overview: [../../README.md](../../README.md) · extends [../08-osm-mcp/plan.md](../08-osm-mcp/plan.md) (stdio)

- Goal: local apps (Claude Desktop / Code, Gemini CLI, Grok and other MCP clients) connect to **one public MCP URL** instead of running the server locally.
- `clients/mcp_server.py`: `MCP_TRANSPORT=stdio` (default, local) | `http` → Streamable HTTP at `/mcp` (stateless), `GET /health` for Render. Same tools as stdio (`check_accessibility`, `search_accessible_places`), still a client of the Open API (`RAMPA_API_URL`, `RAMPA_API_KEY`).
- Optional `MCP_AUTH_TOKEN`: when set, `/mcp` needs `Authorization: Bearer <token>` (clients that can send headers: Claude Code, Gemini CLI). Empty = public read-only (needed for claude.ai custom connectors, which support only no-auth or OAuth).
- `Dockerfile.mcp` → second Render web service (Docker). Port from `$PORT`.
- Limits: read-only tools; all MCP users share the backend API key rate limit (`PUBLIC_RATE_LIMIT_PER_MIN`).
