export async function getJSON(url, options = {}) {
  let response;

  try {
    response = await fetch(url, {
      ...options,
      headers: {
        Accept: "application/json",
        ...(options.headers || {}),
      },
    });
  } catch (error) {
    throw new Error(`Unable to reach the backend: ${error.message}`);
  }

  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error(`Backend returned an invalid response (${response.status}).`);
  }

  if (!response.ok) {
    const message = payload.detail || payload.message || response.statusText;
    throw new Error(`Request failed (${response.status}): ${message}`);
  }

  return payload;
}

