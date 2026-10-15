# The API, the poller, and the Desk agent: one image, three commands (see docker-compose.yml).
# Built from the root of the repository, which holds the memory library beside the backend.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/backend
COPY lighthouse-memory /srv/lighthouse-memory
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
ENV PATH="/srv/backend/.venv/bin:$PATH"
RUN mkdir -p /data && chown nobody:nogroup /data && chmod 700 /data
USER nobody
EXPOSE 8100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
