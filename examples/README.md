# Client configuration snippets

Drop the matching file into your client's MCP config location and edit the
`ADB_MCP_CONFIG` path if you keep a custom `config.yaml`.

| Client | File here | Where it goes |
|---|---|---|
| Claude Desktop | [claude_desktop_config.json](claude_desktop_config.json) | `%APPDATA%\Claude\claude_desktop_config.json` (Win) / `~/Library/Application Support/Claude/claude_desktop_config.json` (mac) |
| Cursor | [cursor.mcp.json](cursor.mcp.json) | `~/.cursor/mcp.json` or `<project>/.cursor/mcp.json` |
| Cline (VS Code) | [cline_mcp_settings.json](cline_mcp_settings.json) | Cline → MCP Servers → "Configure MCP Servers" |
| Antigravity | [antigravity_mcp_config.json](antigravity_mcp_config.json) | Antigravity → Settings → MCP servers |
| OpenCode | [opencode.json](opencode.json) | `<project>/opencode.json` or `~/.config/opencode/opencode.json` |
| LM Studio | [lmstudio_mcp.json](lmstudio_mcp.json) | LM Studio → Program → Install → Edit `mcp.json` (or `~/.lmstudio/mcp.json`) |
| mcphost (Ollama bridge) | [mcphost.json](mcphost.json) | Pass with `mcphost --config ./mcphost.json --model ollama:qwen3:14b` |

The `mcpServers` JSON shape is shared by most clients — if your client isn't
listed, try the Claude Desktop snippet first and consult your client's docs
for the exact file path.
