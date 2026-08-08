export async function onRequestPost(context) {
  const { request, env } = context;
  
  const NVIDIA_API_KEY = env.NVIDIA_API_KEY || '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';
  const INVOKE_URL = 'https://integrate.api.nvidia.com/v1/chat/completions';

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