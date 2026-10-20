<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { User } from '../api/auth'

defineProps<{ user: User; loggingOut: boolean; logoutMessage: string }>()
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
</script>

<template>
  <div class="home-page">
    <header class="home-header">
      <a class="brand" href="./"><span class="brand-icon" aria-hidden="true">K</span>KomgaRead</a>
      <button class="text-button" :disabled="loggingOut" @click="$emit('logout')">{{ loggingOut ? '正在退出…' : '退出登录' }}</button>
    </header>
    <main>
      <div class="home-welcome">
        <p class="eyebrow">BJB的收藏库</p>
        <h1>今天，读点什么？</h1>
        <p class="intro account-email">欢迎回来，{{ user.email }}</p>
      </div>
      <p v-if="logoutMessage" role="alert">{{ logoutMessage }}</p>
      <section aria-labelledby="recommendations-title" :aria-busy="loading">
        <div class="section-heading">
          <div>
            <h2 id="recommendations-title">随机推荐</h2>
            <p>从你的书库里，发现下一个故事。</p>
          </div>
          <button class="text-button refresh-button" :disabled="loading" @click="loadRecommendations">{{ loading ? '加载中…' : '换一批' }}</button>
        </div>
        <p v-if="error" class="form-message" role="alert">{{ error }}</p>
        <p v-if="loading && !series.length" class="empty-state" role="status">正在从书库挑选漫画…</p>
        <p v-else-if="!error && !series.length" class="empty-state">还没有可推荐的漫画，请检查 Komga 书库和账号权限。</p>
        <div v-if="series.length" class="series-grid">
          <article v-for="item in series" :key="item.id" class="series-card">
            <div class="series-cover">
              <img v-if="!failedCovers.has(item.id)" :src="item.thumbnailUrl" :alt="item.title + '封面'" loading="lazy" @error="failedCovers.add(item.id)" />
              <span v-else class="cover-fallback">暂无封面</span>
            </div>
            <h3>{{ item.title }}</h3>
            <p>{{ item.booksCount }} 本</p>
          </article>
        </div>
      </section>
    </main>
  </div>
</template>
