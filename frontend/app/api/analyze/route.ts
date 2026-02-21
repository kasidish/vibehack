import { NextResponse } from "next/server"

export async function POST(req: Request) {
  const body = await req.json()

  const response = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${process.env.OPENAI_API_KEY}`,
    },
    body: JSON.stringify({
      model: "gpt-4o-mini",
      messages: [
        {
          role: "system",
          content: "You are a retail AI analyst.",
        },
        {
          role: "user",
          content: `Analyze this sales forecast data and give business insights:\n${JSON.stringify(body)}`,
        },
      ],
    }),
  })

  const data = await response.json()

  return NextResponse.json(data)
}