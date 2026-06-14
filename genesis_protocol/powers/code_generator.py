"""Genesis Protocol - AI Code Generator

Generates code in multiple languages using AI.
Supports: Python, JavaScript, TypeScript, Java, C++, Go, Rust, and more.
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from genesis_protocol.ai.provider_chain import get_provider_chain, AICallResult
from genesis_protocol.utils.logger import get_logger

logger = get_logger("powers.code_generator")


@dataclass
class CodeGenerationRequest:
    """Code generation request."""
    description: str
    language: str
    framework: Optional[str] = None
    requirements: Optional[List[str]] = None
    complexity: str = "medium"  # simple, medium, complex
    include_tests: bool = False
    include_docs: bool = False


@dataclass
class CodeGenerationResult:
    """Code generation result."""
    success: bool
    code: str
    language: str
    explanation: str
    files_created: List[str]
    warnings: List[str]
    error: Optional[str] = None


class CodeGenerator:
    """
    AI-powered code generator with multi-language support.
    
    Capabilities:
    - Generate code from natural language description
    - Support for 15+ programming languages
    - Framework-specific code generation
    - Auto-create tests and documentation
    - Code review and optimization suggestions
    """

    SUPPORTED_LANGUAGES = {
        "python": ["py", "python"],
        "javascript": ["js", "javascript"],
        "typescript": ["ts", "typescript"],
        "java": ["java"],
        "cpp": ["cpp", "c++", "cxx"],
        "c": ["c", "c/h"],
        "go": ["go", "golang"],
        "rust": ["rs", "rust"],
        "ruby": ["rb", "ruby"],
        "php": ["php"],
        "swift": ["swift"],
        "kotlin": ["kt", "kotlin"],
        "html": ["html"],
        "css": ["css", "scss", "sass"],
        "sql": ["sql"],
        "bash": ["sh", "bash", "shell"],
        "dockerfile": ["dockerfile", "docker"],
        "yaml": ["yaml", "yml"],
        "json": ["json"],
    }

    FRAMEWORK_TEMPLATES = {
        "python": {
            "flask": "Flask REST API with blueprints",
            "fastapi": "FastAPI with Pydantic models",
            "django": "Django with models and views",
            "discord": "Discord bot with commands",
            "telegram": "Telegram bot with handlers",
            "bot": "General chatbot framework",
        },
        "javascript": {
            "react": "React functional components",
            "next": "Next.js pages and API routes",
            "express": "Express.js REST API",
            "node": "Node.js application",
            "discord.js": "Discord.js bot",
        },
        "typescript": {
            "react": "React with TypeScript",
            "next": "Next.js TypeScript",
            "nest": "NestJS backend",
        }
    }

    def __init__(self):
        """Initialize code generator."""
        self.provider_chain = get_provider_chain()
        logger.info("Code Generator initialized")

    def parse_request(self, query: str) -> CodeGenerationRequest:
        """Parse natural language into code generation request."""
        query_lower = query.lower()
        
        # Detect language
        detected_language = "python"  # default
        for lang, aliases in self.SUPPORTED_LANGUAGES.items():
            if any(alias in query_lower for alias in aliases):
                detected_language = lang
                break
        
        # Detect framework
        detected_framework = None
        for lang, templates in self.FRAMEWORK_TEMPLATES.items():
            for framework, _ in templates.items():
                if framework in query_lower:
                    detected_framework = framework
                    if lang == detected_language:
                        detected_language = lang
                    break
        
        # Detect complexity
        complexity = "medium"
        if any(w in query_lower for w in ["simple", "basic", "easy", "small"]):
            complexity = "simple"
        elif any(w in query_lower for w in ["complex", "advanced", "enterprise", "full"]):
            complexity = "complex"
        
        # Detect options
        include_tests = "test" in query_lower or "testing" in query_lower
        include_docs = "doc" in query_lower or "document" in query_lower
        
        return CodeGenerationRequest(
            description=query,
            language=detected_language,
            framework=detected_framework,
            complexity=complexity,
            include_tests=include_tests,
            include_docs=include_docs
        )

    async def generate(self, request: CodeGenerationRequest) -> CodeGenerationResult:
        """Generate code from request."""
        try:
            prompt = self._build_prompt(request)
            
            messages = [
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": prompt}
            ]
            
            result = await self.provider_chain.call(
                messages=messages,
                user_input=request.description
            )
            
            if result.success:
                code, explanation = self._parse_response(result.response.content, request.language)
                return CodeGenerationResult(
                    success=True,
                    code=code,
                    language=request.language,
                    explanation=explanation,
                    files_created=self._suggest_filename(request),
                    warnings=self._validate_code(code, request.language)
                )
            else:
                return CodeGenerationResult(
                    success=False,
                    code="",
                    language=request.language,
                    explanation="",
                    files_created=[],
                    warnings=[],
                    error=result.error
                )
                
        except Exception as e:
            logger.error(f"Code generation failed: {e}")
            return CodeGenerationResult(
                success=False,
                code="",
                language=request.language,
                explanation="",
                files_created=[],
                warnings=[],
                error=str(e)
            )

    def _build_prompt(self, request: CodeGenerationRequest) -> str:
        """Build prompt for code generation."""
        complexity_prompt = {
            "simple": "Create a simple, clean implementation with basic functionality.",
            "medium": "Create a well-structured implementation with error handling and good practices.",
            "complex": "Create a production-ready implementation with full error handling, logging, and best practices."
        }
        
        framework_note = ""
        if request.framework:
            framework_note = f"Use {request.framework} framework. "
        
        tests_note = "Include unit tests using pytest. " if request.include_tests else ""
        docs_note = "Add docstrings and comments. " if request.include_docs else ""
        
        return f"""Generate {request.language} code for:

{request.description}

Requirements:
- {complexity_prompt[request.complexity]}
- {framework_note}{tests_note}{docs_note}
- Follow {request.language} best practices and idioms

Return the code in this format:
```code
# Your generated code here
```
```explanation
Brief explanation of what the code does
```"""

    def _get_system_prompt(self) -> str:
        """Get system prompt for code generation."""
        return """You are Genesis, an expert code generator.

RULES:
- Generate COMPLETE, RUNNABLE code
- Include necessary imports
- Add error handling
- Follow language best practices
- Use modern syntax (Python 3.10+, ES6+, etc.)
- Add type hints where applicable
- Hinglish comments allowed for clarity

Output format:
```code
[generated code]
```
```explanation
[brief explanation]
```"""

    def _parse_response(self, response: str, language: str) -> Tuple[str, str]:
        """Parse AI response into code and explanation."""
        code = ""
        explanation = ""
        
        # Extract code block
        code_match = re.search(r'```code?\n(.*?)```', response, re.DOTALL)
        if code_match:
            code = code_match.group(1).strip()
        
        # Extract explanation
        exp_match = re.search(r'```explanation\n(.*?)```', response, re.DOTALL)
        if exp_match:
            explanation = exp_match.group(1).strip()
        else:
            # Try to get text after code as explanation
            if code_match:
                remaining = response[code_match.end():].strip()
                if remaining:
                    explanation = remaining.split('\n')[0][:200]
        
        return code, explanation

    def _suggest_filename(self, request: CodeGenerationRequest) -> List[str]:
        """Suggest filename for generated code."""
        extension_map = {
            "python": "py",
            "javascript": "js",
            "typescript": "ts",
            "java": "java",
            "cpp": "cpp",
            "go": "go",
            "rust": "rs",
            "ruby": "rb",
            "php": "php",
            "swift": "swift",
            "kotlin": "kt",
            "html": "html",
            "css": "css",
            "sql": "sql",
            "bash": "sh",
        }
        
        ext = extension_map.get(request.language, "txt")
        filename = f"generated_code.{ext}"
        
        files = [filename]
        if request.include_tests:
            test_filename = f"test_generated_code.{ext}"
            files.append(test_filename)
        
        return files

    def _validate_code(self, code: str, language: str) -> List[str]:
        """Validate generated code and return warnings."""
        warnings = []
        
        if not code:
            warnings.append("No code generated")
            return warnings
        
        # Basic validation
        if language == "python":
            if "import " not in code and "from " not in code:
                warnings.append("No imports found - code may be incomplete")
            if "def " not in code and "class " not in code:
                warnings.append("No functions or classes found")
            if code.count(":") < code.count("\n") / 3:
                warnings.append("Possible syntax issue - check indentation")
        
        elif language == "javascript":
            if "function" not in code and "const" not in code and "let" not in code:
                warnings.append("No functions or variables found")
        
        return warnings

    async def generate_from_natural_language(
        self, 
        description: str,
        language: str = "python"
    ) -> CodeGenerationResult:
        """Generate code directly from natural language."""
        request = CodeGenerationRequest(
            description=description,
            language=language
        )
        return await self.generate(request)


# Singleton
_code_generator: Optional[CodeGenerator] = None


def get_code_generator() -> CodeGenerator:
    """Get or create CodeGenerator singleton."""
    global _code_generator
    if _code_generator is None:
        _code_generator = CodeGenerator()
    return _code_generator