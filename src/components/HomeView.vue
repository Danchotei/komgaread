<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import AppHeader from './AppHeader.vue'


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

// UTC+8 无夏令时；按中国日期边界更新，休眠恢复时也检查是否跨日。
const chinaDay = () => Math.floor((Date.now() + 8 * 3600000) / 86400000)
let loadedDay = chinaDay()
let midnightTimer: ReturnType<typeof setTimeout>
function scheduleUpdate() {
  const nextMidnight = (chinaDay() + 1) * 86400000 - 8 * 3600000
  midnightTimer = setTimeout(() => {
    loadedDay = chinaDay()
    void loadRecommendations()
    scheduleUpdate()
  }, nextMidnight - Date.now() + 100)
}
function checkDay() {
  if (!document.hidden && chinaDay() !== loadedDay) {
    loadedDay = chinaDay()
    void loadRecommendations()
  }
}
onMounted(() => {
  void loadRecommendations()
  scheduleUpdate()
  document.addEventListener('visibilitychange', checkDay)
})
onUnmounted(() => {
  clearTimeout(midnightTimer)
  document.removeEventListener('visibilitychange', checkDay)
})
onMounted(loadRecent)
</script>

<template>
  <div class="home-page">
    <AppHeader />
    <main>
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
            <h2 id="recommendations-title">每日推荐</h2>
          </div>
          <span class="daily-update-note">每日 00:00 更新 · 中国时间</span>
        </div>
        <p v-if="error" class="form-message" role="alert">{{ error }} <button class="text-button" :disabled="loading" @click="loadRecommendations">重试</button></p>
        <p v-if="loading && !series.length" class="empty-state" role="status">正在从书库挑选漫画…</p>
        <p v-else-if="!error && !series.length" class="empty-state">还没有可推荐的漫画，请检查 Komga 书库和账号权限。</p>
        <div v-if="series.length" class="series-grid" tabindex="0" role="region" aria-label="每日推荐的系列，可左右滚动">
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
