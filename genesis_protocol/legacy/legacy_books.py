"""Legacy Books - GLUTTONY Legacy

Generates knowledge books from accumulated data."""

import os
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path


class LegacyBooks:
    """Generates books from accumulated lessons, failures, recoveries, and projects."""
    
    def __init__(self, output_path: str = "."):
        self.output_path = output_path
        Path(output_path).mkdir(parents=True, exist_ok=True)
    
    def _load_from_file(self, filepath: str, key: str) -> List[Dict]:
        """Load data from a JSON file."""
        import json
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    return data.get(key, [])
            except:
                pass
        return []
    
    def generate_book_of_lessons(self) -> str:
        """Generate BOOK_OF_LESSONS.md."""
        lessons = []
        
        # Load from timeline
        timeline_path = "data/timeline.json"
        if os.path.exists(timeline_path):
            import json
            with open(timeline_path, 'r') as f:
                data = json.load(f)
                lessons = data.get('lessons', [])
        
        # Load from archive
        archive_lessons_path = "data/archive/lessons.json"
        if os.path.exists(archive_lessons_path):
            import json
            with open(archive_lessons_path, 'r') as f:
                data = json.load(f)
                lessons.extend(data)
        
        # Generate markdown
        content = f"""# BOOK OF LESSONS
*GLUTTONY  OS+2 Legacy*

Generated: {datetime.now().isoformat()}
Total Lessons: {len(lessons)}

---

## Table of Contents
"""
        
        categories = {}
        for lesson in lessons:
            cat = lesson.get('category', 'general')
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(lesson)
        
        for i, cat in enumerate(sorted(categories.keys()), 1):
            content += f"{i}. {cat.title()}\n"
        
        content += "\n---\n\n"
        
        for cat in sorted(categories.keys()):
            content += f"## {cat.title()}\n\n"
            for lesson in categories[cat]:
                content += f"### {lesson.get('lesson', lesson.get('title', 'Untitled'))}\n\n"
                content += f"{lesson.get('context', lesson.get('description', ''))}\n\n"
                content += f"*Recorded: {lesson.get('learned_at', lesson.get('archived_at', 'Unknown'))}*\n\n"
                content += "---\n\n"
        
        filepath = os.path.join(self.output_path, "BOOK_OF_LESSONS.md")
        with open(filepath, 'w') as f:
            f.write(content)
        
        return filepath
    
    def generate_book_of_failures(self) -> str:
        """Generate BOOK_OF_FAILURES.md."""
        failures = []
        
        # Load from journal
        journal_path = "./data/gluttony_os/journal"
        if os.path.exists(journal_path):
            import json
            for date_dir in os.listdir(journal_path):
                date_path = os.path.join(journal_path, date_dir)
                if os.path.isdir(date_path):
                    entries_file = os.path.join(date_path, "entries.json")
                    if os.path.exists(entries_file):
                        with open(entries_file, 'r') as f:
                            entries = json.load(f)
                            failures.extend([e for e in entries if e.get('type') == 'failure'])
        
        content = f"""# BOOK OF FAILURES
*GLUTTONY  OS+2 Legacy*

Generated: {datetime.now().isoformat()}
Total Failures Recorded: {len(failures)}

---

## Philosophy

Every failure is a lesson in disguise. This book documents all failures
to ensure they are never repeated unnecessarily.

---
"""
        
        for failure in failures:
            content += f"### Failure: {failure.get('timestamp', 'Unknown Date')}\n\n"
            content += f"**Entry:** {failure.get('content', 'No description')}\n\n"
            if failure.get('tags'):
                content += f"**Tags:** {', '.join(failure.get('tags', []))}\n\n"
            content += "---\n\n"
        
        filepath = os.path.join(self.output_path, "BOOK_OF_FAILURES.md")
        with open(filepath, 'w') as f:
            f.write(content)
        
        return filepath
    
    def generate_book_of_recoveries(self) -> str:
        """Generate BOOK_OF_RECOVERIES.md."""
        recoveries = []
        
        # Load from timeline
        timeline_path = "data/timeline.json"
        if os.path.exists(timeline_path):
            import json
            with open(timeline_path, 'r') as f:
                data = json.load(f)
                recoveries = data.get('recoveries', [])
        
        content = f"""# BOOK OF RECOVERIES
*GLUTTONY  OS+2 Legacy*

Generated: {datetime.now().isoformat()}
Total Recoveries: {len(recoveries)}

---

## Recovery Log

Every recovery represents resilience. These entries document how
GLUTTONY recovered from failures.

---
"""
        
        for recovery in recoveries:
            content += f"### Recovery from: {recovery.get('failure_context', 'Unknown Failure')}\n\n"
            content += f"**Method:** {recovery.get('recovery_method', 'Unknown method')}\n\n"
            content += f"**Lessons Learned:**\n{recovery.get('lessons_learned', 'No lessons recorded')}\n\n"
            content += f"*Recovered: {recovery.get('recovered_at', 'Unknown date')}*\n\n"
            content += "---\n\n"
        
        filepath = os.path.join(self.output_path, "BOOK_OF_RECOVERIES.md")
        with open(filepath, 'w') as f:
            f.write(content)
        
        return filepath
    
    def generate_book_of_projects(self) -> str:
        """Generate BOOK_OF_PROJECTS.md."""
        projects = []
        
        # Load from relationship history
        rel_path = "data/legacy/relationship_history.json"
        if os.path.exists(rel_path):
            import json
            with open(rel_path, 'r') as f:
                data = json.load(f)
                for rel in data.values():
                    projects.extend(rel.get('shared_projects', []))
        
        # Load from knowledge graph
        kg_path = "data/legacy/knowledge_graph.json"
        if os.path.exists(kg_path):
            import json
            with open(kg_path, 'r') as f:
                data = json.load(f)
                nodes = data.get('nodes', {})
                projects.extend([n for n in nodes.values() if n.get('type') == 'project'])
        
        content = f"""# BOOK OF PROJECTS
*GLUTTONY  OS+2 Legacy*

Generated: {datetime.now().isoformat()}
Total Projects: {len(projects)}

---

## Active Projects
"""
        
        active = [p for p in projects if p.get('status') == 'active']
        for proj in active:
            content += f"### {proj.get('name', 'Unnamed Project')}\n\n"
            content += f"**Description:** {proj.get('description', 'No description')}\n\n"
            content += f"**Status:** Active\n\n"
            content += f"**Started:** {proj.get('started_at', proj.get('created_at', 'Unknown'))}\n\n"
            content += "---\n\n"
        
        content += "\n## Completed Projects\n"
        
        completed = [p for p in projects if p.get('status') == 'completed']
        for proj in completed:
            content += f"### {proj.get('name', 'Unnamed Project')}\n\n"
            content += f"**Description:** {proj.get('description', 'No description')}\n\n"
            content += f"**Started:** {proj.get('started_at', proj.get('created_at', 'Unknown'))}\n\n"
            content += f"**Completed:** {proj.get('ended_at', 'Unknown')}\n\n"
            content += "---\n\n"
        
        filepath = os.path.join(self.output_path, "BOOK_OF_PROJECTS.md")
        with open(filepath, 'w') as f:
            f.write(content)
        
        return filepath
    
    def generate_all_books(self) -> Dict[str, str]:
        """Generate all legacy books."""
        return {
            'lessons': self.generate_book_of_lessons(),
            'failures': self.generate_book_of_failures(),
            'recoveries': self.generate_book_of_recoveries(),
            'projects': self.generate_book_of_projects()
        }


_legacy_books: Optional[LegacyBooks] = None


def get_legacy_books() -> LegacyBooks:
    """Get legacy books singleton."""
    global _legacy_books
    if _legacy_books is None:
        _legacy_books = LegacyBooks()
    return _legacy_books
