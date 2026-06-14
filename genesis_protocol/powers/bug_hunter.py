"""Genesis Protocol - Bug Hunter

AI-powered code analysis and bug detection.
Finds bugs, security issues, performance problems, and code smells.
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from genesis_protocol.ai.provider_chain import get_provider_chain, AICallResult
from genesis_protocol.utils.logger import get_logger

logger = get_logger("powers.bug_hunter")


class BugSeverity(Enum):
    """Bug severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class BugType(Enum):
    """Types of bugs/issues."""
    SYNTAX_ERROR = "syntax_error"
    RUNTIME_ERROR = "runtime_error"
    LOGIC_ERROR = "logic_error"
    SECURITY = "security"
    PERFORMANCE = "performance"
    CODE_SMELL = "code_smell"
    BEST_PRACTICE = "best_practice"
    TYPE_ERROR = "type_error"
    NULL_CHECK = "null_check"
    RESOURCE_LEAK = "resource_leak"


@dataclass
class Bug:
    """Detected bug."""
    line: Optional[int]
    severity: BugSeverity
    bug_type: BugType
    title: str
    description: str
    suggestion: str
    code_snippet: Optional[str] = None


@dataclass
class AnalysisResult:
    """Code analysis result."""
    success: bool
    bugs: List[Bug]
    score: int  # 0-100 code quality score
    summary: str
    security_issues: int
    performance_issues: int
    error: Optional[str] = None


class BugHunter:
    """
    AI-powered bug detection and code analysis.
    
    Capabilities:
    - Syntax error detection
    - Logic error finding
    - Security vulnerability scanning
    - Performance issue detection
    - Code quality analysis
    - Auto-fix suggestions
    """

    # Common patterns for static analysis
    PATTERNS = {
        BugType.NULL_CHECK: [
            (r'\.get\([^)]+\)\s*(?!if|and|or)', "Potential None access after .get()"),
            (r'if\s+not\s+\w+\s*:', "Check for empty value instead of truthiness"),
        ],
        BugType.RESOURCE_LEAK: [
            (r'open\([^)]+\)\s*(?!as)', "File opened without 'with' statement"),
            (r'open\([^)]+\)\s*as[^:]+:\s*(?!try)', "File not in try-finally block"),
        ],
        BugType.SECURITY: [
            (r'sql\s*\+\s*["\']', "SQL injection risk - use parameterized queries"),
            (r'eval\s*\(', "Code injection risk - avoid eval()"),
            (r'exec\s*\(', "Code injection risk - avoid exec()"),
            (r'password\s*=\s*["\'][^"\']+["\']', "Hardcoded password detected"),
            (r'api[_-]?key\s*=\s*["\'][^"\']+["\']', "Hardcoded API key detected"),
            (r'token\s*=\s*["\'][^"\']+["\']', "Hardcoded token detected"),
        ],
        BugType.PERFORMANCE: [
            (r'for\s+\w+\s+in\s+.*:\s*\n\s*for\s+\w+\s+in', "Nested loops - consider optimization"),
            (r'\.append\([^)]+\)\s+for\s+', "List comprehension more efficient than append loop"),
        ],
    }

    def __init__(self):
        """Initialize bug hunter."""
        self.provider_chain = get_provider_chain()
        logger.info("Bug Hunter initialized")

    async def analyze(self, code: str, language: str = "python") -> AnalysisResult:
        """Analyze code for bugs and issues."""
        try:
            # Static analysis first
            static_bugs = self._static_analysis(code, language)
            
            # AI-powered deep analysis
            ai_bugs = await self._ai_analysis(code, language)
            
            # Combine results
            all_bugs = static_bugs + ai_bugs
            
            # Calculate score
            score = self._calculate_score(code, all_bugs)
            
            return AnalysisResult(
                success=True,
                bugs=all_bugs,
                score=score,
                summary=self._generate_summary(all_bugs, score),
                security_issues=len([b for b in all_bugs if b.bug_type == BugType.SECURITY]),
                performance_issues=len([b for b in all_bugs if b.bug_type == BugType.PERFORMANCE])
            )
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return AnalysisResult(
                success=False,
                bugs=[],
                score=0,
                summary="",
                security_issues=0,
                performance_issues=0,
                error=str(e)
            )

    def _static_analysis(self, code: str, language: str) -> List[Bug]:
        """Perform static pattern-based analysis."""
        bugs = []
        lines = code.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            # Check patterns
            for bug_type, patterns in self.PATTERNS.items():
                for pattern, message in patterns:
                    if re.search(pattern, line):
                        bugs.append(Bug(
                            line=line_num,
                            severity=self._get_severity(bug_type),
                            bug_type=bug_type,
                            title=self._format_title(bug_type),
                            description=message,
                            suggestion=self._get_suggestion(bug_type),
                            code_snippet=line.strip()
                        ))
        
        return bugs

    async def _ai_analysis(self, code: str, language: str) -> List[Bug]:
        """Use AI for deep code analysis."""
        try:
            prompt = f"""Analyze this {language} code for bugs, issues, and improvements:

```{language}
{code}
```

Find issues in these categories:
1. Logic errors
2. Runtime errors
3. Edge cases not handled
4. Type errors
5. Error handling issues

Return in this format:
```issues
LINE|NEVERITY|TYPE|TITLE|DESCRIPTION|SUGGESTION
```

Where:
- LINE = line number or "N/A"
- SEVERITY = critical/high/medium/low
- TYPE = logic_error/runtime_error/type_error/null_check/error_handling
- TITLE = short issue name
- DESCRIPTION = what the problem is
- SUGGESTION = how to fix it

If no issues found, return: NO_ISSUES"""

            messages = [
                {"role": "system", "content": "You are Genesis, an expert code reviewer. Be thorough and find real bugs."},
                {"role": "user", "content": prompt}
            ]
            
            result = await self.provider_chain.call(
                messages=messages,
                user_input="Analyze code"
            )
            
            if result.success:
                return self._parse_ai_response(result.response.content)
            
            return []
            
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return []

    def _parse_ai_response(self, response: str) -> List[Bug]:
        """Parse AI response into Bug objects."""
        bugs = []
        
        if "NO_ISSUES" in response:
            return bugs
        
        for line in response.split('\n'):
            if '|' not in line:
                continue
            
            parts = line.split('|')
            if len(parts) < 6:
                continue
            
            try:
                bug = Bug(
                    line=int(parts[0]) if parts[0] != "N/A" else None,
                    severity=BugSeverity(parts[1]),
                    bug_type=BugType(parts[2]),
                    title=parts[3].strip(),
                    description=parts[4].strip(),
                    suggestion=parts[5].strip()
                )
                bugs.append(bug)
            except (ValueError, IndexError):
                continue
        
        return bugs

    def _get_severity(self, bug_type: BugType) -> BugSeverity:
        """Get default severity for bug type."""
        mapping = {
            BugType.SECURITY: BugSeverity.CRITICAL,
            BugType.RUNTIME_ERROR: BugSeverity.HIGH,
            BugType.LOGIC_ERROR: BugSeverity.HIGH,
            BugType.NULL_CHECK: BugSeverity.MEDIUM,
            BugType.TYPE_ERROR: BugSeverity.MEDIUM,
            BugType.RESOURCE_LEAK: BugSeverity.MEDIUM,
            BugType.PERFORMANCE: BugSeverity.LOW,
            BugType.CODE_SMELL: BugSeverity.LOW,
            BugType.BEST_PRACTICE: BugSeverity.INFO,
            BugType.SYNTAX_ERROR: BugSeverity.CRITICAL,
        }
        return mapping.get(bug_type, BugSeverity.MEDIUM)

    def _format_title(self, bug_type: BugType) -> str:
        """Format bug type as title."""
        return bug_type.value.replace('_', ' ').title()

    def _get_suggestion(self, bug_type: BugType) -> str:
        """Get fix suggestion for bug type."""
        suggestions = {
            BugType.NULL_CHECK: "Add explicit None check or use optional chaining",
            BugType.SECURITY: "Use secure patterns and never hardcode secrets",
            BugType.PERFORMANCE: "Consider algorithmic optimization",
            BugType.RESOURCE_LEAK: "Use context managers (with statement)",
            BugType.BEST_PRACTICE: "Follow language best practices",
        }
        return suggestions.get(bug_type, "Review and fix this issue")

    def _calculate_score(self, code: str, bugs: List[Bug]) -> int:
        """Calculate code quality score (0-100)."""
        if not code:
            return 0
        
        # Base score
        score = 100
        
        # Deduct for bugs by severity
        for bug in bugs:
            if bug.severity == BugSeverity.CRITICAL:
                score -= 25
            elif bug.severity == BugSeverity.HIGH:
                score -= 15
            elif bug.severity == BugSeverity.MEDIUM:
                score -= 8
            elif bug.severity == BugSeverity.LOW:
                score -= 3
            else:
                score -= 1
        
        return max(0, score)

    def _generate_summary(self, bugs: List[Bug], score: int) -> str:
        """Generate analysis summary."""
        critical = len([b for b in bugs if b.severity == BugSeverity.CRITICAL])
        high = len([b for b in bugs if b.severity == BugSeverity.HIGH])
        medium = len([b for b in bugs if b.severity == BugSeverity.MEDIUM])
        low = len([b for b in bugs if b.severity == BugSeverity.LOW])
        
        rating = "Excellent" if score >= 90 else "Good" if score >= 70 else "Fair" if score >= 50 else "Poor"
        
        return f"""📊 Code Quality Score: {score}/100 ({rating})

Found {len(bugs)} issues:
🔴 Critical: {critical} | 🟠 High: {high} | 🟡 Medium: {medium} | 🔵 Low: {low}

{"⚠️ Critical issues found - fix immediately!" if critical > 0 else "No critical issues!"}"""


# Singleton
_bug_hunter: Optional[BugHunter] = None


def get_bug_hunter() -> BugHunter:
    """Get or create BugHunter singleton."""
    global _bug_hunter
    if _bug_hunter is None:
        _bug_hunter = BugHunter()
    return _bug_hunter