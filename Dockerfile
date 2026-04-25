# syntax=docker/dockerfile:1.7

ARG BUILDER_IMAGE=dhi.io/python:3.12.12-debian13-dev
ARG RUNTIME_IMAGE=dhi.io/python:3.12.12-debian13

FROM ${BUILDER_IMAGE} AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VENV_PATH=/opt/venv

WORKDIR /app

RUN python -m venv ${VENV_PATH}
ENV PATH="${VENV_PATH}/bin:${PATH}"

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app

FROM ${RUNTIME_IMAGE} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    PORT=8000

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
