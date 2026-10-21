<script setup lang="ts">
import { onActivated, onMounted, ref } from 'vue'
import { getJson } from '../api/library'

const props = defineProps<{ seriesId: string }>()
interface Reactions { liked: boolean; favorited: boolean; likesCount: number; favoritesCount: number }
const state = ref<Reactions | null>(null)
const busy = ref(false)
const error = ref('')
const endpoint = () => `/api/series/${encodeURIComponent(props.seriesId)}/reactions`
async function load() {
  if (busy.value) return
  error.value = ''
  busy.value = true
  try { state.value = await getJson<Reactions>(endpoint()) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '加载失败，请重试' }
  finally { busy.value = false }
}
async function toggle(kind: 'like' | 'favorite') {
  if (busy.value || !state.value) return
  busy.value = true
  error.value = ''
  try {
    const response = await fetch(endpoint(), {
      method: 'PATCH', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind, selected: !(kind === 'like' ? state.value.liked : state.value.favorited) }),
    })
    const data = await response.json().catch(() => null)
    if (!response.ok || !data) throw new Error(typeof data?.detail === 'string' ? data.detail : '保存失败，请重试')
    state.value = data
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '保存失败，请重试' }
  finally { busy.value = false }
}
// 初次进入及从缓存返回时刷新，显示其他用户更新后的总数。
onMounted(load)
onActivated(load)
</script>

<template>
  <div class="series-reactions">
    <div class="reaction-buttons" aria-label="系列点赞和收藏" :aria-busy="busy">
      <button type="button" class="reaction-button" :class="{ 'is-selected': state?.liked }" :disabled="busy || !state" :aria-pressed="state?.liked ?? false" :aria-label="state?.liked ? '取消点赞' : '点赞'" @click="toggle('like')">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z" /></svg>
        <span>{{ state?.likesCount ?? '—' }}</span>
      </button>
      <button type="button" class="reaction-button" :class="{ 'is-selected': state?.favorited }" :disabled="busy || !state" :aria-pressed="state?.favorited ?? false" :aria-label="state?.favorited ? '取消收藏' : '收藏'" @click="toggle('favorite')">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-2.9-5.6 2.9 1.1-6.2L3 9.6l6.2-.9Z" /></svg>
        <span>{{ state?.favoritesCount ?? '—' }}</span>
      </button>
    </div>
    <p v-if="error" class="reaction-error" role="alert">{{ error }} <button class="text-button" :disabled="busy" @click="load">重试</button></p>
  </div>
</template>
