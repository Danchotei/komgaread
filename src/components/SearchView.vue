<script setup lang="ts">
import { nextTick, onActivated, onDeactivated, onBeforeUnmount, onMounted, ref } from 'vue'
import { searchState, type SearchSeries } from '../searchState'
const order = ref<'asc' | 'desc'>('desc')
const keyword = ref('')
defineProps<{ canBack?: boolean }>()
defineEmits<{ back: [] }>()
const results = ref<SearchSeries[]>([])
const total = ref(0)
const last = ref(true)
const loading = ref(false)
const searched = ref(false)
const hasLoadedMore = ref(false)
const awayFromTop = ref(false)
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
let disposed = false
let active = true
let activatedOnce = false
onActivated(async () => {
  active = true
  if (activatedOnce) {
    await nextTick()
    if (scrollContainer.value && Math.abs(scrollContainer.value.scrollTop - scrollPosition) > 1) {
      scrollContainer.value.scrollTop = scrollPosition
    }
  }
  activatedOnce = true
})
onDeactivated(() => { active = false })
function loadNearBottom() {
  const container = scrollContainer.value
  if (disposed || !active || !container || loading.value || error.value || !results.value.length || last.value) return
  if (container.scrollHeight - container.scrollTop - container.clientHeight < 320) void search(true)
}
function handleScroll() {
  rememberScroll()
  loadNearBottom()
}
function rememberScroll() {
  if (active && scrollContainer.value) {
    scrollPosition = scrollContainer.value.scrollTop
    awayFromTop.value = scrollPosition > 32
  }
}
onMounted(() => {
  const entry = searchState.pendingSearch
  searchState.pendingSearch = null
  if (entry) {
    keyword.value = entry.keyword
    filterType = entry.filterType || 'all'
    exact = entry.exact || false
    if (entry.keyword.trim()) void search()
  }
})
onBeforeUnmount(() => {
  disposed = true
  version++
  controller?.abort()
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
    hasLoadedMore.value = false
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
    if (more) hasLoadedMore.value = true
  } catch (cause) {
    if (current === version && !(cause instanceof DOMException && cause.name === 'AbortError')) error.value = cause instanceof Error ? cause.message : '搜索失败，请重试'
  } finally {
    if (current === version) {
      loading.value = false
      await nextTick()
      loadNearBottom()
    }
  }
}
async function toggleOrder() {
  if (loading.value) return
  order.value = order.value === 'desc' ? 'asc' : 'desc'
  const top = scrollContainer.value?.scrollTop || 0
  await search(false, true)
  await nextTick()
  if (scrollContainer.value) scrollContainer.value.scrollTop = top
}
</script>

<template>
  <main ref="scrollContainer" class="tab-page search-page" @scroll.passive="handleScroll">
    <button v-if="canBack" class="text-button return-series" @click="$emit('back')">← 返回</button>
    <form class="search-form" @submit.prevent="search(false, false, true)">
      <div class="search-input-row"><input v-model="keyword" aria-label="搜索关键词" placeholder="搜索标题、作者、分类或标签" maxlength="200" required /><button class="text-button" type="submit">搜索</button></div>
    </form>
    <p v-if="error" class="form-message" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">正在搜索…</p>
    <div v-if="searched" class="search-result-toolbar"><p class="search-count">{{ total ? `找到 ${total} 个系列` : loading ? '正在查询' : '没有找到相关系列' }}</p><button class="text-button" :disabled="loading" @click="toggleOrder">{{ order === 'desc' ? '从新到旧 ↓' : '从旧到新 ↑' }}</button></div>
    <div class="search-results">
      <a v-for="item in results" :key="item.id" class="book-link" :href="`#/series/${encodeURIComponent(item.id)}`"><div class="series-cover"><img v-if="!failed.has(item.id)" :src="item.thumbnailUrl" :alt="item.title" loading="lazy" @error="failed.add(item.id)" /><span v-else>暂无封面</span></div><h3>{{ item.title }}</h3><p class="search-card-genres" :title="item.genres?.join('、')">{{ item.genres?.join('、') || '暂无分类' }}</p><p class="search-card-meta"><span>{{ item.booksCount }} 章</span><time v-if="item.lastReleaseDate" :datetime="item.lastReleaseDate" title="最后一章发行日期">{{ item.lastReleaseDate }}</time><span v-else>日期未知</span></p></a>
    </div>
    <div v-if="results.length" class="search-load-status" role="status">
      <span v-if="loading">正在加载…</span>
      <button v-else-if="error && !last" class="text-button" @click="search(true)">重试加载</button>
      <span v-else-if="last">已显示全部结果</span>
    </div>
    <button v-if="hasLoadedMore && awayFromTop" class="search-back-top" aria-label="返回顶部" title="返回顶部" @click="scrollContainer?.scrollTo({ top: 0, behavior: 'smooth' })">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14M12 20V9m-5 5 5-5 5 5" /></svg>
    </button>
  </main>
</template>
