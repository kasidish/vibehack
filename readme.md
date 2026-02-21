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

1.Start the backend (from backend):
python -m uvicorn main:app --reload

2.Start the frontend (from frontend):
npm run dev

3.Open http://localhost:3000 in the browser.