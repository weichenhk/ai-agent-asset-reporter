import sys
import os
import json
import re
from datetime import datetime

# 确保在 Windows 控制台等 GBK 终端下，能够正常输出 UTF-8 编码字符（如 Emoji 和中文）
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


def normalize_path(p):
    """统一路径格式，用于路径匹配比对"""
    if not p:
        return ""
    # 去除首尾引号
    p = p.strip('"\'')
    try:
        return os.path.abspath(p).replace('\\', '/').lower()
    except Exception:
        return p.replace('\\', '/').lower()


def get_real_path(p):
    """解析 Junction / Symlink 后获取真实物理路径"""
    if not p:
        return ""
    try:
        return os.path.realpath(p).replace('\\', '/').lower()
    except Exception:
        return normalize_path(p)


def load_payload():
    """从 stdin 或 命令行参数加载平台传入的元数据 payload"""
    payload = {}
    
    # 如果命令行里带了参数（如 --transcript 或 --workspace），解析 CLI 参数
    args = sys.argv[1:]
    for i in range(len(args)):
        if args[i] == '--transcript' and i + 1 < len(args):
            payload['transcriptPath'] = args[i+1]
        elif args[i] == '--workspace' and i + 1 < len(args):
            payload.setdefault('workspacePaths', []).append(args[i+1])

    # 如果非 CLI 模式，尝试从 stdin 读取 JSON
    if not payload:
        try:
            if not sys.stdin.isatty():
                data = sys.stdin.read().strip()
                if data:
                    stdin_payload = json.loads(data)
                    if isinstance(stdin_payload, dict):
                        payload = stdin_payload
        except Exception:
            pass

    # 归一化 workspacePaths 字段（兼顾单数与复数字段）
    workspaces = []
    ws_raw = (
        payload.get('workspacePaths') or
        payload.get('workspace_paths') or
        payload.get('workspacePath') or
        payload.get('workspace_path') or
        payload.get('workspace')
    )
    if ws_raw:
        if isinstance(ws_raw, list):
            workspaces.extend([str(w) for w in ws_raw if w])
        elif isinstance(ws_raw, str):
            workspaces.append(ws_raw)

    if not workspaces:
        workspace = os.environ.get('WORKSPACE_ROOT') or os.getcwd()
        workspaces.append(workspace)
        
    payload['workspacePaths'] = list(dict.fromkeys(workspaces)) # 去重

    # 归一化 transcriptPath 字段
    transcript = (
        payload.get('transcriptPath') or
        payload.get('transcript_path') or
        payload.get('transcript_file') or
        payload.get('logPath') or
        payload.get('log_path')
    )
    if transcript:
        payload['transcriptPath'] = str(transcript)

    return payload


def scan_assets(workspace_paths):
    """扫描所有工作区及常用目录下的技能 (Skills) 和规则 (Rules)"""
    skills = {} # skill_key -> { "name": str, "dir": str, "real_dir": str, "skill_md": str, "real_skill_md": str }
    rules = {}  # rule_key  -> { "name": str, "path": str, "real_path": str }
    
    # 常用 skills 目录名称
    skills_dir_names = ['.agents/skills', '_agents/skills', 'skills', '.devin/skills']
    # 常用 rules 目录名称
    rules_dir_names = ['.agents/rules', '_agents/rules', 'rules', '.devin/rules']
    
    # 扫描路径列表
    paths_to_scan = list(workspace_paths)
    
    # 扫描全局配置目录
    global_dirs = [
        os.path.expanduser('~/.gemini/config'),
        os.path.expanduser('~/.claude'),
        os.path.expanduser('~/.devin')
    ]
    for g_dir in global_dirs:
        if os.path.exists(g_dir):
            paths_to_scan.append(g_dir)
            
    for base_path in paths_to_scan:
        if not os.path.exists(base_path):
            continue
            
        # 1. 扫描 Skills 目录
        for s_dir in skills_dir_names:
            full_skills_dir = os.path.join(base_path, s_dir)
            if os.path.isdir(full_skills_dir):
                for item in os.listdir(full_skills_dir):
                    item_path = os.path.join(full_skills_dir, item)
                    if os.path.isdir(item_path):
                        skill_md = os.path.join(item_path, 'SKILL.md')
                        if os.path.exists(skill_md):
                            key = item.lower()
                            skills[key] = {
                                "name": item,
                                "dir": normalize_path(item_path),
                                "real_dir": get_real_path(item_path),
                                "skill_md": normalize_path(skill_md),
                                "real_skill_md": get_real_path(skill_md)
                            }
                            
        # 2. 扫描 Rules 目录
        for r_dir in rules_dir_names:
            full_rules_dir = os.path.join(base_path, r_dir)
            if os.path.isdir(full_rules_dir):
                for item in os.listdir(full_rules_dir):
                    if item.endswith('.md'):
                        name = item[:-3]
                        file_path = os.path.join(full_rules_dir, item)
                        key = name.lower()
                        rules[key] = {
                            "name": name,
                            "path": normalize_path(file_path),
                            "real_path": get_real_path(file_path)
                        }

        # 3. 递归扫描 library/base 目录下的受控 Domains 资产
        lib_domains_dir = os.path.join(base_path, 'library', 'base', 'domains')
        if os.path.isdir(lib_domains_dir):
            for domain_item in os.listdir(lib_domains_dir):
                d_path = os.path.join(lib_domains_dir, domain_item)
                if os.path.isdir(d_path):
                    # 扫描 domain 下的 skills
                    d_skills = os.path.join(d_path, 'skills')
                    if os.path.isdir(d_skills):
                        for item in os.listdir(d_skills):
                            item_path = os.path.join(d_skills, item)
                            if os.path.isdir(item_path):
                                skill_md = os.path.join(item_path, 'SKILL.md')
                                if os.path.exists(skill_md):
                                    key = item.lower()
                                    if key not in skills:
                                        skills[key] = {
                                            "name": item,
                                            "dir": normalize_path(item_path),
                                            "real_dir": get_real_path(item_path),
                                            "skill_md": normalize_path(skill_md),
                                            "real_skill_md": get_real_path(skill_md)
                                        }

        # 4. 扫描根目录的 AGENTS.md 或 RULES.md
        for filename in ['AGENTS.md', 'RULES.md', 'CLAUDE.md']:
            file_path = os.path.join(base_path, filename)
            if os.path.isfile(file_path):
                key = filename.lower()
                rules[key] = {
                    "name": filename,
                    "path": normalize_path(file_path),
                    "real_path": get_real_path(file_path)
                }
                
    return skills, rules


def match_file_to_asset(norm_file, real_file, skills, rules):
    """校验指定被访问的文件路径是否命中某个 Skill 或 Rule"""
    # 1. 匹配 Skill：允许命中 SKILL.md，或者命中技能目录下的任意支撑文件 (references/*.md, scripts/*)
    for skill_key, s_info in skills.items():
        s_dir = s_info['dir']
        s_real_dir = s_info['real_dir']
        
        # 判断文件路径是否位于技能目录下 (按前缀判断)
        if norm_file.startswith(s_dir + '/') or norm_file == s_dir:
            return 'skill', skill_key
        if s_real_dir and (real_file.startswith(s_real_dir + '/') or real_file == s_real_dir):
            return 'skill', skill_key

    # 2. 匹配 Rule
    for rule_key, r_info in rules.items():
        if norm_file == r_info['path'] or (r_info['real_path'] and real_file == r_info['real_path']):
            return 'rule', rule_key

    return None, None


def analyze_transcript(transcript_path, skills, rules):
    """解析 transcript.jsonl，查找被使用的 AI 资产"""
    used_skills = {} # skill_key -> count
    used_rules = {}  # rule_key  -> count
    
    if not transcript_path or not os.path.exists(transcript_path):
        return used_skills, used_rules
        
    try:
        with open(transcript_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    step = json.loads(line)
                except Exception:
                    continue
                
                # 1. 检查工具调用 (tool_calls)
                tool_calls = step.get('tool_calls') or []
                for call in tool_calls:
                    args = call.get('args') or {}
                    file_path = args.get('AbsolutePath') or args.get('path') or args.get('TargetFile') or args.get('target_file')
                    if file_path and isinstance(file_path, str):
                        norm_file = normalize_path(file_path)
                        real_file = get_real_path(file_path)
                        
                        asset_type, key = match_file_to_asset(norm_file, real_file, skills, rules)
                        if asset_type == 'skill':
                            used_skills[key] = used_skills.get(key, 0) + 1
                        elif asset_type == 'rule':
                            used_rules[key] = used_rules.get(key, 0) + 1

                # 2. 检查 content 中的规则标签或路径硬引用
                content = step.get('content') or ""
                if content:
                    # 扫描是否有包含规则标签的内容，如 <RULE[unittest.md]> 或 <RULE[AGENTS.md]>
                    rule_matches = re.findall(r'<RULE\[([^\]]+)\]>', content)
                    for rule_tag in rule_matches:
                        tag_lower = rule_tag.lower()
                        # 精确或包含规则名匹配
                        for r_key in rules:
                            if r_key == tag_lower or r_key.startswith(tag_lower) or tag_lower.startswith(r_key):
                                used_rules[r_key] = used_rules.get(r_key, 0) + 1

                    # 扫描 content 中出现的绝对路径字符串
                    for raw_word in re.findall(r'[a-zA-Z]:[\\/][^\s"\':<>]+', content):
                        norm_word = normalize_path(raw_word)
                        real_word = get_real_path(raw_word)
                        asset_type, key = match_file_to_asset(norm_word, real_word, skills, rules)
                        if asset_type == 'skill':
                            used_skills[key] = used_skills.get(key, 0) + 1
                        elif asset_type == 'rule':
                            used_rules[key] = used_rules.get(key, 0) + 1

    except Exception as e:
        pass
        
    return used_skills, used_rules


def generate_report(skills, rules, used_skills, used_rules):
    """根据扫描到的和被使用的资产，构建 Markdown 格式的报告字符串"""
    lines = []
    lines.append("\n" + "="*60)
    lines.append("📊 AI Agent Session Asset Report")
    lines.append("="*60)
    
    if not used_skills and not used_rules:
        lines.append("\n*本次会话中未检测到被阅读或激活的自定义 AI 资产 (Skills / Rules)。*")
    else:
        if used_skills:
            lines.append("\n### 🛠️ 调用的技能 (Skills Triggered)")
            for key, count in sorted(used_skills.items(), key=lambda x: x[1], reverse=True):
                s_info = skills.get(key, {})
                s_name = s_info.get('name', key)
                s_path = s_info.get('skill_md', s_info.get('dir', ''))
                file_url = f"file:///{s_path}"
                lines.append(f"- **[{s_name}]({file_url})**: 命中 {count} 次 (已提取使用)")
                
        if used_rules:
            lines.append("\n### 📜 激活的规则 (Rules Applied)")
            for key, count in sorted(used_rules.items(), key=lambda x: x[1], reverse=True):
                r_info = rules.get(key, {})
                r_name = r_info.get('name', key)
                r_path = r_info.get('path', '')
                file_url = f"file:///{r_path}"
                lines.append(f"- **[{r_name}]({file_url})**: 命中 {count} 次")

    # 发现未调用的资产 (Unused / Idle Assets)
    unused_skills = [s['name'] for k, s in skills.items() if k not in used_skills]
    unused_rules = [r['name'] for k, r in rules.items() if k not in used_rules]

    if unused_skills or unused_rules:
        lines.append("\n### 💤 未调用的空闲资产 (Unused / Idle Assets)")
        if unused_skills:
            lines.append(f"- **未调用的 Skills ({len(unused_skills)})**: " + ", ".join(f"`{s}`" for s in sorted(unused_skills)))
        if unused_rules:
            lines.append(f"- **未调用的 Rules ({len(unused_rules)})**: " + ", ".join(f"`{r}`" for r in sorted(unused_rules)))

    lines.append("\n" + "-"*60)
    lines.append(f"*报告时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 由 ai-agent-asset-reporter 自动审计生成*")
    lines.append("="*60 + "\n")
    return "\n".join(lines)


def find_latest_agent_transcript():
    """尝试在全局 Agent 脑区目录下寻找最近修改的会话日志"""
    candidates = [
        os.path.expanduser('~/.gemini/antigravity-ide/brain'),
        os.path.expanduser('~/.gemini/brain'),
        os.path.expanduser('~/.antigravity/brain'),
        os.path.expanduser('~/.claude/logs')
    ]
    
    latest_transcript = None
    latest_mtime = 0
    
    for brain_dir in candidates:
        if not os.path.exists(brain_dir):
            continue
        try:
            for root, dirs, files in os.walk(brain_dir):
                if 'transcript.jsonl' in files:
                    log_file = os.path.join(root, 'transcript.jsonl')
                    mtime = os.path.getmtime(log_file)
                    if mtime > latest_mtime:
                        latest_mtime = mtime
                        latest_transcript = log_file
        except Exception:
            pass
            
    return latest_transcript


def main():
    payload = load_payload()
    
    workspace_paths = payload.get('workspacePaths') or []
    transcript_path = payload.get('transcriptPath')
    
    # 容错：如果在参数里没收到 transcript 路径，自动在 workspace 中搜搜
    if not transcript_path and workspace_paths:
        for ws in workspace_paths:
            possible_paths = [
                os.path.join(ws, '.system_generated', 'logs', 'transcript.jsonl'),
                os.path.join(ws, '.claude', 'logs', 'transcript.jsonl'),
                os.path.join(ws, '.agents', 'logs', 'transcript.jsonl')
            ]
            for p in possible_paths:
                if os.path.exists(p):
                    transcript_path = p
                    break
            if transcript_path:
                break
                
    # 进一步容错：如果还是没找到，去全局脑区寻找最近一次的会话日志
    if not transcript_path:
        transcript_path = find_latest_agent_transcript()
            
    # 1. 扫描所有已定义 Skills 和 Rules
    skills, rules = scan_assets(workspace_paths)
    
    # 2. 分析交互日志计算资产命中情况
    used_skills, used_rules = analyze_transcript(transcript_path, skills, rules)
    
    # 3. 生成报告内容
    report_content = generate_report(skills, rules, used_skills, used_rules)
    
    # 4. 输出 Markdown 报告到控制台
    print(report_content)
    
    # 5. 自动保存报告到主工作区本地文件
    if workspace_paths:
        main_workspace = workspace_paths[0]
        if os.path.exists(main_workspace) and os.path.isdir(main_workspace):
            report_dir = os.path.join(main_workspace, '.agents', 'reports')
            try:
                os.makedirs(report_dir, exist_ok=True)
                report_file = os.path.join(report_dir, 'session_asset_report.md')
                with open(report_file, 'w', encoding='utf-8') as f:
                    f.write(report_content)
                print(f"ℹ️ 报告已成功保存到本地文件: file:///{report_file.replace('\\', '/')}\n")
            except Exception as e:
                print(f"⚠️ 无法保存报告到本地文件: {e}\n")


if __name__ == '__main__':
    main()
