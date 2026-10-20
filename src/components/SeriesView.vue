<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getJson } from '../api/library'
const props = defineProps<{ seriesId: string }>()
interface Series { title: string; summary: string; publisher: string; booksCount: number; thumbnailUrl: string }
interface Book { id: string; title: string; pagesCount: number; thumbnailUrl: string }
const series = ref<Series | null>(null)
const books = ref<Book[]>([])
const error = ref('')
const loading = ref(false)
const last = ref(false)
const page = ref(0)
const failed = ref(new Set<string>())
async function loadBooks() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const data = await getJson<{ items: Book[]; last: boolean }>(`/api/series/${encodeURIComponent(props.seriesId)}/books?page=${page.value}`)
    books.value.push(...data.items)
    last.value = data.last
    page.value++
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '书籍加载失败' }
  finally { loading.value = false }
}
async function load() {
  error.value = ''
  try {
    series.value = await getJson<Series>(`/api/series/${encodeURIComponent(props.seriesId)}`)
    await loadBooks()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '系列加载失败' }
}
onMounted(load)
</script>

<template>
  <main class="detail-page">
    <header class="detail-header"><a class="text-button" href="#/">返回首页</a><span>系列详情</span></header>
    <p v-if="error" class="form-message" role="alert">{{ error }} <button class="text-button" @click="series ? loadBooks() : load()">重试</button></p>
    <p v-if="!series && !error" role="status">正在加载…</p>
    <template v-if="series">
      <section class="series-info">
        <img v-if="!failed.has('series')" :src="series.thumbnailUrl" :alt="series.title" @error="failed.add('series')" />
        <div><h1>{{ series.title }}</h1><p>{{ series.booksCount }} 篇<span v-if="series.publisher"> · {{ series.publisher }}</span></p><p v-if="series.summary" class="series-summary">{{ series.summary }}</p></div>
      </section>
      <h2>书籍</h2>
      <div class="book-grid">
        <a v-for="book in books" :key="book.id" class="book-link" :href="`#/books/${encodeURIComponent(book.id)}`">
          <div class="series-cover"><img v-if="!failed.has(book.id)" :src="book.thumbnailUrl" :alt="book.title + '封面'" loading="lazy" @error="failed.add(book.id)" /><span v-else>暂无封面</span></div>
          <h3>{{ book.title }}</h3><p>{{ book.pagesCount }} 页</p>
        </a>
      </div>
      <p v-if="!books.length && last">暂无书籍</p>
      <button v-if="!last" class="text-button load-more" :disabled="loading" @click="loadBooks">{{ loading ? '加载中…' : '加载更多' }}</button>
    </template>
  </main>
</template>
