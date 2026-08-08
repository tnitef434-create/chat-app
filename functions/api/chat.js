export async function onRequestPost(context) {
  const { request } = context;
  
  const NVIDIA_API_KEY = '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';
  const INVOKE_URL = 'https://integrate.api.nvidia.com/v1/chat/completions';

  try {
    const body = await request.json();
    body.stream = false;
    
    const response = await fetch(INVOKE_URL, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${NVIDIA_API_KEY}`,
        'Accept': 'application/json',
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

    const data = await response.json();
    return new Response(JSON.stringify(data), {
      headers: { 'Content-Type': 'application/json' }
    });
  } catch (err) {
    return new Response(
      JSON.stringify({ error: err.message }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    );
  }
}