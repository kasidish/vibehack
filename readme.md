System Architecture :

Browser → Next.js (page.tsx dashboard)
          ↓
          FastAPI (forecast)
          ↓
          Supabase
          
Browser → Next.js API Route → OpenAI

--------------------------------------

Project Structure :

retailpilot-ai/
│
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── app/
│   ├── pages/api/ai.ts
│   ├── lib/supabase.ts
│   ├── package.json
│   └── Dockerfile
│
├── docker-compose.yml
└── .env

--------------------------------------

How to test :

1. Start the backend (from backend). Use --host 0.0.0.0 if you open the app by IP (e.g. http://192.168.1.112:3000):
   cd backend
   python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

2. Start the frontend (from frontend):
   cd frontend
   npm run dev

3. Open http://192.168.1.112:3000 in the browser (or http://localhost:3000 on this machine).

Backend and frontend are set for IP 192.168.1.112 (frontend/.env.local has NEXT_PUBLIC_API_URL=http://192.168.1.112:8000).