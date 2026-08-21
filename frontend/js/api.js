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
    const detail = payload.detail || payload.message;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg || "Invalid request value").join("; ")
      : (detail || response.statusText);
    const error = new Error(`Request failed (${response.status}): ${message}`);
    error.status = response.status;
    throw error;
  }

  return payload;
}

const responseCache = new Map();

export function clearCachedJSON(url) {
  responseCache.delete(url);
}

export async function getCachedJSON(url, { maxAgeMs = 60_000, force = false } = {}) {
  if (force) {
    responseCache.delete(url);
  }

  const now = Date.now();
  const cached = responseCache.get(url);
  if (cached?.value !== undefined && cached.expiresAt > now) {
    return cached.value;
  }
  if (cached?.promise) {
    return cached.promise;
  }

  const promise = getJSON(url)
    .then((value) => {
      responseCache.set(url, { value, expiresAt: Date.now() + maxAgeMs });
      return value;
    })
    .catch((error) => {
      responseCache.delete(url);
      throw error;
    });
  responseCache.set(url, { promise, expiresAt: 0 });
  return promise;
}
