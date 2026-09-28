/**
 * SovereignAI — Centralized API client.
 *
 * All fetch calls go through this module so that:
 * 1. Cookie credentials are always included (same-origin).
 * 2. 401 responses redirect to login automatically.
 * 3. Content-Type defaults to JSON unless overridden.
 */

const API_BASE = '';  // same origin — Vite proxy in dev, FastAPI in prod

/** Normalize a FastAPI error body into a readable string. `detail` is a
 * plain string for HTTPException, but a list of {msg, loc, ...} objects
 * for pydantic validation errors (422s) -- without this, those render as
 * "[object Object]". */
function extractErrorMessage(body, fallback) {
  const detail = body?.detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => d?.msg || JSON.stringify(d)).join('; ') || fallback;
  }
  return detail || fallback;
}

export async function fetchAPI(url, options = {}) {
  const isFormData = options.body instanceof FormData;

  const defaultHeaders = isFormData ? {} : { 'Content-Type': 'application/json' };

  const merged = {
    ...options,
    credentials: 'same-origin',
    headers: {
      ...defaultHeaders,
      ...(options.headers || {}),
    },
  };

  const res = await fetch(`${API_BASE}${url}`, merged);

  if (res.status === 401 && !url.includes('/auth/login') && !url.includes('/me') && window.location.pathname !== '/login') {
    window.location.href = '/login';
    throw new Error('Session expired. Please log in.');
  }

  return res;
}

/** GET convenience wrapper */
export async function apiGet(url) {
  const res = await fetchAPI(url);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(extractErrorMessage(err, res.statusText));
  }
  return res.json();
}

/** POST convenience wrapper (JSON body) */
export async function apiPost(url, body) {
  const res = await fetchAPI(url, {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(extractErrorMessage(err, res.statusText));
  }
  return res.json();
}

/** POST with streaming NDJSON — invokes onEvent for each parsed event object */
export async function apiStream(url, body, onEvent) {
  const res = await fetchAPI(url, {
    method: 'POST',
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(extractErrorMessage(err, res.statusText));
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const emitLine = (line) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    try {
      onEvent(JSON.parse(trimmed));
    } catch {
      // skip malformed lines
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      emitLine(line);
    }
  }

  // process remaining buffer
  if (buffer.trim()) {
    emitLine(buffer);
  }
}

/** Upload file as multipart FormData */
export async function apiUpload(url, file) {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetchAPI(url, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(extractErrorMessage(err, res.statusText));
  }
  return res.json();
}

/** DELETE convenience wrapper */
export async function apiDelete(url, body) {
  const options = { method: 'DELETE' };
  if (body) {
    options.body = JSON.stringify(body);
  }
  const res = await fetchAPI(url, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(extractErrorMessage(err, res.statusText));
  }
  return res.json();
}

/** PUT convenience wrapper */
export async function apiPut(url, body) {
  const res = await fetchAPI(url, {
    method: 'PUT',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(extractErrorMessage(err, res.statusText));
  }
  return res.json();
}

/** PATCH convenience wrapper */
export async function apiPatch(url, body) {
  const res = await fetchAPI(url, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(extractErrorMessage(err, res.statusText));
  }
  return res.json();
}
