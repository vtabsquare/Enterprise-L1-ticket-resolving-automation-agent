
# Security Constraints

- Never construct or print a raw DATABASE_URL (or any credential) with an embedded password in a command or log output.
- When you need to use a database URL or secret in a temporary script, read it directly from the environment inside the script (e.g., \os.environ['DATABASE_URL']\ or using \python-dotenv\) rather than passing it as a literal string in the command line where it could end up logged or committed.

# Local Development

- Always run Uvicorn with `--reload` during any testing/development session (e.g., `python -m uvicorn app.main:app --reload --port 8000`). This ensures code changes (like prompt updates in Gemini) are automatically picked up, preventing stale-code issues.
