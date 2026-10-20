/**
 * 搜索相关的跨页面内存状态。
 *
 * 目前负责：
 * 1. 搜索页离开时保存快照，返回时恢复关键词、排序、结果、分页及滚动位置。
 * 2. 点击系列详情里的作者／分类／标签时，准备对应字段的精确搜索并跳转。
 * 3. 记录该搜索的来源系列，让“返回系列”能回到指定详情及原滚动位置。
 *
 * 此文件不请求 API、不缓存封面图片，也不保存账号密码或登录会话。
 * 状态是普通 JavaScript 对象，不是 ref/reactive；页面在挂载和卸载时主动读取／写入。
 * 刷新或关闭网页后清空；登录、退出等身份重置时由 App.vue 调用 resetSearchState。
 */

/** 一张搜索结果卡片需要的数据，图片这里只存地址。 */
import { seriesState } from './seriesState'

export interface SearchSeries {
  id: string
  title: string
  booksCount: number // 本项目中对应章节数量。
  thumbnailUrl: string
  lastReleaseDate?: string | null // 序号最后一章的发行日期，可能缺失。
}

/** 搜索页快照；SearchView.vue 负责保存和恢复。 */
export interface SearchSnapshot {
  keyword: string // 输入框当前文字，用户可能修改后还没有提交。
  submitted: string // 结果实际对应的关键词，加载更多时继续使用它。
  order: 'asc' | 'desc' // 末章发行日期：asc 从旧到新，desc 从新到旧。
  results: SearchSeries[] // 已加载的全部结果，包括“加载更多”追加的内容。
  total: number // 匹配系列总数。
  last: boolean // 是否已到最后一页。
  searched: boolean // 是否提交过搜索；false + 预填关键词会触发首次自动搜索。
  page: number // 下一次请求的分页索引，从 0 开始。
  scrollY: number // 搜索页独立容器的 scrollTop，不是窗口的 window.scrollY。
  filterType?: 'all' | 'author' | 'genre' | 'tag' // 手动搜索用 all，点击元数据用对应字段。
  exact?: boolean // 元数据按钮入口使用精确匹配，避免命中名称相近的其他词条。
  sourceSeries?: { id: string; scrollY: number } // 最近发起元数据搜索的系列及当时窗口位置。
}

export const searchState: {
  snapshot: SearchSnapshot | null
  // 点击“返回系列”时设置；SeriesView.vue 恢复滚动后消费并清空，避免重复应用。
  returnPosition: { id: string; scrollY: number } | null
} = { snapshot: null, returnPosition: null }

/** 身份变化时清理搜索数据，防止不同账号之间沿用结果。 */
export function resetSearchState() {
  searchState.snapshot = null
  searchState.returnPosition = null
  seriesState.snapshot = null
}

/**
 * 系列详情中点击作者、分类或标签的统一入口。
 * 新建未执行的搜索快照，记录来源，然后跳转；实际 API 请求由 SearchView.vue 发起。
 * 从另一个系列再次调用时，会替换旧来源，让“返回系列”指向最近发起搜索的系列。
 */
export function searchMetadata(keyword: string, filterType: 'author' | 'genre' | 'tag', sourceId: string) {
  searchState.snapshot = {
    keyword, submitted: keyword, filterType, exact: true,
    order: 'desc', results: [], total: 0, last: true,
    searched: false, page: 0, scrollY: 0,
    sourceSeries: { id: sourceId, scrollY: window.scrollY },
  }
  window.location.hash = '#/search'
}
