FROM python:3.11-slim

RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir poetry==1.8.2 &&     poetry config virtualenvs.create false &&     poetry install --no-interaction --no-ansi --no-root

EXPOSE 8501
CMD ["bash", "-c", "make demo && streamlit run dashboard/ui.py --server.headless=true"]
