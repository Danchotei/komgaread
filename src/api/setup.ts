export interface SetupStatus { configured: boolean }
export interface SetupCheck { address: 'primary'; reachable: boolean; message: string }
export interface SetupInput { setup_key: string; primary_url: string }

export async function setupRequest<T>(path = '', body?: SetupInput): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api/setup${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      credentials: 'same-origin',
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    })
  } catch { throw new Error('无法连接网站后端，请检查容器状态') }
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `请求失败（HTTP ${response.status}），请检查填写的地址与后端状态`)
  if (!data) throw new Error('后端响应异常，请检查反向代理配置')
  return data as T
}
