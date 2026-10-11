FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable
COPY app ./app
COPY data/demo ./data/demo
COPY reports/metrics_by_sku.csv reports/metrics_by_horizon.csv ./reports/
COPY .streamlit ./.streamlit
COPY scripts/run_demo.py ./scripts/run_demo.py
EXPOSE 8501
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=2)"]
CMD ["/app/.venv/bin/python", "scripts/run_demo.py", "--address", "0.0.0.0", "--port", "8501"]
