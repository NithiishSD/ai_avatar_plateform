# AI Avatar Platform

This project contains a FastAPI backend and a React + Vite frontend for the avatar generation workflow.

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- Docker and Docker Compose
- Git

## Quick start

### 1) Create the environment file

From the project root:

```bash
cp .env.example .env
```

### 2) Create and activate the Python virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

If you prefer to use the existing environment already created in this repo:

```bash
./venv/bin/python --version
```

### 3) Install Python dependencies

```bash
./venv/bin/pip install -r backend/requirements.txt
```

### 4) Start infrastructure containers with Docker

This project uses Redis and PostgreSQL for local infrastructure.

```bash
./start-docker.sh
```

You can stop the containers with:

```bash
docker compose -f backend/docker-compose.yml down
```

### 5) Start the backend API

From the project root:

```bash
cd backend
PYTHONPATH=. ../venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at:

- http://localhost:8000
- http://localhost:8000/docs

### 6) Start the frontend

Open a second terminal and run:

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

The frontend will be available at:

- http://localhost:5173

## Project structure

```text
.
├── backend/
│   ├── app.py
│   ├── celery_app.py
│   ├── contracts.py
│   ├── docker-compose.yml
│   ├── job_queue.py
│   ├── requirements.txt
│   ├── voice_engine.py
│   └── outputs/
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.js
├── docs/
├── tests/
├── .env.example
├── README.md
├── start-docker.sh
├── inputs/
├── outputs/
└── venv/
```

## Useful commands

### Run backend tests

```bash
cd /home/nithiish/Documents/ai_avatar_plateform
./venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q
```

### Build frontend for production

```bash
cd frontend
npm run build
```

## Notes

- The default queue backend is set to `in_memory` in `.env.example` for local development.
- If you want to use Celery/Redis queue processing, set `QUEUE_BACKEND=celery` in your environment and make sure Redis is running.
- The frontend is configured to call the backend from `http://localhost:8000` with CORS enabled for local development.
