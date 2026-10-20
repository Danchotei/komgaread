<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { getJson, saveProgress } from '../api/library'
const props = defineProps<{ bookId: string }>()
interface Book { title: string; seriesId: string; pagesCount: number; readProgress: { page: number; completed: boolean } | null }
const book = ref<Book | null>(null)
const page = ref(1)
const error = ref('')
const imageFailed = ref(false)
const imageLoading = ref(true)
const retry = ref(0)
const saveMessage = ref('')
const saveError = ref(false)
const returning = ref(false)
let latestSave: Promise<void> = Promise.resolve()
let saveVersion = 0
let displayedPage = 0
function persistPage() {
  if (!displayedPage) return
  const version = ++saveVersion
  saveError.value = false
  saveMessage.value = '正在保存…'
  latestSave = saveProgress(props.bookId, displayedPage)
  void latestSave.then(() => {
    if (version === saveVersion) saveMessage.value = '进度已保存'
  }).catch((cause) => {
    if (version === saveVersion) {
      saveError.value = true
      saveMessage.value = cause instanceof Error ? cause.message : '进度保存失败'
    }
  })
}
function imageLoaded(event: Event) {
  const image = event.target as HTMLImageElement
  const number = Number(image.dataset.page)
  if (number !== page.value) return
  imageLoading.value = false
  displayedPage = number
  persistPage()
}
async function goBack() {
  returning.value = true
  try {
    await latestSave
    window.location.hash = book.value ? `#/series/${encodeURIComponent(book.value.seriesId)}` : '#/'
  } catch {
    saveError.value = true
    saveMessage.value = '进度未保存，请重试；也可以使用浏览器返回离开'
  } finally { returning.value = false }
}
const pageUrl = computed(() => `/api/books/${encodeURIComponent(props.bookId)}/pages/${page.value}?retry=${retry.value}`)
function turn(delta: number) {
  if (book.value) page.value = Math.max(1, Math.min(book.value.pagesCount, page.value + delta))
}
function keydown(event: KeyboardEvent) {
  if (event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement) return
  if (event.key === 'ArrowRight') { event.preventDefault(); turn(1) }
  if (event.key === 'ArrowLeft') { event.preventDefault(); turn(-1) }
}
watch(page, () => { imageFailed.value = false; imageLoading.value = true })
async function load() {
  error.value = ''
  try {
    book.value = await getJson<Book>(`/api/books/${encodeURIComponent(props.bookId)}`)
    page.value = Math.max(1, Math.min(book.value.pagesCount || 1, book.value.readProgress?.page || 1))
  }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '书籍加载失败' }
}
onMounted(() => { void load(); window.addEventListener('keydown', keydown) })
onUnmounted(() => window.removeEventListener('keydown', keydown))
</script>

<template>
  <main class="reader-page">
    <header class="reader-header">
      <button class="text-button" :disabled="returning" @click="goBack">{{ returning ? '保存中…' : '返回' }}</button>
      <h1>{{ book?.title || '阅读器' }}</h1>
    </header>
    <p v-if="error" class="form-message" role="alert">{{ error }} <button class="text-button" @click="load">重试</button></p>
    <p v-if="!book && !error" role="status">正在加载书籍…</p>
    <template v-if="book">
      <p v-if="!book.pagesCount" class="empty-state">暂无可阅读页面，请检查 Komga 是否已完成分析。</p>
      <template v-else>
        <div class="reader-image-area" :aria-busy="imageLoading">
          <p v-if="imageLoading" class="reader-status" role="status">图片加载中…</p>
          <div v-if="imageFailed" class="empty-state" role="alert">页面加载失败，请检查网络或阅读权限。<button class="text-button" @click="imageFailed = false; imageLoading = true; retry++">重试</button></div>
          <img v-else :key="pageUrl" :src="pageUrl" :alt="`第 ${page} 页`" class="reader-image" :data-page="page" @load="imageLoaded" @error="imageLoading = false; imageFailed = true" />
        </div>
        <div class="progress-save-status" role="status">{{ saveMessage }} <button v-if="saveError" class="text-button" @click="persistPage">重试保存</button></div>
        <nav class="reader-controls" aria-label="翻页">
          <button class="text-button" :disabled="page <= 1" @click="turn(-1)">上一页</button>
          <label class="page-picker">页码 <input v-model.number="page" type="range" min="1" :max="book.pagesCount" :aria-valuetext="`${page} / ${book.pagesCount}`" /><span>{{ page }} / {{ book.pagesCount }}</span></label>
          <button class="text-button" :disabled="page >= book.pagesCount" @click="turn(1)">下一页</button>
        </nav>
      </template>
    </template>
  </main>
</template>
