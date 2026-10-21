<script setup lang="ts">
import { onActivated, onDeactivated, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import type { User } from '../api/auth'
import { getJson } from '../api/library'

defineProps<{ user: User; loggingOut: boolean; message: string }>()
defineEmits<{ logout: [] }>()
type Kind = 'history' | 'favorites'
interface Item { id: string; title: string; booksCount: number; thumbnailUrl: string }
const selected = ref<Kind>('history')
const createList = () => ({ items: [] as Item[], page: 0, last: false, busy: false, error: '' })
const lists = reactive({ history: createList(), favorites: createList() })
const failed = reactive(new Set<string>())
const favoriteKeyword = ref('')
const appliedKeyword = ref('')
const versions = { history: 0, favorites: 0 }
let searchTimer: ReturnType<typeof setTimeout> | undefined
async function searchFavorites() {
  clearTimeout(searchTimer)
  const keyword = favoriteKeyword.value.trim()
  if (keyword.length > 200) return
  appliedKeyword.value = keyword
  await load('favorites', false, true)
}
watch(favoriteKeyword, () => {
  clearTimeout(searchTimer)
  // 输入一变化就让旧响应失效，避免防抖等待期间旧结果闪回。
  versions.favorites++
  lists.favorites.busy = true
  if (!favoriteKeyword.value.trim()) void searchFavorites()
  else searchTimer = setTimeout(() => { void searchFavorites() }, 300)
})
async function load(kind: Kind, more = false, reset = false) {
  const list = lists[kind]
  if (list.busy && !reset) return
  const version = ++versions[kind]
  const keyword = appliedKeyword.value
  list.busy = true
  list.error = ''
  try {
    // 从详情返回时保留已加载页数，一次替换列表，避免先清空造成高度跳变。
    const start = more ? list.page : 0
    const end = more ? start + 1 : reset ? 1 : Math.max(1, list.page)
    const items: Item[] = more ? [...list.items] : []
    let last = false
    let nextPage = start
    for (let page = start; page < end; page++) {
      const path = kind === 'favorites' && keyword
        ? `/api/search?favorites=true&q=${encodeURIComponent(keyword)}&page=${page}`
        : `/api/me/${kind}?page=${page}`
      const data = await getJson<{ items: Item[]; last: boolean }>(path)
      if (version !== versions[kind]) return
      items.push(...data.items)
      last = data.last
      nextPage = page + 1
      if (last) break
    }
    list.items = [...new Map(items.map(item => [item.id, item])).values()]
    list.page = nextPage
    list.last = last
  } catch (cause) {
    if (version === versions[kind]) list.error = cause instanceof Error ? cause.message : '加载失败，请重试'
  } finally { if (version === versions[kind]) list.busy = false }
}
function refresh() {
  void load('history')
  if (appliedKeyword.value !== favoriteKeyword.value.trim()) void searchFavorites()
  else void load('favorites')
}
function stopPending() {
  clearTimeout(searchTimer)
  versions.history++
  versions.favorites++
  lists.history.busy = false
  lists.favorites.busy = false
}
onMounted(refresh)
onActivated(refresh)
onDeactivated(stopPending)
onUnmounted(stopPending)
</script>

<template>
  <main class="tab-page profile-page">
    <h1 class="tab-title">我</h1>
    <p class="account-email">{{ user.email }}</p>
    <button class="text-button" :disabled="loggingOut" @click="$emit('logout')">{{ loggingOut ? '正在退出…' : '退出登录' }}</button>
    <p v-if="message" role="alert">{{ message }}</p>
    <nav class="personal-tabs" aria-label="个人记录">
      <button class="personal-tab" :aria-pressed="selected === 'history'" @click="selected = 'history'">浏览记录</button>
      <button class="personal-tab" :aria-pressed="selected === 'favorites'" @click="selected = 'favorites'">我的收藏</button>
    </nav>
    <section v-for="kind in (['history', 'favorites'] as const)" v-show="selected === kind" :key="kind" :aria-label="kind === 'history' ? '浏览记录' : '我的收藏'" :aria-busy="lists[kind].busy">
      <form v-if="kind === 'favorites'" class="search-form" @submit.prevent="searchFavorites">
        <div class="search-input-row"><input v-model="favoriteKeyword" type="search" aria-label="搜索我的收藏" placeholder="输入关键词" maxlength="200" /><button v-if="favoriteKeyword" class="text-button" type="button" @click="favoriteKeyword = ''">清除</button></div>
      </form>
      <p class="personal-hint">{{ kind === 'history' ? '最近浏览的系列，最多保留 50 条' : '最近收藏的系列排在最前' }}</p>
      <p v-if="lists[kind].error" class="form-message" role="alert">{{ lists[kind].error }} <button class="text-button" :disabled="lists[kind].busy" @click="load(kind)">重试</button></p>
      <p v-if="!lists[kind].items.length && !lists[kind].error" class="empty-state">{{ lists[kind].busy ? '正在加载…' : kind === 'history' ? '暂无浏览记录' : appliedKeyword ? '收藏中没有匹配的系列' : '暂无收藏，点击系列详情中的星星即可收藏' }}</p>
      <div class="personal-series-grid">
        <a v-for="item in lists[kind].items" :key="item.id" class="book-link" :href="`#/series/${encodeURIComponent(item.id)}`">
          <div class="series-cover"><img v-if="!failed.has(item.id)" :src="item.thumbnailUrl" :alt="item.title" loading="lazy" @error="failed.add(item.id)" /><span v-else class="cover-fallback">暂无封面</span></div>
          <h3>{{ item.title }}</h3><p>{{ item.booksCount }} 章</p>
        </a>
      </div>
      <button v-if="lists[kind].page && !lists[kind].last" class="text-button load-more" :disabled="lists[kind].busy" @click="load(kind, true)">{{ lists[kind].busy ? '正在加载…' : '加载更多' }}</button>
    </section>
  </main>
</template>
