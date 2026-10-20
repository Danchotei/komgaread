export interface SearchSeries { id: string; title: string; booksCount: number; thumbnailUrl: string }
export interface SearchSnapshot {
  keyword: string
  submitted: string
  order: 'asc' | 'desc'
  results: SearchSeries[]
  total: number
  last: boolean
  searched: boolean
  page: number
  scrollY: number
}
// 当前登录期间的内存状态，不写入持久存储。
export const searchState: { snapshot: SearchSnapshot | null } = { snapshot: null }
export function resetSearchState() { searchState.snapshot = null }
