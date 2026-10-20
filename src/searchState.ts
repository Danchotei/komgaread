/**
 * 搜索相关的跨页面内存状态。
 *
 * 目前负责：
 * 点击分类或系列详情里的作者／分类／标签时，准备新搜索的初始参数。
 * 返回目标及窗口滚动位置由 App.vue 页面栈管理；结果和分页由 KeepAlive 保留。
 *
 * 此文件不请求 API、不缓存封面图片，也不保存账号密码或登录会话。
 * 状态是普通 JavaScript 对象，不是 ref/reactive；搜索页挂载时读取入口参数。
 * 刷新或关闭网页后清空；登录、退出等身份重置时由 App.vue 调用 resetSearchState。
 */

/** 一张搜索结果卡片需要的数据，图片这里只存地址。 */

export interface SearchSeries {
  id: string
  title: string
  booksCount: number // 本项目中对应章节数量。
  genres?: string[] // 系列分类，搜索卡片中以纯文本显示。
  thumbnailUrl: string
  lastReleaseDate?: string | null // 序号最后一章的发行日期，可能缺失。
}

/** 搜索页的初始数据；返回时直接复用缓存的页面实例。 */
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
}

export const searchState: {
  snapshot: SearchSnapshot | null
} = { snapshot: null }

/** 身份变化时清理搜索数据，防止不同账号之间沿用结果。 */
export function resetSearchState() {
  searchState.snapshot = null
}

/**
 * 系列详情中点击作者、分类或标签的统一入口。
 * 新建未执行的搜索初始数据并跳转；实际 API 请求由 SearchView.vue 发起。
 */
export function searchMetadata(keyword: string, filterType: 'author' | 'genre' | 'tag') {
  searchState.snapshot = {
    keyword, submitted: keyword, filterType, exact: true,
    order: 'desc', results: [], total: 0, last: true,
    searched: false, page: 0, scrollY: 0,
  }
  window.location.hash = '#/search'
}
