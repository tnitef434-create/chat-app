export async function onRequestPost(context) {
  const { request, env } = context;
  
  const NVIDIA_API_KEY = env.NVIDIA_API_KEY;
  const INVOKE_URL = 'https://integrate.api.nvidia.com/v1/chat/completions';
  
  if (!NVIDIA_API_KEY) {
    return new Response(
      JSON.stringify({ error: 'NVIDIA_API_KEY not configured in Worker secrets' }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    );
  }

  try {
    const body = await request.json();
    
    const response = await fetch(INVOKE_URL, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${NVIDIA_API_KEY}`,
        'Accept': 'text/event-stream',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(body)
    });

    if (!response.ok) {
      const err = await response.text();
      return new Response(
        JSON.stringify({ error: `NVIDIA API Error: ${response.status} ${err}` }),
        { status: response.status, headers: { 'Content-Type': 'application/json' } }
      );
    }

    // Stream the response back to client
    return new Response(response.body, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive'
      }
    });
  } catch (err) {
    return new Response(
      JSON.stringify({ error: err.message }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    );
  }
}