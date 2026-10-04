FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/app/.venv/bin:/home/user/.local/bin:$PATH \
    UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PORT=7860
WORKDIR /home/user/app
COPY --chown=user pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY --chown=user engine ./engine
COPY --chown=user artifacts ./artifacts
COPY --chown=user dataset ./dataset
COPY --chown=user out ./out
EXPOSE 7860
# The host sets PORT (Render, Hugging Face use their own); default 7860.
CMD ["sh", "-c", "uvicorn engine.api.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
