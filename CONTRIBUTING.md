# Contributing to Alexandria

Thank you for your interest in contributing to Alexandria. We welcome bug reports, documentation enhancements, feature proposals, and pull requests.

---

## Core Guidelines & Policies

1. **Strictly Zero Emojis**:
   - Alexandria adheres to an absolute zero-emoji policy across all code, docstrings, terminal output, log messages, commit messages, and documentation.
   - PRs containing emojis will require revision before merge.

2. **Terminal-Native CLI Philosophy**:
   - Alexandria is built strictly as a terminal workstation. Do not introduce web servers, browser-based GUI frameworks, or heavy external graphical dependencies into the core engine.

3. **Jellyfin File Naming Standards**:
   - All media scrapers and downloaders must organize output files in compliance with the Jellyfin media server naming conventions.

---

## Development Setup

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/alexandria-media/alexandria.git
   cd alexandria
   ```

2. **Create a Virtual Environment**:
   ```bash
   python -m venv .venv
   # On Windows:
   .venv\Scripts\activate
   # On macOS/Linux:
   source .venv/bin/activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install -e ".[dev]"
   ```

4. **Verify Your Environment**:
   ```bash
   python run.py --help
   pytest
   ```

---

## Adding a New Media Provider

Providers are located under `providers/`. When adding a new provider:
1. Implement the required interface (`search`, `get_details`, `get_video_url` or `get_stream_info`).
2. Integrate your provider into `providers/manager.py` using lazy loading properties.
3. Add robust exception handling so network or parsing failures gracefully fall back to alternative providers.
4. Ensure downloaded files are saved using standard naming structures.
5. Add unit and smoke test coverage in `tests/`.

---

## Pull Request Process

1. Fork the repository and create your feature branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. Commit your changes using conventional commit prefixes (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`).
3. Ensure all tests pass:
   ```bash
   pytest
   ```
4. Verify code conforms to PEP 8 syntax standards:
   ```bash
   flake8 --max-line-length=120 --exclude=Book_Files,booker,.venv,__pycache__
   ```
5. Submit your Pull Request against the `main` branch with a clear description of the problem solved.
