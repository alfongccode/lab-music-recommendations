class HttpError extends Error {
  constructor(message, { status, url, body } = {}) {
    super(message);
    this.name = 'HttpError';
    this.status = status;
    this.url = url;
    this.body = body;
  }
}

async function parseBody(response) {
  const contentType = response.headers?.get?.('content-type') ?? '';

  if (!contentType.includes('application/json')) {
    return response.text().catch(() => null);
  }

  return response.json().catch(() => null);
}

async function request(url, options = {}) {
  const { signal, ...rest } = options;

  const response = await fetch(url, { ...rest, signal });
  const body = await parseBody(response);

  if (!response.ok) {
    throw new HttpError(`Request to ${url} failed with ${response.status}`, {
      status: response.status,
      url,
      body,
    });
  }

  return body;
}

function post(url, data, { signal } = {}) {
  return request(url, {
    method: 'POST',
    body: data,
    signal,
  });
}

export { post };