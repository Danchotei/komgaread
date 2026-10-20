<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { getJson, saveProgress } from '../api/library'
const props = defineProps<{ bookId: string }>()
interface Book { title: string; seriesId: string; pagesCount: number; readProgress: { page: number; completed: boolean } | null }
const book = ref<Book | null>(null)
const page = ref(1)
const error = ref('')
const saveMessage = ref('')
const saveError = ref(false)
const returning = ref(false)
const failed = ref(new Set<number>())
const loaded = ref(new Set<number>())
const retries = ref<Record<number, number>>({})
const strip = ref<HTMLElement | null>(null)
const controlsVisible = ref(false)
let tapStart: { x: number; y: number; scrollY: number } | null = null
function startTap(event: PointerEvent) {
  tapStart = event.isPrimary ? { x: event.clientX, y: event.clientY, scrollY: window.scrollY } : null
}
function finishTap(event: PointerEvent) {
  const start = tapStart
  tapStart = null
  if (!start || !event.isPrimary || (event.target as HTMLElement).closest('button, a, input')) return
  if (Math.hypot(event.clientX - start.x, event.clientY - start.y) < 10 && Math.abs(window.scrollY - start.scrollY) < 10) {
    controlsVisible.value = !controlsVisible.value
  }
}
let observer: IntersectionObserver | undefined
const visible = new Map<number, HTMLElement>()
let frame = 0
let saveTimer: ReturnType<typeof setTimeout> | undefined
let latestSave: Promise<void> = Promise.resolve()
let saveVersion = 0
let displayedPage = 0
let lastQueuedPage = 0
let disposed = false

function persistPage(force = false) {
  if (!displayedPage || (!force && displayedPage === lastQueuedPage)) return
  const target = displayedPage
  lastQueuedPage = target
  const version = ++saveVersion
  saveError.value = false
  saveMessage.value = '正在保存…'
  latestSave = saveProgress(props.bookId, target)
  void latestSave.then(() => {
    if (version === saveVersion) saveMessage.value = '进度已保存'
  }).catch((cause) => {
    if (version === saveVersion) {
      lastQueuedPage = 0
      saveError.value = true
      saveMessage.value = cause instanceof Error ? cause.message : '进度保存失败'
    }
  })
}
function updateVisiblePage() {
  frame = 0
  const line = Math.min(window.innerHeight * 0.35, 240)
  const candidates = [...visible.entries()].filter(([number]) => loaded.value.has(number))
  const current = candidates.find(([, element]) => {
    const rect = element.getBoundingClientRect()
    return rect.top <= line && rect.bottom > line
  }) ?? candidates.filter(([, element]) => element.getBoundingClientRect().bottom > 64)
    .sort((a, b) => Math.abs(a[1].getBoundingClientRect().top - line) - Math.abs(b[1].getBoundingClientRect().top - line))[0]
  if (!current) return
  page.value = current[0]
  if (displayedPage === page.value) return
  displayedPage = page.value
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => persistPage(), 400)
}
function onScroll() { if (!frame) frame = requestAnimationFrame(updateVisiblePage) }
function imageLoaded(number: number) { loaded.value.add(number); onScroll() }
function retryImage(number: number) { failed.value.delete(number); retries.value[number] = (retries.value[number] || 0) + 1 }
function jumpToPage() {
  const element = strip.value?.querySelector<HTMLElement>(`[data-page="${page.value}"]`)
  element?.scrollIntoView({ block: 'start', behavior: 'instant' })
  onScroll()
}
async function goBack() {
  returning.value = true
  clearTimeout(saveTimer)
  updateVisiblePage()
  persistPage()
  try {
    await latestSave
    window.location.replace(book.value ? `#/series/${encodeURIComponent(book.value.seriesId)}` : '#/')
  } catch {
    saveError.value = true
    saveMessage.value = '进度未保存，请重试；也可以使用浏览器返回离开'
  } finally { returning.value = false }
}
async function load() {
  error.value = ''
  try {
    const data = await getJson<Book>(`/api/books/${encodeURIComponent(props.bookId)}`)
    if (disposed) return
    book.value = data
    page.value = Math.max(1, Math.min(data.pagesCount || 1, data.readProgress?.page || 1))
    await nextTick()
    if (disposed) return
    observer?.disconnect()
    visible.clear()
    observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        const element = entry.target as HTMLElement
        const number = Number(element.dataset.page)
        if (entry.isIntersecting) visible.set(number, element)
        else visible.delete(number)
      }
      onScroll()
    })
    strip.value?.querySelectorAll<HTMLElement>('[data-page]').forEach(element => observer?.observe(element))
    jumpToPage()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '书籍加载失败' }
}
function flushProgress() { clearTimeout(saveTimer); persistPage() }
function visibilityChanged() { if (document.hidden) flushProgress() }
onMounted(() => {
  void load()
  window.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('resize', onScroll)
  window.addEventListener('pagehide', flushProgress)
  document.addEventListener('visibilitychange', visibilityChanged)
})
onUnmounted(() => {
  disposed = true
  observer?.disconnect()
  cancelAnimationFrame(frame)
  flushProgress()
  window.removeEventListener('scroll', onScroll)
  window.removeEventListener('resize', onScroll)
  window.removeEventListener('pagehide', flushProgress)
  document.removeEventListener('visibilitychange', visibilityChanged)
})
</script>

<template>
  <main class="reader-page webtoon-reader">
    <Transition name="reader-toolbar-top">
    <header v-show="controlsVisible" class="reader-header">
      <button class="text-button" :disabled="returning" @click="goBack">{{ returning ? '保存中…' : '返回' }}</button>
      <h1>{{ book?.title || '阅读器' }}</h1>
    </header>
    </Transition>
    <p v-if="error" class="form-message" role="alert">{{ error }} <button class="text-button" @click="load">重试</button></p>
    <p v-if="!book && !error" role="status">正在加载书籍…</p>
    <template v-if="book">
      <p v-if="!book.pagesCount" class="empty-state">暂无可阅读页面，请检查 Komga 是否已完成分析。</p>
      <template v-else>
        <div ref="strip" class="webtoon-strip" tabindex="0" aria-label="漫画阅读区域，轻点或按空格显示或隐藏工具栏" @pointerdown="startTap" @pointerup="finishTap" @pointercancel="tapStart = null" @keydown.space.self.prevent="controlsVisible = !controlsVisible">
          <div v-for="number in book.pagesCount" :key="number" :data-page="number" class="webtoon-page" :class="{ 'is-loaded': loaded.has(number) }">
            <div v-if="failed.has(number)" class="webtoon-image-error" role="alert">第 {{ number }} 页加载失败<button class="text-button" @click="retryImage(number)">重试</button></div>
            <img v-else :key="`${number}-${retries[number] || 0}`" :src="`/api/books/${encodeURIComponent(bookId)}/pages/${number}?retry=${retries[number] || 0}`" :alt="`第 ${number} 页`" :loading="number === page ? 'eager' : 'lazy'" decoding="async" @load="imageLoaded(number)" @error="failed.add(number); loaded.delete(number)" />
          </div>
        </div>
        <Transition name="reader-toolbar-bottom">
        <nav v-show="controlsVisible" class="reader-controls" aria-label="阅读进度">
          <label class="page-picker">页码 <input v-model.number="page" type="range" min="1" :max="book.pagesCount" :aria-valuetext="`${page} / ${book.pagesCount}`" @change="jumpToPage" /><span>{{ page }} / {{ book.pagesCount }}</span></label>
          <span class="webtoon-save-status" role="status">{{ saveMessage }}</span>
          <button v-if="saveError" class="text-button" @click="persistPage(true)">重试保存</button>
        </nav>
        </Transition>
      </template>
    </template>
  </main>
</template>
