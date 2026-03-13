FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock ./
COPY components/ ./components/
COPY flows/ ./flows/
COPY prompts/ ./prompts/

# Install dependencies
RUN uv sync --frozen --no-dev

# Environment variables (override at runtime)
ENV LANGFLOW_SECRET_KEY=${LANGFLOW_SECRET_KEY}

EXPOSE 7860

CMD ["uv", "run", "langflow", "run", "--host", "0.0.0.0", "--port", "7860"]
