FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra ocr --extra cloud --extra observability --no-install-project
COPY . .
RUN uv sync --frozen --no-dev --extra ocr --extra cloud --extra observability
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["keel", "api", "--host", "0.0.0.0"]
