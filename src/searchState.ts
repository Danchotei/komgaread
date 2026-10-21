import { navigateTo } from './navigation'

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

/** 新搜索的一次性入口参数；结果、分页和滚动由页面实例保存。 */
export interface SearchEntry {
  keyword: string
  filterType?: 'all' | 'author' | 'genre' | 'tag' // 手动搜索用 all，点击元数据用对应字段。
  exact?: boolean // 元数据按钮入口使用精确匹配，避免命中名称相近的其他词条。
}

export const searchState: {
  pendingSearch: SearchEntry | null
} = { pendingSearch: null }

/** 身份变化时清理搜索数据，防止不同账号之间沿用结果。 */
export function resetSearchState() {
  searchState.pendingSearch = null
}

/**
 * 系列详情中点击作者、分类或标签的统一入口。
 * 新建未执行的搜索初始数据并跳转；实际 API 请求由 SearchView.vue 发起。
 */
export function searchMetadata(keyword: string, filterType: 'author' | 'genre' | 'tag') {
  searchState.pendingSearch = { keyword, filterType, exact: true }
  navigateTo('#/search')
}
