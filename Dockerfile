FROM python:3.12-slim

WORKDIR /app
RUN useradd --create-home app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

USER app
ENV MCP_TRANSPORT=streamable-http HOST=0.0.0.0 PORT=8000
EXPOSE 8000
CMD ["leadflow-mcp"]
