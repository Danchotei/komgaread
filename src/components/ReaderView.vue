<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { getJson } from '../api/library'
const props = defineProps<{ bookId: string }>()
interface Book { title: string; seriesId: string; pagesCount: number }
const book = ref<Book | null>(null)
const page = ref(1)
const error = ref('')
const imageFailed = ref(false)
const imageLoading = ref(true)
const retry = ref(0)
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
  try { book.value = await getJson<Book>(`/api/books/${encodeURIComponent(props.bookId)}`) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '书籍加载失败' }
}
onMounted(() => { void load(); window.addEventListener('keydown', keydown) })
onUnmounted(() => window.removeEventListener('keydown', keydown))
</script>

<template>
  <main class="reader-page">
    <header class="reader-header">
      <a class="text-button" :href="book ? `#/series/${encodeURIComponent(book.seriesId)}` : '#/'">返回</a>
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
          <img v-else :key="pageUrl" :src="pageUrl" :alt="`第 ${page} 页`" class="reader-image" @load="imageLoading = false" @error="imageLoading = false; imageFailed = true" />
        </div>
        <nav class="reader-controls" aria-label="翻页">
          <button class="text-button" :disabled="page <= 1" @click="turn(-1)">上一页</button>
          <label class="page-picker">页码 <input v-model.number="page" type="range" min="1" :max="book.pagesCount" :aria-valuetext="`${page} / ${book.pagesCount}`" /><span>{{ page }} / {{ book.pagesCount }}</span></label>
          <button class="text-button" :disabled="page >= book.pagesCount" @click="turn(1)">下一页</button>
        </nav>
      </template>
    </template>
  </main>
</template>
