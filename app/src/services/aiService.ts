import { GoogleGenAI } from '@google/genai';

let aiClient: GoogleGenAI | null = null;

function getAiClient(): GoogleGenAI | null {
  if (!aiClient) {
    const apiKey = process.env.GEMINI_API_KEY;
    if (apiKey) {
      aiClient = new GoogleGenAI({ apiKey });
    }
  }
  return aiClient;
}

export async function askAfconAiAssistant(userPrompt: string): Promise<string> {
  const client = getAiClient();
  if (!client) {
    return `[AFCON360 AI Assistant Mode] 
Thank you for asking about AFCON 360! 
Query: "${userPrompt}"

Key Information:
- AFCON 2027 East Africa (Uganda, Kenya, Tanzania) matches are scheduled across Kampala (Namboole Stadium), Nairobi (Kasarani), and Dar es Salaam.
- Fan Wallets support instant MTN & Airtel Mobile Money deposits, Visa card top-ups, and double-entry escrow protection for property bookings.
- Transport shuttles can be booked directly from Entebbe International Airport (EBB) to major hotels and fan zones.
(To enable live real-time Gemini AI responses, configure your GEMINI_API_KEY in the platform environment.)`;
  }

  try {
    const response = await client.models.generateContent({
      model: 'gemini-2.5-flash',
      contents: [
        {
          role: 'user',
          parts: [
            {
              text: `You are the official AFCON360 AI Concierge and Tournament Guide. 
Provide a clear, helpful, concise, and enthusiastic response to the fan's query: "${userPrompt}".
Emphasize East Africa hospitality, stadium details, transport shuttles, accommodation tips, and fan wallet payments.`
            }
          ]
        }
      ]
    });

    return response.text || 'No response generated from AFCON360 AI.';
  } catch (err: any) {
    console.error('Error calling Gemini API:', err);
    return `I received your question regarding "${userPrompt}". Currently, our AI guide is operating in offline assistant mode. Feel free to explore our Events, Accommodation, and Transport tabs!`;
  }
}
