import type { SeriesCardItem } from './seriesState'

const key = 'komgaread.daily-recommendations'
export const chinaDay = () => Math.floor((Date.now() + 8 * 3600000) / 86400000)

// 标签页内按账号和中国日期复用；存储不可用时仍可正常加载。
export function readDailyRecommendations(userId: string): SeriesCardItem[] | null {
  try {
    const cache = JSON.parse(sessionStorage.getItem(key) || 'null')
    return cache?.userId === userId && cache.day === chinaDay() && Array.isArray(cache.items)
      ? cache.items : null
  } catch { return null }
}

export function saveDailyRecommendations(userId: string, day: number, items: SeriesCardItem[]) {
  try { sessionStorage.setItem(key, JSON.stringify({ userId, day, items })) } catch { /* 不影响阅读 */ }
}

export function clearDailyRecommendations() {
  try { sessionStorage.removeItem(key) } catch { /* 存储可能被浏览器禁用 */ }
}
