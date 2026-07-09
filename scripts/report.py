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


def load_payload():
    """从 stdin 或 命令行参数加载平台传入的元数据 payload"""
    # 尝试从 stdin 读取 JSON
    try:
        if not sys.stdin.isatty():
            data = sys.stdin.read().strip()
            if data:
                return json.loads(data)
    except Exception:
        pass
    
    # 如果 stdin 为空，尝试从命令行参数解析 --transcript 和 --workspace
    payload = {}
    args = sys.argv[1:]
    for i in range(len(args)):
        if args[i] == '--transcript' and i + 1 < len(args):
            payload['transcriptPath'] = args[i+1]
        elif args[i] == '--workspace' and i + 1 < len(args):
            payload['workspacePaths'] = [args[i+1]]
            
    # 兜底：如果都没有，从环境变量或当前目录猜测
    if 'workspacePaths' not in payload:
        workspace = os.environ.get('WORKSPACE_ROOT') or os.getcwd()
        payload['workspacePaths'] = [workspace]
        
    return payload

def scan_assets(workspace_paths):
    """扫描所有工作空间目录下的技能 (Skills) 和规则 (Rules)"""
    skills = {} # name -> { "path": str, "type": "skill" }
    rules = {}  # name -> { "path": str, "type": "rule" }
    
    # 常用 skills 目录名称
    skills_dir_names = ['.agents/skills', '_agents/skills', 'skills']
    # 常用 rules 目录名称
    rules_dir_names = ['.agents/rules', '_agents/rules', 'rules']
    
    # 同时扫描全局配置目录（如果有）
    global_dirs = [
        os.path.expanduser('~/.gemini/config'),
        os.path.expanduser('~/.claude'),
        os.path.expanduser('~/.devin')
    ]
    
    paths_to_scan = list(workspace_paths)
    for g_dir in global_dirs:
        if os.path.exists(g_dir):
            paths_to_scan.append(g_dir)
        
    for base_path in paths_to_scan:
        if not os.path.exists(base_path):
            continue
            
        # 1. 扫描根下的 Skills
        for s_dir in skills_dir_names:
            full_skills_dir = os.path.join(base_path, s_dir)
            if os.path.isdir(full_skills_dir):
                for item in os.listdir(full_skills_dir):
                    item_path = os.path.join(full_skills_dir, item)
                    if os.path.isdir(item_path):
                        skill_md = os.path.join(item_path, 'SKILL.md')
                        if os.path.exists(skill_md):
                            skills[item.lower()] = {
                                "name": item,
                                "path": os.path.abspath(skill_md),
                                "dir": os.path.abspath(item_path)
                            }
                            
        # 2. 扫描根下的 Rules
        for r_dir in rules_dir_names:
            full_rules_dir = os.path.join(base_path, r_dir)
            if os.path.isdir(full_rules_dir):
                for item in os.listdir(full_rules_dir):
                    if item.endswith('.md'):
                        name = item[:-3]
                        rules[name.lower()] = {
                            "name": name,
                            "path": os.path.abspath(os.path.join(full_rules_dir, item))
                        }
                        
        # 3. 扫描插件目录 (如 .agents/plugins/plugin-name/skills/ 或者是 plugins/plugin-name/rules/) 中的资产
        plugins_dir_names = ['.agents/plugins', '_agents/plugins', 'plugins']
        for p_dir in plugins_dir_names:
            full_plugins_dir = os.path.join(base_path, p_dir)
            if os.path.isdir(full_plugins_dir):
                for plugin_item in os.listdir(full_plugins_dir):
                    plugin_path = os.path.join(full_plugins_dir, plugin_item)
                    if os.path.isdir(plugin_path):
                        # 扫描该插件内的 Skills
                        for s_dir in ['skills']:
                            p_skills_dir = os.path.join(plugin_path, s_dir)
                            if os.path.isdir(p_skills_dir):
                                for item in os.listdir(p_skills_dir):
                                    item_path = os.path.join(p_skills_dir, item)
                                    if os.path.isdir(item_path):
                                        skill_md = os.path.join(item_path, 'SKILL.md')
                                        if os.path.exists(skill_md):
                                            skills[item.lower()] = {
                                                "name": item,
                                                "path": os.path.abspath(skill_md),
                                                "dir": os.path.abspath(item_path)
                                            }
                        # 扫描该插件内的 Rules
                        for r_dir in ['rules']:
                            p_rules_dir = os.path.join(plugin_path, r_dir)
                            if os.path.isdir(p_rules_dir):
                                for item in os.listdir(p_rules_dir):
                                    if item.endswith('.md'):
                                        name = item[:-3]
                                        rules[name.lower()] = {
                                            "name": name,
                                            "path": os.path.abspath(os.path.join(p_rules_dir, item))
                                        }
        
        # 4. 扫描根目录的 AGENTS.md 或类似规则文件
        for filename in ['AGENTS.md', 'RULES.md']:
            file_path = os.path.join(base_path, filename)
            if os.path.isfile(file_path):
                rules[filename.lower()] = {
                    "name": filename,
                    "path": os.path.abspath(file_path)
                }
                
    return skills, rules

def normalize_path(p):
    """统一路径格式，用于路径匹配比对"""
    if not p:
        return ""
    return os.path.abspath(p).replace('\\', '/').lower()

def analyze_transcript(transcript_path, skills, rules):
    """解析 transcript.jsonl，查找被使用的 AI 资产"""
    used_skills = {} # path -> count
    used_rules = {}  # path -> count
    
    # 建立路径到资产的映射，便于 O(1) 路径检索
    skill_path_map = {normalize_path(s['path']): s for s in skills.values()}
    rule_path_map = {normalize_path(r['path']): r for r in rules.values()}
    
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
                    # 兼容不同平台读取文件的参数名
                    file_path = args.get('AbsolutePath') or args.get('path') or args.get('TargetFile')
                    if file_path:
                        if isinstance(file_path, str):
                            file_path = file_path.strip('"\'')
                            norm_file = normalize_path(file_path)
                            
                            # 命中技能
                            if norm_file in skill_path_map:
                                skill_info = skill_path_map[norm_file]
                                used_skills[skill_info['path']] = used_skills.get(skill_info['path'], 0) + 1
                            # 命中规则
                            elif norm_file in rule_path_map:
                                rule_info = rule_path_map[norm_file]
                                used_rules[rule_info['path']] = used_rules.get(rule_info['path'], 0) + 1
                                
                # 2. 检查 content 中的显式引用 (如 "read_file" 后的 content 输出内容，或者 prompt 中的规则标记)
                content = step.get('content') or ""
                if content:
                    # 扫描是否有包含规则标签的初始化内容，例如 <RULE[unittest.md]> 或 <RULE[user_global]>
                    # 提取 rule 标签
                    rule_matches = re.findall(r'<RULE\[([^\]]+)\]>', content)
                    for rule_tag in rule_matches:
                        tag_lower = rule_tag.lower()
                        if tag_lower in rules:
                            rule_info = rules[tag_lower]
                            used_rules[rule_info['path']] = used_rules.get(rule_info['path'], 0) + 1
                            
                    # 也检测在 view_file / read_file 的系统返回值中出现的路径
                    for word in re.findall(r'[a-zA-Z]:[\\/][^:\s"\']+', content):
                        norm_word = normalize_path(word)
                        if norm_word in skill_path_map:
                            skill_info = skill_path_map[norm_word]
                            used_skills[skill_info['path']] = used_skills.get(skill_info['path'], 0) + 1
                        elif norm_word in rule_path_map:
                            rule_info = rule_path_map[norm_word]
                            used_rules[rule_info['path']] = used_rules.get(rule_info['path'], 0) + 1
    except Exception:
        pass
        
    return used_skills, used_rules

def main():
    payload = load_payload()
    
    workspace_paths = payload.get('workspacePaths') or []
    transcript_path = payload.get('transcriptPath') or payload.get('transcript_path') or payload.get('logPath')
    
    # 容错：如果在参数里没收到 transcript 路径，但在 workspace_paths 里有，自动去搜
    if not transcript_path and workspace_paths:
        for ws in workspace_paths:
            possible_path = os.path.join(ws, '.system_generated', 'logs', 'transcript.jsonl')
            if os.path.exists(possible_path):
                transcript_path = possible_path
                break
            # 兼容 Claude Code 或 Devin 等其他命名习惯
            possible_path_alt = os.path.join(ws, '.claude', 'logs', 'transcript.jsonl')
            if os.path.exists(possible_path_alt):
                transcript_path = possible_path_alt
                break
            
    # 1. 扫描所有已定义 Skills 和 Rules
    skills, rules = scan_assets(workspace_paths)
    
    # 2. 分析交互日志计算资产命中情况
    used_skills, used_rules = analyze_transcript(transcript_path, skills, rules)
    
    # 3. 输出 Markdown 报告
    print("\n" + "="*60)
    print("📊 AI Agent Session Asset Report")
    print("="*60)
    
    if not used_skills and not used_rules:
        print("\n*本次会话中未检测到被阅读或激活的自定义 AI 资产 (Skills / Rules)。*")
    else:
        if used_skills:
            print("\n### 🛠️ 调用的技能 (Skills Triggered)")
            for path, count in sorted(used_skills.items(), key=lambda x: x[1], reverse=True):
                skill_name = os.path.basename(os.path.dirname(path))
                file_url = f"file:///{path.replace('\\', '/')}"
                print(f"- **[{skill_name}]({file_url})**: 命中 {count} 次 (已读取 `SKILL.md`) ")
                
        if used_rules:
            print("\n### 📜 激活的规则 (Rules Applied)")
            for path, count in sorted(used_rules.items(), key=lambda x: x[1], reverse=True):
                rule_name = os.path.basename(path)
                file_url = f"file:///{path.replace('\\', '/')}"
                print(f"- **[{rule_name}]({file_url})**: 命中 {count} 次 ")
                
    print("\n" + "-"*60)
    print(f"*报告时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 由 ai-agent-asset-reporter 自动审计生成*")
    print("="*60 + "\n")

if __name__ == '__main__':
    main()
