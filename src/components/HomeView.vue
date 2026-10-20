<script setup lang="ts">
import { onMounted, ref } from 'vue'

defineProps<{ loggingOut: boolean; logoutMessage: string }>()
defineEmits<{ logout: [] }>()

interface Series {
  id: string
  title: string
  booksCount: number
  thumbnailUrl: string
}

const series = ref<Series[]>([])
const loading = ref(false)
const error = ref('')
const failedCovers = ref<Set<string>>(new Set())
const recentSeries = ref<Series[]>([])
const recentLoading = ref(false)
const recentError = ref('')
const recentFailedCovers = ref<Set<string>>(new Set())

async function loadRecent() {
  recentLoading.value = true
  recentError.value = ''
  try {
    const response = await fetch('/api/series/recent', { credentials: 'same-origin' })
    if (!response.ok) {
      const detail = await response.json().catch(() => null)
      throw new Error(typeof detail?.detail === 'string' ? detail.detail : '最近添加加载失败')
    }
    recentSeries.value = await response.json() as Series[]
    recentFailedCovers.value = new Set()
  } catch (cause) {
    recentError.value = cause instanceof Error ? cause.message : '网络连接失败，请重试'
  } finally {
    recentLoading.value = false
  }
}

async function loadRecommendations() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const response = await fetch('/api/series/recommendations', { credentials: 'same-origin' })
    if (!response.ok) {
      const detail = await response.json().catch(() => null)
      throw new Error(typeof detail?.detail === 'string' ? detail.detail : '推荐加载失败，请稍后重试')
    }
    series.value = await response.json() as Series[]
    failedCovers.value = new Set()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '网络连接失败，请重试'
  } finally {
    loading.value = false
  }
}

onMounted(loadRecommendations)
onMounted(loadRecent)
</script>

<template>
  <div class="home-page">
    <header class="home-header">
      <a class="brand" href="./"><span class="brand-icon" aria-hidden="true">K</span>KomgaRead</a>
      <button class="text-button" :disabled="loggingOut" @click="$emit('logout')">{{ loggingOut ? '正在退出…' : '退出登录' }}</button>
    </header>
    <main>
      <p v-if="logoutMessage" role="alert">{{ logoutMessage }}</p>
      <section aria-labelledby="recent-title" :aria-busy="recentLoading">
        <div class="section-heading">
          <h2 id="recent-title">最近添加</h2>
          <button v-if="recentError" class="text-button" :disabled="recentLoading" @click="loadRecent">重试</button>
        </div>
        <p v-if="recentError" class="form-message" role="alert">{{ recentError }}</p>
        <p v-if="recentLoading" class="empty-state" role="status">正在加载…</p>
        <p v-else-if="!recentError && !recentSeries.length" class="empty-state">暂无系列</p>
        <div v-if="recentSeries.length" class="recent-series-row" tabindex="0" role="region" aria-label="最近添加的系列，可左右滚动">
          <article v-for="item in recentSeries" :key="item.id" class="series-card">
            <a class="series-cover cover-link" :href="`#/series/${encodeURIComponent(item.id)}`" :aria-label="`查看 ${item.title}`">
              <img v-if="!recentFailedCovers.has(item.id)" :src="item.thumbnailUrl" :alt="item.title + '封面'" loading="lazy" @error="recentFailedCovers.add(item.id)" />
              <span v-else class="cover-fallback">暂无封面</span>
            </a>
            <h3 :title="item.title">{{ item.title }}</h3>
            <p>{{ item.booksCount }} 篇</p>
          </article>
        </div>
      </section>
      <section aria-labelledby="recommendations-title" :aria-busy="loading">
        <div class="section-heading">
          <div>
            <h2 id="recommendations-title">随机推荐</h2>
          </div>
          <button class="text-button refresh-button" :disabled="loading" @click="loadRecommendations">{{ loading ? '加载中…' : '换一批' }}</button>
        </div>
        <p v-if="error" class="form-message" role="alert">{{ error }}</p>
        <p v-if="loading && !series.length" class="empty-state" role="status">正在从书库挑选漫画…</p>
        <p v-else-if="!error && !series.length" class="empty-state">还没有可推荐的漫画，请检查 Komga 书库和账号权限。</p>
        <div v-if="series.length" class="series-grid" tabindex="0" role="region" aria-label="随机推荐的系列，可左右滚动">
          <article v-for="item in series" :key="item.id" class="series-card">
            <a class="series-cover cover-link" :href="`#/series/${encodeURIComponent(item.id)}`" :aria-label="`查看 ${item.title}`">
              <img v-if="!failedCovers.has(item.id)" :src="item.thumbnailUrl" :alt="item.title + '封面'" loading="lazy" @error="failedCovers.add(item.id)" />
              <span v-else class="cover-fallback">暂无封面</span>
            </a>
            <h3 :title="item.title">{{ item.title }}</h3>
            <p>{{ item.booksCount }} 篇</p>
          </article>
        </div>
      </section>
    </main>
  </div>
</template>
