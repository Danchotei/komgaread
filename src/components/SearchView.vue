<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, onUnmounted, ref } from 'vue'
import { searchState } from '../searchState'
import AppHeader from './AppHeader.vue'
interface Series { id: string; title: string; booksCount: number; thumbnailUrl: string; lastReleaseDate?: string | null }
const order = ref<'asc' | 'desc'>('desc')
const keyword = ref('')
const sourceSeries = ref<{ id: string; scrollY: number } | null>(null)
function returnToSeries() {
  if (!sourceSeries.value) return
  searchState.returnPosition = { ...sourceSeries.value }
  window.location.replace(`#/series/${encodeURIComponent(sourceSeries.value.id)}`)
}

const results = ref<Series[]>([])
const total = ref(0)
const last = ref(true)
const loading = ref(false)
const searched = ref(false)
const error = ref('')
const failed = ref(new Set<string>())
let page = 0
let submitted = ''
let filterType = 'all'
let exact = false
let controller: AbortController | undefined
let version = 0
let scrollPosition = 0
const scrollContainer = ref<HTMLElement | null>(null)
function rememberScroll() {
  if (scrollContainer.value) scrollPosition = scrollContainer.value.scrollTop
}
onMounted(async () => {
  const saved = searchState.snapshot
  if (saved) {
    keyword.value = saved.keyword
    sourceSeries.value = saved.sourceSeries || null
    submitted = saved.submitted
    filterType = saved.filterType || 'all'
    exact = saved.exact || false
    order.value = saved.order
    results.value = [...saved.results]
    total.value = saved.total
    last.value = saved.last
    searched.value = saved.searched
    page = saved.page
    scrollPosition = saved.scrollY
    await nextTick()
    if (scrollContainer.value) scrollContainer.value.scrollTop = saved.scrollY
    if (!saved.searched && saved.keyword.trim()) void search()
  }
})
onBeforeUnmount(() => {
  rememberScroll()
  searchState.snapshot = {
    keyword: keyword.value, submitted, order: order.value,
    results: [...results.value], total: total.value, last: last.value,
    searched: searched.value, page, scrollY: scrollPosition,
    filterType: filterType as 'all' | 'author' | 'genre' | 'tag', exact,
    sourceSeries: sourceSeries.value || undefined,
  }
})
async function search(more = false, resort = false, manual = false) {
  if (!more && !resort && !keyword.value.trim()) return
  if (more && loading.value) return
  if (manual) { filterType = 'all'; exact = false }
  controller?.abort()
  controller = new AbortController()
  const current = ++version
  if (!more) {
    if (!resort) submitted = keyword.value.trim()
    page = 0
    if (!resort) results.value = []
    failed.value = new Set()
    searched.value = true
  }
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ q: submitted, page: String(page), order: order.value, type: filterType, exact: String(exact) })
    const response = await fetch(`/api/search?${params}`, { signal: controller.signal, credentials: 'same-origin' })
    const data = await response.json()
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '搜索失败')
    if (current !== version) return
    if (more) results.value.push(...data.items)
    else results.value = data.items
    total.value = data.total
    last.value = data.last
    page++
  } catch (cause) {
    if (current === version && !(cause instanceof DOMException && cause.name === 'AbortError')) error.value = cause instanceof Error ? cause.message : '搜索失败，请重试'
  } finally { if (current === version) loading.value = false }
}
async function toggleOrder() {
  if (loading.value) return
  order.value = order.value === 'desc' ? 'asc' : 'desc'
  const top = scrollContainer.value?.scrollTop || 0
  await search(false, true)
  await nextTick()
  if (scrollContainer.value) scrollContainer.value.scrollTop = top
}
onUnmounted(() => { version++; controller?.abort() })
</script>

<template>
  <main ref="scrollContainer" class="tab-page search-page" @scroll.passive="rememberScroll">
    <AppHeader title="搜索" />
    <button v-if="sourceSeries" class="text-button return-series" @click="returnToSeries">← 返回系列</button>
    <form class="search-form" @submit.prevent="search(false, false, true)">
      <div class="search-input-row"><input v-model="keyword" aria-label="搜索关键词" placeholder="搜索标题、作者、分类或标签" maxlength="200" required /><button class="text-button" type="submit">搜索</button></div>

    </form>
    <p v-if="error" class="form-message" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">正在搜索…</p>
    <div v-if="searched" class="search-result-toolbar"><p class="search-count">{{ total ? `找到 ${total} 个系列` : loading ? '正在查询' : '没有找到相关系列' }}</p><button class="text-button" :disabled="loading" @click="toggleOrder">{{ order === 'desc' ? '从新到旧 ↓' : '从旧到新 ↑' }}</button></div>
    <div class="search-results">
      <a v-for="item in results" :key="item.id" class="book-link" :href="`#/series/${encodeURIComponent(item.id)}`"><div class="series-cover"><img v-if="!failed.has(item.id)" :src="item.thumbnailUrl" :alt="item.title" loading="lazy" @error="failed.add(item.id)" /><span v-else>暂无封面</span></div><h3>{{ item.title }}</h3><p class="search-card-meta"><span>{{ item.booksCount }} 章</span><time v-if="item.lastReleaseDate" :datetime="item.lastReleaseDate" title="最后一章发行日期">{{ item.lastReleaseDate }}</time><span v-else>日期未知</span></p></a>
    </div>
    <button v-if="results.length && !last" class="text-button load-more" :disabled="loading" @click="search(true)">加载更多</button>
  </main>
</template>
