# AI Agent Asset Reporter 📊

A lightweight, zero-dependency, cross-platform utility plugin designed for AI coding agents (such as **Google Antigravity**, **Claude Code**, **Cursor**, **Codex**, and **Devin**). It scans your project's AI assets (custom Skills and Rules) and audits which ones were actually read, triggered, or referenced during your chat session, printing a neat Markdown report when the session terminates.

## 🌟 Why use this?
When customizing AI agents, developers write custom **Skills** (`SKILL.md`) and **Rules** (`AGENTS.md`, `RULES.md`, `rules/*.md`). Over time, custom assets can become stale or bloated. This tool helps you:
- Identify "dead" or unused customized rules and skills.
- Verify whether the agent is actually adopting the correct guidelines in its execution path.
- Optimize your prompt token budgets by pruning unused skills and rules.

---

## 🚀 How it works
On session exit, the agent framework fires a `Stop` or `SessionEnd` hook. The framework sends metadata to this plugin via `stdin`. The reporter script:
1. Scans the workspace directory to index all available Skills and Rules.
2. Parses the session transaction logs (`transcript.jsonl` or other platform logs).
3. Matches file access logs (e.g. `view_file` or `read_file` calls) against indexed assets.
4. Outputs a summary Markdown report directly to your terminal.

---

## 📦 Setup Guides

### 1. Google Antigravity & Claude Code
Antigravity and Claude Code automatically scan project plugins from `.agents/plugins/` (or global `~/.gemini/config/plugins/`).

* **Workspace Hook Setup**:
  Clone or symlink this folder inside your workspace:
  ```bash
  ln -s /path/to/ai-agent-asset-reporter your-project/.agents/plugins/session-asset-reporter
  ```
  *(On Windows PowerShell, run: `New-Item -ItemType SymbolicLink -Path "your-project\.agents\plugins\session-asset-reporter" -Target "\path\to\ai-agent-asset-reporter"`)*

* **Configuration**:
  The provided `hooks.json` will automatically route the `Stop` event to `scripts/report.py`.

---

### 2. Devin
Devin intercepts execution via project-level configurations in `.devin/hooks.v1.json`.

* **Configuration**:
  Copy the contents of `devin-hooks.json` into your project's `.devin/hooks.v1.json` file:
  ```json
  {
    "Stop": [
      {
        "type": "command",
        "command": "python .agents/plugins/session-asset-reporter/scripts/report.py"
      }
    ]
  }
  ```

---

### 3. Cursor
Cursor supports session lifecycle scripts.

* **Configuration**:
  Ensure the script is triggered on session end by copying `hooks-cursor.json` to your local settings, or executing `report.py` manually when ending a debugging workspace session.

---

### 4. Codex
Codex discovers plugins via `.codex-plugin/`.

* **Configuration**:
  The `.codex-plugin/plugin.json` in this repository handles automatic mapping. Register this plugin directory within your Codex configuration (`~/.codex/config.toml`).

---

## 🛠️ CLI Manual Mode (Local Audit)
You can also run the audit manually against any saved transcript log:
```bash
python scripts/report.py --workspace /path/to/project --transcript /path/to/transcript.jsonl
```

---

## 📄 License
This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.
