<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { getJson } from '../api/library'
const props = defineProps<{ seriesId: string }>()
defineEmits<{ back: [] }>()
interface Series { title: string; summary: string; publisher: string; booksCount: number; thumbnailUrl: string; authors: string[]; genres: string[]; tags: string[] }
interface Book { id: string; title: string; pagesCount: number; thumbnailUrl: string; readProgress: { page: number; completed: boolean } | null }
const series = ref<Series | null>(null)
const books = ref<Book[]>([])
const error = ref('')
const loading = ref(false)
const last = ref(false)
const page = ref(0)
const order = ref<'asc' | 'desc'>('asc')
async function changeOrder() {
  if (loading.value) return
  const nextOrder = order.value === 'asc' ? 'desc' : 'asc'
  loading.value = true
  error.value = ''
  try {
    // 加载期间保留原列表，避免页面高度骤减导致浏览器收回滚动位置。
    const data = await getJson<{ items: Book[]; last: boolean }>(`/api/series/${encodeURIComponent(props.seriesId)}/books?page=0&order=${nextOrder}`)
    const scrollY = window.scrollY
    books.value = data.items
    last.value = data.last
    page.value = 1
    order.value = nextOrder
    await nextTick()
    window.scrollTo({ top: scrollY, behavior: 'instant' })
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '排序失败，请重试' }
  finally { loading.value = false }
}
const failed = ref(new Set<string>())
async function loadBooks() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const data = await getJson<{ items: Book[]; last: boolean }>(`/api/series/${encodeURIComponent(props.seriesId)}/books?page=${page.value}&order=${order.value}`)
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
    <header class="detail-header"><button class="text-button" @click="$emit('back')">返回</button><span>系列详情</span></header>
    <p v-if="error" class="form-message" role="alert">{{ error }} <button class="text-button" @click="series ? loadBooks() : load()">重试</button></p>
    <p v-if="!series && !error" role="status">正在加载…</p>
    <template v-if="series">
      <section class="series-info">
        <img v-if="!failed.has('series')" :src="series.thumbnailUrl" :alt="series.title" @error="failed.add('series')" />
        <div v-else class="detail-cover-placeholder">暂无封面</div>
        <div class="series-description">
          <h1>{{ series.title }}</h1>
          <dl class="series-metadata">
            <div><dt>作者</dt><dd>{{ series.authors?.join('、') || '暂无' }}</dd></div>
            <div><dt>分类</dt><dd>{{ series.genres?.join('、') || '暂无' }}</dd></div>
            <div><dt>标签</dt><dd class="metadata-tags"><template v-if="series.tags?.length"><span v-for="tag in series.tags" :key="tag">{{ tag }}</span></template><template v-else>暂无</template></dd></div>
          </dl>
          <p v-if="series.summary" class="series-summary">{{ series.summary }}</p>
        </div>
      </section>
      <div class="books-toolbar"><h2 class="books-heading">书籍 <small>{{ series.booksCount }} 篇</small></h2><button class="text-button" :aria-label="order === 'asc' ? '当前序号升序，点击切换倒序' : '当前序号倒序，点击切换升序'" :disabled="loading" @click="changeOrder">{{ order === 'asc' ? '序号升序 ↑' : '序号倒序 ↓' }}</button></div>
      <div class="book-grid">
        <a v-for="book in books" :key="book.id" class="book-link" :href="`#/books/${encodeURIComponent(book.id)}`">
          <div class="series-cover"><img v-if="!failed.has(book.id)" :src="book.thumbnailUrl" :alt="book.title + '封面'" loading="lazy" @error="failed.add(book.id)" /><span v-else>暂无封面</span></div>
          <h3>{{ book.title }}</h3><p>{{ book.pagesCount }} 页</p><p class="book-progress">{{ book.readProgress?.completed ? '已读完' : book.readProgress && book.readProgress.page > 0 ? `读到第 ${book.readProgress.page} 页` : '未读' }}</p>
        </a>
      </div>
      <p v-if="!books.length && last">暂无书籍</p>
      <button v-if="!last" class="text-button load-more" :disabled="loading" @click="loadBooks">{{ loading ? '加载中…' : '加载更多' }}</button>
    </template>
  </main>
</template>
