"""Genesis Protocol - Error Fixer

AI-powered automatic error fixing and debugging.
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from genesis_protocol.ai.provider_chain import get_provider_chain, AICallResult
from genesis_protocol.utils.logger import get_logger

logger = get_logger("powers.error_fixer")


@dataclass
class ErrorFix:
    """Error and its fix."""
    original_error: str
    fixed_code: str
    explanation: str
    confidence: float  # 0.0 - 1.0
    changes_made: List[str]


@dataclass
class ErrorFixResult:
    """Result of error fixing attempt."""
    success: bool
    original_error: str
    fixes: List[ErrorFix]
    fixed_code: str
    summary: str
    error: Optional[str] = None


class ErrorFixer:
    """
    AI-powered error fixing system.
    
    Capabilities:
    - Parse error messages and tracebacks
    - Identify root cause
    - Generate fix suggestions
    - Apply automatic fixes
    - Explain what went wrong
    """

    # Common Python errors and their patterns
    COMMON_ERRORS = {
        "SyntaxError": {
            "IndentationError": "Check indentation - use consistent spaces (4 recommended)",
            "unexpected EOF": "Missing closing bracket, parenthesis, or quote",
            "invalid syntax": "Check for typos or missing operators",
        },
        "AttributeError": {
            "has no attribute": "Object doesn't have this attribute - check spelling or import",
            "'NoneType'": "Object is None - add null check before access",
        },
        "TypeError": {
            "unsupported operand": "Type mismatch - check data types",
            "'str' and 'int'": "Convert to same type before operation",
            "object is not iterable": "Need to iterate over collection",
        },
        "ImportError": {
            "No module named": "Module not installed or import path incorrect",
            "cannot import name": "Name not in module - check exports",
        },
        "NameError": {
            "not defined": "Variable not defined - check spelling or initialization",
        },
        "FileNotFoundError": {
            "No such file": "Check file path - use absolute path or create file",
        },
        "KeyError": {
            "KeyError": "Key not in dictionary - use .get() or check keys",
        },
        "IndexError": {
            "list index out of range": "Index too large - check list length",
        },
        "ValueError": {
            "invalid literal": "Check input format/type",
        },
    }

    def __init__(self):
        """Initialize error fixer."""
        self.provider_chain = get_provider_chain()
        logger.info("Error Fixer initialized")

    async def fix_error(
        self, 
        error_message: str, 
        code: str = "",
        traceback: str = "",
        language: str = "python"
    ) -> ErrorFixResult:
        """Fix an error from error message and optional code."""
        try:
            # Parse the error
            error_type, error_details = self._parse_error(error_message)
            
            # Try quick fixes first
            quick_fixes = self._try_quick_fixes(error_type, error_details, code)
            
            if quick_fixes:
                return ErrorFixResult(
                    success=True,
                    original_error=error_message,
                    fixes=quick_fixes,
                    fixed_code=quick_fixes[0].fixed_code if code else "",
                    summary=f"Applied {len(quick_fixes)} quick fix(es)"
                )
            
            # Use AI for complex fixes
            ai_fix = await self._ai_fix(error_message, code, traceback, language)
            
            if ai_fix:
                return ErrorFixResult(
                    success=True,
                    original_error=error_message,
                    fixes=[ai_fix],
                    fixed_code=ai_fix.fixed_code,
                    summary=ai_fix.explanation
                )
            
            return ErrorFixResult(
                success=False,
                original_error=error_message,
                fixes=[],
                fixed_code=code,
                summary="Could not automatically fix this error",
                error="No suitable fix found"
            )
            
        except Exception as e:
            logger.error(f"Error fixing failed: {e}")
            return ErrorFixResult(
                success=False,
                original_error=error_message,
                fixes=[],
                fixed_code=code,
                summary="Error fixing failed",
                error=str(e)
            )

    def _parse_error(self, error_message: str) -> Tuple[str, str]:
        """Parse error message into type and details."""
        lines = error_message.split('\n')
        first_line = lines[0] if lines else ""
        
        # Extract error type
        match = re.match(r'(\w+Error|\w+Exception):\s*(.*)', first_line)
        if match:
            return match.group(1), match.group(2)
        
        return "UnknownError", error_message

    def _try_quick_fixes(
        self, 
        error_type: str, 
        error_details: str, 
        code: str
    ) -> List[ErrorFix]:
        """Try quick pattern-based fixes."""
        fixes = []
        
        if error_type == "IndentationError" and code:
            # Fix common indentation issues
            fixed = self._fix_indentation(code)
            if fixed != code:
                fixes.append(ErrorFix(
                    original_error=f"{error_type}: {error_details}",
                    fixed_code=fixed,
                    explanation="Fixed indentation issues",
                    confidence=0.9,
                    changes_made=["Fixed indentation to use 4 spaces consistently"]
                ))
        
        elif error_type == "SyntaxError" and code:
            # Try to fix common syntax issues
            fixed = self._fix_syntax(code)
            if fixed != code:
                fixes.append(ErrorFix(
                    original_error=f"{error_type}: {error_details}",
                    fixed_code=fixed,
                    explanation="Fixed syntax error",
                    confidence=0.8,
                    changes_made=["Fixed syntax issue"]
                ))
        
        elif "'str' and 'int'" in error_details and code:
            # Type conversion fix
            fixed = self._fix_type_conversion(code, error_details)
            if fixed != code:
                fixes.append(ErrorFix(
                    original_error=f"{error_type}: {error_details}",
                    fixed_code=fixed,
                    explanation="Added type conversion",
                    confidence=0.85,
                    changes_made=["Added str() conversion"]
                ))
        
        elif "list index out of range" in error_details and code:
            # Index bounds fix
            fixed = self._fix_index_bounds(code)
            if fixed != code:
                fixes.append(ErrorFix(
                    original_error=f"{error_type}: {error_details}",
                    fixed_code=fixed,
                    explanation="Added index bounds check",
                    confidence=0.8,
                    changes_made=["Added bounds checking"]
                ))
        
        elif "KeyError" in error_type and code:
            # Key error fix
            fixed = self._fix_key_error(code, error_details)
            if fixed != code:
                fixes.append(ErrorFix(
                    original_error=f"{error_type}: {error_details}",
                    fixed_code=fixed,
                    explanation="Added .get() with default value",
                    confidence=0.85,
                    changes_made=["Changed to .get() with default"]
                ))
        
        elif "has no attribute" in error_details and code:
            # Attribute error fix
            fixed = self._fix_attribute_error(code, error_details)
            if fixed != code:
                fixes.append(ErrorFix(
                    original_error=f"{error_type}: {error_details}",
                    fixed_code=fixed,
                    explanation="Added null check before attribute access",
                    confidence=0.75,
                    changes_made=["Added hasattr() check"]
                ))
        
        return fixes

    async def _ai_fix(
        self, 
        error_message: str, 
        code: str, 
        traceback: str,
        language: str
    ) -> Optional[ErrorFix]:
        """Use AI to fix the error."""
        try:
            context = f"Error:\n{error_message}\n\n"
            if traceback:
                context += f"Traceback:\n{traceback}\n\n"
            if code:
                context += f"Code:\n```{language}\n{code}\n```"
            
            prompt = f"""Fix this {language} error:

{context}

Analyze the error and provide a fixed version of the code.
If the error is in the provided code, return the fixed code.
If no code is provided, explain how to fix the error.

Return in this format:
```fixed_code
[your fixed code here]
```
```explanation
Brief explanation of what was wrong and how it was fixed
```
```changes
- change 1
- change 2
```"""

            messages = [
                {"role": "system", "content": "You are Genesis, an expert debugger. Fix errors accurately and completely."},
                {"role": "user", "content": prompt}
            ]
            
            result = await self.provider_chain.call(
                messages=messages,
                user_input="Fix error"
            )
            
            if result.success:
                return self._parse_ai_fix(result.response.content)
            
            return None
            
        except Exception as e:
            logger.error(f"AI fix failed: {e}")
            return None

    def _parse_ai_fix(self, response: str) -> Optional[ErrorFix]:
        """Parse AI response into ErrorFix."""
        code_match = re.search(r'```fixed_code\n(.*?)```', response, re.DOTALL)
        exp_match = re.search(r'```explanation\n(.*?)```', response, re.DOTALL)
        changes_match = re.search(r'```changes\n(.*?)```', response, re.DOTALL)
        
        if code_match:
            changes = []
            if changes_match:
                changes = [c.strip() for c in changes_match.group(1).split('\n') if c.strip()]
            
            return ErrorFix(
                original_error="",
                fixed_code=code_match.group(1).strip(),
                explanation=exp_match.group(1).strip() if exp_match else "Fixed using AI",
                confidence=0.9,
                changes_made=changes if changes else ["Applied AI-generated fix"]
            )
        
        return None

    def _fix_indentation(self, code: str) -> str:
        """Fix common indentation issues."""
        lines = code.split('\n')
        fixed_lines = []
        
        for line in lines:
            # Convert tabs to 4 spaces
            if '\t' in line:
                line = line.replace('\t', '    ')
            fixed_lines.append(line)
        
        return '\n'.join(fixed_lines)

    def _fix_syntax(self, code: str) -> str:
        """Fix common syntax issues."""
        code = code.strip()
        
        # Fix missing closing brackets
        open_parens = code.count('(')
        close_parens = code.count(')')
        if open_parens > close_parens:
            code += ')' * (open_parens - close_parens)
        
        open_brackets = code.count('[')
        close_brackets = code.count(']')
        if open_brackets > close_brackets:
            code += ']' * (open_brackets - close_brackets)
        
        open_braces = code.count('{')
        close_braces = code.count('}')
        if open_braces > close_braces:
            code += '}' * (open_braces - close_braces)
        
        return code

    def _fix_type_conversion(self, code: str, error_details: str) -> str:
        """Fix type conversion issues."""
        # Simple heuristic: wrap int literals with str()
        if "'str' and 'int'" in error_details:
            lines = code.split('\n')
            fixed_lines = []
            
            for line in lines:
                # Add str() around numbers when concatenating with strings
                if '+' in line and ('f"' in line or "'" in line):
                    # Simple fix - just return as is for complex cases
                    pass
                fixed_lines.append(line)
            
            return '\n'.join(fixed_lines)
        
        return code

    def _fix_index_bounds(self, code: str) -> str:
        """Add index bounds checking."""
        # This is a simplified fix - AI would do better
        return code

    def _fix_key_error(self, code: str, error_details: str) -> str:
        """Fix KeyError by using .get() with default."""
        # Extract the key if visible
        key_match = re.search(r"KeyError:\s*['\"]?(\w+)['\"]?", error_details)
        if key_match:
            key = key_match.group(1)
            # Replace dict[key] with dict.get(key, default)
            pattern = rf"(\w+)\[{key}\]"
            code = re.sub(pattern, rf"\1.get('{key}')", code)
        
        return code

    def _fix_attribute_error(self, code: str, error_details: str) -> str:
        """Fix AttributeError by adding hasattr check."""
        attr_match = re.search(r"'(\w+)'.*has no attribute '(\w+)'", error_details)
        if attr_match:
            obj, attr = attr_match.groups()
            # Add hasattr check
            code = code.replace(
                f"{obj}.{attr}",
                f"getattr({obj}, '{attr}', None)"
            )
        
        return code


# Singleton
_error_fixer: Optional[ErrorFixer] = None


def get_error_fixer() -> ErrorFixer:
    """Get or create ErrorFixer singleton."""
    global _error_fixer
    if _error_fixer is None:
        _error_fixer = ErrorFixer()
    return _error_fixer