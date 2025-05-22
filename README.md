# QSR Local Demo

This repository contains a local, Dockerized pipeline to demonstrate an end-to-end "Qualitative Safety Report" (QSR) generation process.

## Quick Start

### Prerequisites (non-Docker path)

```bash
# Clone
git clone <YOUR_REPO_URL_HERE> qsr-local && cd qsr-local # Replace <YOUR_REPO_URL_HERE>
# Python 3.11 via pyenv (skip if installed)
pyenv install 3.11.9 && pyenv local 3.11.9
# Poetry env + deps
pip install poetry
poetry install --no-root
poetry shell
# LLM key (OpenAI shown here)
export LLM_API_KEY="sk-..."
```

### Docker

Build and run the Docker image:

```bash
docker build -t qsr-demo:latest .
docker run -e LLM_API_KEY=sk-... -p 8501:8501 qsr-demo:latest
```
Then, open your browser and navigate to `http://localhost:8501`.

### Makefile

To run the pipeline steps:
```bash
make demo
```

See `Makefile` for other available targets like `generate`, `extract`, `pss`, `qsr`, `clean`.
