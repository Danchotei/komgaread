/** 系列详情进入元数据搜索前的快照；仅在点击“返回系列”时恢复。 */
export interface SeriesInfo {
  title: string; summary: string; publisher: string; booksCount: number
  thumbnailUrl: string; authors: string[]; genres: string[]; tags: string[]
}
export interface ChapterInfo {
  id: string; title: string; pagesCount: number; thumbnailUrl: string
  readProgress: { page: number; completed: boolean } | null
}
export const seriesState: { snapshot: {
  id: string; series: SeriesInfo; books: ChapterInfo[]
  order: 'asc' | 'desc'; page: number; last: boolean; failed: string[]
} | null } = { snapshot: null }
