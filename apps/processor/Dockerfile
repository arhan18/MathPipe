FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MATHPIPE_BUCKET=mathpipe-files

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY worker ./worker

# Hugging Face Docker Spaces route traffic to 7860.
EXPOSE 7860

CMD ["python", "-m", "worker.service", "--serve", "7860"]
