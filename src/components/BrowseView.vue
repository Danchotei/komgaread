<script setup lang="ts">
import { computed, nextTick, onActivated, onDeactivated, onMounted, onUnmounted, ref } from 'vue'
import SeriesResultCard from './SeriesResultCard.vue'
import BackToTop from './BackToTop.vue'
import type { SeriesCardItem } from '../seriesState'

const props = defineProps<{ kind: 'latest' | 'random' | 'all' }>()
defineEmits<{ back: [] }>()
const title = computed(() => ({ latest: '最近更新', random: '随机本子', all: '浏览所有' })[props.kind])
const items = ref<SeriesCardItem[]>([])
const busy = ref(false)
const error = ref('')
const last = ref(false)
const container = ref<HTMLElement | null>(null)
const failed = ref(new Set<string>())
const hasLoadedMore = ref(false)
const awayFromTop = ref(false)
let page = 0
let scrollTop = 0
let active = true
let disposed = false
const controller = new AbortController()
async function load() {
  if (busy.value || last.value || disposed) return
  busy.value = true
  error.value = ''
  try {
    const response = await fetch(`/api/browse/${props.kind}?page=${page}`, { credentials: 'same-origin', signal: controller.signal })
    const data = await response.json()
    if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : '加载失败，请重试')
    if (disposed) return
    items.value = [...new Map([...items.value, ...data.items].map(item => [item.id, item])).values()]
    last.value = data.last
    if (page > 0) hasLoadedMore.value = true
    page++
  } catch (cause) { if (!disposed) error.value = cause instanceof Error ? cause.message : '加载失败，请重试' }
  finally { busy.value = false }
  await nextTick()
  nearBottom()
}
function nearBottom() {
  const element = container.value
  if (active && element && !error.value && items.value.length && element.scrollHeight - element.scrollTop - element.clientHeight < 320) void load()
}
function onScroll() { scrollTop = container.value?.scrollTop ?? 0; awayFromTop.value = scrollTop > 32; nearBottom() }
onMounted(load)
onActivated(async () => {
  active = true
  await nextTick()
  if (container.value && Math.abs(container.value.scrollTop - scrollTop) > 1) container.value.scrollTop = scrollTop
})
onDeactivated(() => { active = false })
onUnmounted(() => { disposed = true; controller.abort() })
</script>

<template>
  <main ref="container" class="tab-page browse-page" @scroll.passive="onScroll">
    <div class="browse-heading"><button class="text-button" @click="$emit('back')">← 返回</button><h1>{{ title }}</h1></div>
    <p class="personal-hint">{{ kind === 'latest' ? '按最后一章发行日期倒序，最多 30 个系列' : kind === 'random' ? '随机展示 12 个系列' : '按名称排列，下滑加载更多系列' }}</p>
    <div class="series-results">
      <SeriesResultCard v-for="item in items" :key="item.id" :item="item" :failed="failed.has(item.id)" @cover-error="failed.add(item.id)" />
    </div>
    <p v-if="error" class="form-message" role="alert">{{ error }} <button class="text-button" @click="load">重试</button></p>
    <p v-else class="search-load-status" role="status">{{ busy ? '正在加载…' : !items.length ? '暂无系列' : last ? '已显示全部结果' : '继续下滑加载更多' }}</p>
    <BackToTop v-if="kind === 'all' && hasLoadedMore && awayFromTop" :target="container" />
  </main>
</template>
