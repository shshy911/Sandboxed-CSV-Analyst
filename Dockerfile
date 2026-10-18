FROM python:3.12-slim

RUN pip install --no-cache-dir pandas numpy matplotlib

# run as a non-root user inside the container
RUN useradd -m sandbox
USER sandbox
WORKDIR /app
