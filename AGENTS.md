# AGENTS.md

## Build & Run
- Install: `pip install -r requirements.txt && playwright install chromium`
- Run: `python src/main_trending.py`
- No test framework exists yet; tests should use pytest

## Architecture
- **Entry point**: `src/main_trending.py` - orchestrates 7-step pipeline
- **Data flow**: SkillsFetcher → DetailFetcher → ClaudeSummarizer → Database → TrendAnalyzer → HTMLReporter → ResendSender
- **Database**: SQLite at `data/trends.db` with tables: skills_snapshot, skills_daily, skills_details, skills_history
- **Config**: `src/config.py` loads env vars via python-dotenv; key vars: ZHIPU_API_KEY, RESEND_API_KEY, EMAIL_TO

## Code Style
- Python 3.11+, type hints required (`typing` module: Dict, List, Optional, Any)
- Module docstrings at top, class/method docstrings with Args/Returns sections
- Imports: stdlib → third-party → local (`from src.xxx import ...`)
- Classes use context managers (`__enter__`/`__exit__`) where appropriate
- Chinese comments/docstrings are acceptable (project is bilingual)
- Error handling: catch specific exceptions, log with emoji prefixes (✅, ❌, ⚠️)
- No trailing commas required; snake_case for functions/variables, PascalCase for classes
