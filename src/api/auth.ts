export interface User {
  id: string
  email: string
}

// 浏览器只连接本站 /api，开发时由 Vite 转发给 FastAPI。
export async function authRequest<T>(path: string, body?: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api/auth/${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      credentials: 'same-origin',
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    })
  } catch {
    throw new Error('连接网站后端失败，请确认 FastAPI 已启动')
  }
  if (!response.ok) {
    const error = await response.json().catch(() => null)
    throw new Error(typeof error?.detail === 'string' ? error.detail : '请求失败，请检查后端是否正常运行')
  }
  return response.status === 204 ? undefined as T : await response.json() as T
}
