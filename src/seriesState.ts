/** 系列和章节的数据类型；页面状态由 KeepAlive 保留。 */
export interface SeriesCardItem {
  id: string
  title: string
  booksCount: number
  thumbnailUrl: string
  genres?: string[]
  lastReleaseDate?: string | null
}

export interface SeriesInfo {
  title: string; summary: string; publisher: string; booksCount: number
  thumbnailUrl: string; authors: string[]; genres: string[]; tags: string[]
}
export interface ChapterInfo {
  id: string; title: string; pagesCount: number; thumbnailUrl: string
  readProgress: { page: number; completed: boolean } | null
}
