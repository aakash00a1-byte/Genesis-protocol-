# 🎯 Genesis Protocol Skills System

## Overview

Genesis Protocol ab **30 autonomous skills** ke saath kaam kar sakta hai! Ye skills system aapke AI agent ko OpenHands jaise powerful capabilities deta hai.

---

## 📊 Skills Summary

| Category | Skills Count | Description |
|----------|-------------|-------------|
| **Coding** | 5 | Code writing, editing, debugging, review, testing |
| **File Management** | 5 | Files, project explore, git operations |
| **Web Browser** | 4 | Navigation, forms, content extraction, search |
| **Automation** | 4 | Cron jobs, GitHub Actions, API integration, webhooks |
| **DevOps** | 4 | Docker, Kubernetes, Cloud services, IaC |
| **Specialized** | 5 | Linear, Notion, Slack, GitHub PR, Data analysis |
| **Document** | 3 | LaTeX, Skill files, Markdown to PDF |
| **TOTAL** | **30** | **All enabled and ready!** |

---

## 🛠️ Skills Details

### 1️⃣ Coding & Development (5 skills)

| Skill | Description | Tools |
|-------|-------------|-------|
| `code_write` | Write code in Python, JavaScript, Go, Rust, etc. | subprocess, file_write |
| `code_edit` | Edit existing code with precision | file_read, file_write, subprocess |
| `debugging` | Debug code and fix errors | subprocess, grep |
| `code_review` | Review code for quality and best practices | file_read, subprocess |
| `testing` | Write and run tests (pytest, etc.) | subprocess, file_write |

**Capabilities:**
- Multi-language code generation
- Python code analysis (AST parsing)
- Linting (ruff, pylint)
- Test execution
- Refactoring suggestions

---

### 2️⃣ File & Project Management (5 skills)

| Skill | Description | Tools |
|-------|-------------|-------|
| `file_create` | Create new files with content | file_write |
| `file_edit` | Edit existing files | file_read, file_write |
| `file_delete` | Delete files and directories | subprocess |
| `project_explore` | Explore project structure | subprocess |
| `git_operations` | Git commit, push, pull, merge, branches | subprocess, git |

**Capabilities:**
- Safe file operations (workspace validation)
- Project structure tree generation
- File pattern matching
- Git history and diff viewing
- Branch management

---

### 3️⃣ Web & Browser (4 skills)

| Skill | Description | Tools |
|-------|-------------|-------|
| `web_navigate` | Navigate websites, click, type | browser, http |
| `web_form_fill` | Fill forms and submit data | browser |
| `web_content_extract` | Extract text, links, images, tables | http, browser |
| `web_search` | Search web using Tavily API | tavily, http |

**Capabilities:**
- HTML parsing and content extraction
- Form handling
- Web scraping
- Tavily API integration for real search
- Metadata extraction

---

### 4️⃣ Automation (4 skills)

| Skill | Description | Tools |
|-------|-------------|-------|
| `cron_jobs` | Create and manage cron jobs | subprocess, crontab |
| `github_actions` | Create CI/CD workflows | file_write, git |
| `api_integration` | Integrate with external APIs | http, json |
| `webhook_handler` | Handle webhooks and events | http, json |

**Capabilities:**
- Cron job creation/deletion
- GitHub Actions workflow generation
- CI workflow templates
- Docker build/push workflows
- API call execution

---

### 5️⃣ DevOps (4 skills)

| Skill | Description | Tools |
|-------|-------------|-------|
| `docker_management` | Docker containers, images, compose | docker, subprocess |
| `kubernetes_management` | K8s clusters and deployments | kubectl, docker |
| `cloud_services` | AWS, GCP, Azure integration | aws, gcloud, az |
| `infrastructure_as_code` | Create IaC configurations | file_write, terraform |

**Capabilities:**
- Docker container lifecycle
- docker-compose management
- Kubernetes pod/service management
- K8s manifest generation
- Cloud CLI integration
- Dockerfile/docker-compose generation

---

### 6️⃣ Specialized Tools (5 skills)

| Skill | Description | Tools |
|-------|-------------|-------|
| `linear_integration` | Manage Linear issues | graphql, http |
| `notion_integration` | Notion pages and databases | http, json |
| `slack_integration` | Slack messages and channels | http, api |
| `github_pr_management` | GitHub PRs creation and review | gh, git |
| `data_analysis` | Analyze data, generate reports | python, pandas |

**Capabilities:**
- Linear GraphQL API (issues, comments, state changes)
- Notion API (pages, blocks, search)
- Slack Web API (messages, channels)
- GitHub CLI (PR creation, review, merge)
- CSV data analysis with pandas
- Report generation (Markdown, JSON)

---

### 7️⃣ Document Creation (3 skills)

| Skill | Description | Tools |
|-------|-------------|-------|
| `latex_document` | Create LaTeX and compile to PDF | pdflatex, file_write |
| `skill_file_management` | Create agent skill files | file_write, file_read |
| `markdown_to_pdf` | Convert Markdown to PDF | pandoc, file_write |

**Capabilities:**
- LaTeX document generation
- PDF compilation
- Agent skill file creation (AGENTS.md)
- Markdown to PDF conversion
- Skill file templates

---

## 🔧 How to Use Skills

### In Python Code:

```python
from genesis_protocol.skills import get_skill_registry

# Get skill registry
registry = get_skill_registry()

# Get enabled skills
skills = registry.get_enabled_skills()

# Get skills by category
coding_skills = registry.get_skills_by_category(SkillCategory.CODING)

# Get available tools
tools = registry.get_available_tools()
print(f"Available tools: {tools}")
```

### Execute a Skill:

```python
from genesis_protocol.skills.coding import execute_code_write
from genesis_protocol.skills.file_management import execute_git_operation

# Write code
result = await execute_code_write(
    task="Create a hello world function",
    language="python",
    output_path="hello.py"
)

# Git operation
result = await execute_git_operation(
    operation="status"
)
```

---

## 🎯 Example: Using Skills in Telegram Bot

```python
@bot.message_handler(commands=['code'])
async def handle_code_request(message):
    # Get skill registry
    registry = get_skill_registry()
    
    # Use coding skill
    from genesis_protocol.skills.coding import CodeGenerator
    generator = CodeGenerator()
    
    code = generator.generate_function(
        language="python",
        function_name="hello_world",
        params=[],
        body='    print("Hello, World!")'
    )
    
    await bot.reply_to(message, f"```python\n{code}\n```")
```

---

## 📈 Available Tools (23 total)

```
subprocess, file_write, file_read, file_delete, git, grep
browser, http, tavily, json, crontab, docker, kubectl
aws, gcloud, az, terraform, graphql, api, python, pandas
pdflatex, pandoc
```

---

## 🚀 Future Enhancements

- [ ] Add more AI provider integrations
- [ ] Browser automation (Selenium/Playwright)
- [ ] Database operations (SQL, MongoDB)
- [ ] More DevOps integrations (Terraform, Ansible)
- [ ] Advanced data analysis (matplotlib, numpy)
- [ ] Image processing capabilities
- [ ] Multi-agent coordination

---

## 📝 Notes

- All skills are **enabled by default**
- Skills can be **enabled/disabled** at runtime
- Each skill has **dependencies** that are automatically tracked
- Skills use **sandboxed file operations** for security
- API keys are loaded from **environment variables**

---

*Generated on: 2026-06-16*
*Genesis Protocol v2.0 - Skills System*