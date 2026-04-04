#!/bin/bash
set -e

echo "Setting up Multi-Agent Research Assistant..."

echo "1. Installing Python dependencies..."
pip install -r requirements.txt

echo "2. Installing frontend dependencies..."
(
  cd frontend
  npm install
)

echo "3. Setting up .env..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "   Created .env from .env.example"
fi

if [ ! -f frontend/.env.local ]; then
    cp frontend/.env.local.example frontend/.env.local
    echo "   Created frontend/.env.local from frontend/.env.local.example"
fi

echo "4. Initializing the code sandbox..."
python -m app.sandbox.environment --setup-sandbox

echo "5. Ingesting sample documents into ChromaDB..."
python -m app.ingestion.ingest --path ./data/sample_docs

echo "6. Running tests..."
pytest tests/ -v

echo ""
echo "Setup complete."
echo "Before starting the app, make sure GROQ_API_KEY is set in .env."
echo "Start the backend with:"
echo "   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
echo "Then start the frontend with:"
echo "   cd frontend && npm run dev"
