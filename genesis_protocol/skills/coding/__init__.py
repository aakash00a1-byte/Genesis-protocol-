"""
Coding & Development Skills
============================
Code writing, editing, debugging, and development capabilities.
"""

import subprocess
import re
import ast
from typing import Dict, List, Optional, Any
from pathlib import Path
from genesis_protocol.skills import Skill, SkillCategory

# Supported languages
SUPPORTED_LANGUAGES = [
    "python", "javascript", "typescript", "java", "c", "cpp", 
    "csharp", "go", "rust", "ruby", "php", "swift", "kotlin", "sql"
]

# Skill definitions
SKILLS = [
    # 1. Code Writing
    Skill(
        name="code_write",
        category=SkillCategory.CODING,
        description="Write code in multiple programming languages",
        tools=["subprocess", "file_write"],
        version="1.0.0"
    ),
    
    # 2. Code Editing
    Skill(
        name="code_edit",
        category=SkillCategory.CODING,
        description="Edit existing code with precision",
        tools=["file_read", "file_write", "subprocess"],
        version="1.0.0"
    ),
    
    # 3. Debugging
    Skill(
        name="debugging",
        category=SkillCategory.CODING,
        description="Debug code and fix errors",
        tools=["subprocess", "file_read", "grep"],
        version="1.0.0"
    ),
    
    # 4. Code Review
    Skill(
        name="code_review",
        category=SkillCategory.CODING,
        description="Review code for quality and best practices",
        tools=["file_read", "subprocess"],
        version="1.0.0"
    ),
    
    # 5. Testing
    Skill(
        name="testing",
        category=SkillCategory.CODING,
        description="Write and run tests",
        tools=["subprocess", "file_write"],
        version="1.0.0"
    ),
]


class CodeGenerator:
    """Generate code in various programming languages."""
    
    def __init__(self):
        self.language_patterns = {
            "python": {
                "extension": ".py",
                "comment": "#",
                "multiline_comment": '"""'
            },
            "javascript": {
                "extension": ".js",
                "comment": "//",
                "multiline_comment": "/*"
            },
            "typescript": {
                "extension": ".ts",
                "comment": "//",
                "multiline_comment": "/*"
            },
            "java": {
                "extension": ".java",
                "comment": "//",
                "multiline_comment": "/*"
            },
            "go": {
                "extension": ".go",
                "comment": "//",
                "multiline_comment": "/*"
            },
            "rust": {
                "extension": ".rs",
                "comment": "//",
                "multiline_comment": "/*"
            },
        }
    
    def detect_language(self, file_path: str) -> Optional[str]:
        """Detect programming language from file extension."""
        ext = Path(file_path).suffix.lower()
        for lang, patterns in self.language_patterns.items():
            if ext == patterns["extension"]:
                return lang
        return None
    
    def generate_function(self, language: str, function_name: str, params: List[str], body: str) -> str:
        """Generate a function in the specified language."""
        if language == "python":
            return self._generate_python_function(function_name, params, body)
        elif language == "javascript":
            return self._generate_js_function(function_name, params, body)
        elif language == "go":
            return self._generate_go_function(function_name, params, body)
        elif language == "rust":
            return self._generate_rust_function(function_name, params, body)
        else:
            return f"// Function in {language}: {function_name}"
    
    def _generate_python_function(self, name: str, params: List[str], body: str) -> str:
        params_str = ", ".join(params) if params else ""
        return f"""def {name}({params_str}):
    \"\"\"Generated function.\"\"\"
    {body}
"""
    
    def _generate_js_function(self, name: str, params: List[str], body: str) -> str:
        params_str = ", ".join(params) if params else ""
        return f"""function {name}({params_str}) {{
    // Generated function
    {body}
}}
"""
    
    def _generate_go_function(self, name: str, params: List[str], body: str) -> str:
        params_str = ", ".join(params) if params else ""
        return f"""func {name}({params_str}) {{
    // Generated function
    {body}
}}
"""
    
    def _generate_rust_function(self, name: str, params: List[str], body: str) -> str:
        params_str = ", ".join(params) if params else ""
        return f"""fn {name}({params_str}) {{
    // Generated function
    {body}
}}
"""


class CodeAnalyzer:
    """Analyze code for structure, errors, and patterns."""
    
    def analyze_python_file(self, file_path: str) -> Dict[str, Any]:
        """Analyze a Python file for structure and potential issues."""
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            
            tree = ast.parse(content)
            
            functions = []
            classes = []
            imports = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    functions.append({
                        "name": node.name,
                        "line": node.lineno,
                        "args": [a.arg for a in node.args.args],
                        "docstring": ast.get_docstring(node)
                    })
                elif isinstance(node, ast.ClassDef):
                    classes.append({
                        "name": node.name,
                        "line": node.lineno,
                        "methods": [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                    })
                elif isinstance(node, ast.Import):
                    imports.extend([a.name for a in node.names])
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module)
            
            return {
                "valid": True,
                "functions": functions,
                "classes": classes,
                "imports": imports,
                "line_count": len(content.splitlines())
            }
        except SyntaxError as e:
            return {"valid": False, "error": str(e)}
        except Exception as e:
            return {"valid": False, "error": str(e)}
    
    def find_code_issues(self, file_path: str) -> List[Dict[str, str]]:
        """Find common code issues."""
        issues = []
        
        # Check for TODO comments
        try:
            with open(file_path, 'r') as f:
                lines = f.readlines()
                for i, line in enumerate(lines, 1):
                    if "TODO" in line or "FIXME" in line or "XXX" in line:
                        issues.append({
                            "line": i,
                            "type": "todo",
                            "message": line.strip()
                        })
        except Exception:
            pass
        
        return issues


class Debugger:
    """Debug code and fix issues."""
    
    def run_tests(self, test_path: str = "tests/", verbose: bool = True) -> Dict[str, Any]:
        """Run test suite and return results."""
        try:
            cmd = ["python", "-m", "pytest", test_path]
            if verbose:
                cmd.append("-v")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "errors": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Test timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def lint_code(self, file_path: str, linter: str = "ruff") -> Dict[str, Any]:
        """Run linter on code."""
        try:
            result = subprocess.run(
                [linter, "check", file_path],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "errors": result.stderr
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class Refactorer:
    """Refactor and improve code quality."""
    
    def suggest_refactors(self, code: str, language: str) -> List[Dict[str, str]]:
        """Suggest code refactoring improvements."""
        suggestions = []
        
        if language == "python":
            # Check for common issues
            if "for i in range(len(" in code:
                suggestions.append({
                    "type": "pythonic",
                    "message": "Use enumerate() instead of range(len())"
                })
            
            if re.search(r'if.*== True', code):
                suggestions.append({
                    "type": "simplification",
                    "message": "Remove '== True' comparisons"
                })
            
            if re.search(r'if.*!= False', code):
                suggestions.append({
                    "type": "simplification",
                    "message": "Remove '!= False' comparisons"
                })
            
            # Check for long functions
            lines = code.split('\n')
            in_function = False
            function_lines = 0
            for line in lines:
                if line.strip().startswith('def '):
                    in_function = True
                    function_lines = 0
                elif in_function and line.strip() and not line.strip().startswith('#'):
                    function_lines += 1
                elif in_function and (line.strip().startswith('def ') or line.strip().startswith('class ')):
                    if function_lines > 50:
                        suggestions.append({
                            "type": "function_length",
                            "message": f"Function is {function_lines} lines - consider splitting"
                        })
                    in_function = False
            
            # Check for magic numbers
            magic_numbers = re.findall(r'\b\d{2,}\b', code)
            if magic_numbers:
                suggestions.append({
                    "type": "magic_numbers",
                    "message": f"Found magic numbers: {set(magic_numbers)} - consider using constants"
                })
        
        return suggestions


# Skill execution functions
async def execute_code_write(task: str, language: str, output_path: str) -> Dict[str, Any]:
    """Execute code writing task."""
    generator = CodeGenerator()
    
    # Parse task and generate code
    code = generator.generate_function(
        language=language,
        function_name="generated_function",
        params=[],
        body="    pass"
    )
    
    try:
        with open(output_path, 'w') as f:
            f.write(code)
        return {"success": True, "output": code}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def execute_code_review(file_path: str) -> Dict[str, Any]:
    """Execute code review task."""
    analyzer = CodeAnalyzer()
    refactorer = Refactorer()
    
    if file_path.endswith('.py'):
        analysis = analyzer.analyze_python_file(file_path)
        if analysis.get("valid"):
            with open(file_path, 'r') as f:
                code = f.read()
            suggestions = refactorer.suggest_refactors(code, "python")
            return {
                "success": True,
                "analysis": analysis,
                "suggestions": suggestions
            }
        return {"success": False, "analysis": analysis}
    
    return {"success": False, "error": "Unsupported file type"}


async def execute_debug(task: str, file_path: str) -> Dict[str, Any]:
    """Execute debugging task."""
    debugger = Debugger()
    
    results = {
        "lint": debugger.lint_code(file_path),
        "issues": debugger.run_tests()
    }
    
    return {"success": True, "results": results}


# Export skill execution functions
SKILL_EXECUTORS = {
    "code_write": execute_code_write,
    "code_edit": execute_code_write,
    "code_review": execute_code_review,
    "debugging": execute_debug,
    "testing": lambda: Debugger().run_tests(),
}