export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { credentials: 'same-origin' })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(typeof body?.detail === 'string' ? body.detail : '加载失败，请重试')
  }
  return await response.json() as T
}

// 同一本书的写入按顺序执行，前一次失败也不会阻塞后续保存。
const progressQueues = new Map<string, Promise<void>>()
export function saveProgress(bookId: string, page: number): Promise<void> {
  const previous = progressQueues.get(bookId) ?? Promise.resolve()
  const task = previous.catch(() => {}).then(async () => {
    const response = await fetch(`/api/books/${encodeURIComponent(bookId)}/progress`, {
      method: 'PATCH', credentials: 'same-origin', keepalive: true,
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ page }),
    })
    if (!response.ok) {
      const error = await response.json().catch(() => null)
      throw new Error(typeof error?.detail === 'string' ? error.detail : '进度保存失败')
    }
  })
  progressQueues.set(bookId, task)
  void task.finally(() => { if (progressQueues.get(bookId) === task) progressQueues.delete(bookId) }).catch(() => {})
  return task
}
