"""
Document Creation Skills
==========================
LaTeX documents and skill files management.
"""

import os
import subprocess
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime
from genesis_protocol.skills import Skill, SkillCategory

# Skill definitions
SKILLS = [
    Skill(
        name="latex_document",
        category=SkillCategory.DOCUMENT,
        description="Create LaTeX documents and compile to PDF",
        tools=["pdflatex", "file_write"],
        version="1.0.0"
    ),
    Skill(
        name="skill_file_management",
        category=SkillCategory.DOCUMENT,
        description="Create and manage skill files for agent customization",
        tools=["file_write", "file_read"],
        version="1.0.0"
    ),
    Skill(
        name="markdown_to_pdf",
        category=SkillCategory.DOCUMENT,
        description="Convert markdown documents to PDF",
        tools=["pandoc", "file_write"],
        version="1.0.0"
    ),
]


class LaTeXDocument:
    """Create and compile LaTeX documents."""
    
    def __init__(self, output_dir: str = "."):
        self.output_dir = Path(output_dir)
        self.latex_available = self._check_latex()
    
    def _check_latex(self) -> bool:
        """Check if LaTeX is available."""
        try:
            subprocess.run(["pdflatex", "--version"], capture_output=True, timeout=10)
            return True
        except:
            return False
    
    def create_document(
        self,
        title: str,
        author: str = "",
        content: str = "",
        template: str = "article"
    ) -> Dict[str, Any]:
        """Create a LaTeX document."""
        try:
            content = content or self._get_default_content()
            
            latex_content = f"""\\documentclass[12pt]{{{template}}}

\\usepackage[utf8]{{inputenc}}
\\usepackage{{graphicx}}
\\usepackage{{hyperref}}
\\usepackage{{geometry}}
\\geometry{{a4paper, margin=1in}}

\\title{{{title}}}
\\author{{{author}}}
\\date{{{datetime.now().strftime('%B %d, %Y')}}}

\\begin{{document}}

\\maketitle

{content}

\\end{{document}}
"""
            
            return {
                "success": True,
                "content": latex_content,
                "template": template
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _get_default_content(self) -> str:
        """Get default document content."""
        return """\\section*{Introduction}
This is a generated document. Add your content here.

\\section*{Main Content}
Your main content goes here.

\\section*{Conclusion}
Add your conclusion here.
"""
    
    def save_document(self, filename: str, content: str) -> Dict[str, Any]:
        """Save LaTeX document to file."""
        try:
            output_file = self.output_dir / f"{filename}.tex"
            output_file.write_text(content)
            
            return {
                "success": True,
                "path": str(output_file),
                "filename": filename
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def compile(self, filename: str, clean: bool = True) -> Dict[str, Any]:
        """Compile LaTeX document to PDF."""
        if not self.latex_available:
            return {"success": False, "error": "LaTeX not installed"}
        
        try:
            input_file = self.output_dir / filename
            
            if not input_file.exists():
                return {"success": False, "error": f"File not found: {input_file}"}
            
            # Run pdflatex twice for proper compilation
            for _ in range(2):
                result = subprocess.run(
                    ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", str(input_file)],
                    capture_output=True,
                    text=True,
                    cwd=self.output_dir,
                    timeout=120
                )
                
                if result.returncode != 0:
                    return {
                        "success": False,
                        "error": result.stderr,
                        "log": result.stdout
                    }
            
            # Check if PDF was created
            pdf_file = input_file.with_suffix('.pdf')
            
            if pdf_file.exists():
                result = {
                    "success": True,
                    "pdf_path": str(pdf_file),
                    "pdf_size": pdf_file.stat().st_size
                }
                
                # Clean up auxiliary files
                if clean:
                    self._cleanup_aux_files(input_file.stem)
                
                return result
            else:
                return {"success": False, "error": "PDF not generated"}
                
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Compilation timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _cleanup_aux_files(self, base_name: str) -> None:
        """Clean up auxiliary LaTeX files."""
        extensions = ['.aux', '.log', '.out', '.toc', '.bbl', '.blg']
        for ext in extensions:
            file_path = self.output_dir / f"{base_name}{ext}"
            if file_path.exists():
                file_path.unlink()


class SkillFileManager:
    """Manage agent skill files."""
    
    def __init__(self, skills_dir: str = ".agents/skills"):
        self.skills_dir = Path(skills_dir)
    
    def create_skill(
        self,
        name: str,
        description: str,
        triggers: List[str],
        actions: List[str],
        prompts: Dict[str, str]
    ) -> Dict[str, Any]:
        """Create a skill file."""
        try:
            skill_content = f"""# Skill: {name}

## Description
{description}

## Triggers
{self._format_list(triggers)}

## Actions
{self._format_list(actions)}

## Prompts

### System Prompt
```
{prompts.get('system', 'You are a helpful AI assistant.')}
```

### User Prompt Template
```
{prompts.get('user', 'Please help me with my request.')}
```

---

*Generated on {datetime.now().isoformat()}*
"""
            
            skill_file = self.skills_dir / f"{name.lower().replace(' ', '_')}.md"
            skill_file.parent.mkdir(parents=True, exist_ok=True)
            skill_file.write_text(skill_content)
            
            return {
                "success": True,
                "path": str(skill_file),
                "name": name
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _format_list(self, items: List[str]) -> str:
        """Format a list as markdown."""
        return "\n".join([f"- {item}" for item in items])
    
    def list_skills(self) -> List[Dict[str, Any]]:
        """List all available skills."""
        if not self.skills_dir.exists():
            return []
        
        skills = []
        for file in self.skills_dir.glob("*.md"):
            content = file.read_text()
            
            # Parse skill info from file
            lines = content.split("\n")
            name = file.stem.replace("_", " ").title()
            
            for line in lines:
                if line.startswith("# Skill:"):
                    name = line.replace("# Skill:", "").strip()
                    break
            
            skills.append({
                "name": name,
                "file": str(file.relative_to(self.skills_dir)),
                "path": str(file)
            })
        
        return skills
    
    def create_agents_md(
        self,
        skills: List[str],
        instructions: str = ""
    ) -> Dict[str, Any]:
        """Create or update AGENTS.md file."""
        try:
            content = f"""# Agent Configuration

## Active Skills
{self._format_list(skills)}

## Instructions
{instructions or 'You are a helpful AI assistant with access to various skills.'}

## Memory
- Use the skill files in `.agents/skills/` for reference
- Update this file when skills are added or modified

---

*Last updated: {datetime.now().isoformat()}*
"""
            
            agents_file = self.skills_dir.parent / "AGENTS.md"
            agents_file.parent.mkdir(parents=True, exist_ok=True)
            agents_file.write_text(content)
            
            return {
                "success": True,
                "path": str(agents_file)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class MarkdownToPDF:
    """Convert markdown to PDF using pandoc."""
    
    def __init__(self):
        self.pandoc_available = self._check_pandoc()
    
    def _check_pandoc(self) -> bool:
        """Check if pandoc is available."""
        try:
            subprocess.run(["pandoc", "--version"], capture_output=True, timeout=10)
            return True
        except:
            return False
    
    def convert(
        self,
        input_file: str,
        output_file: str = None,
        options: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Convert markdown to PDF."""
        if not self.pandoc_available:
            return {"success": False, "error": "pandoc not installed"}
        
        try:
            options = options or {}
            input_path = Path(input_file)
            
            if not input_path.exists():
                return {"success": False, "error": f"File not found: {input_file}"}
            
            if output_file is None:
                output_file = str(input_path.with_suffix('.pdf'))
            
            args = [
                str(input_path),
                "-o", output_file,
                "--pdf-engine=pdflatex"
            ]
            
            # Add metadata options
            if "title" in options:
                args.extend(["--metadata", f"title={options['title']}"])
            if "author" in options:
                args.extend(["--metadata", f"author={options['author']}"])
            
            # Add template options
            if options.get("standalone", True):
                args.append("--standalone")
            
            result = subprocess.run(
                ["pandoc"] + args,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0 and Path(output_file).exists():
                return {
                    "success": True,
                    "output": output_file,
                    "size": Path(output_file).stat().st_size
                }
            else:
                return {
                    "success": False,
                    "error": result.stderr or "Conversion failed"
                }
                
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Conversion timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# Export skill executors
async def execute_latex_create(title: str, author: str = "", **kwargs) -> Dict[str, Any]:
    """Execute LaTeX document creation."""
    latex = LaTeXDocument()
    doc_info = latex.create_document(title, author, **kwargs)
    
    if doc_info.get("success"):
        filename = title.lower().replace(" ", "_")
        latex.save_document(filename, doc_info["content"])
        doc_info["filename"] = f"{filename}.tex"
    
    return doc_info


async def execute_skill_create(name: str, description: str, **kwargs) -> Dict[str, Any]:
    """Execute skill file creation."""
    manager = SkillFileManager()
    return manager.create_skill(name, description, **kwargs)


async def execute_markdown_to_pdf(input_file: str, output_file: str = None) -> Dict[str, Any]:
    """Execute markdown to PDF conversion."""
    converter = MarkdownToPDF()
    return converter.convert(input_file, output_file)


# Export skill executors
SKILL_EXECUTORS = {
    "latex_document": execute_latex_create,
    "skill_file_management": execute_skill_create,
    "markdown_to_pdf": execute_markdown_to_pdf,
}