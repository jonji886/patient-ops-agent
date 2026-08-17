FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml setup.py README.md ./
COPY src ./src
RUN pip install --no-cache-dir '.[postgres]'
COPY contracts ./contracts
COPY data ./data
EXPOSE 8000
CMD ["patient-ops-agent"]
