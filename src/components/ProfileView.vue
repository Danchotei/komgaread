<script setup lang="ts">
import { nextTick, onActivated, onDeactivated, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import type { User } from '../api/auth'
import { getJson } from '../api/library'
import SeriesResultCard from './SeriesResultCard.vue'
import type { SeriesCardItem } from '../seriesState'

const props = defineProps<{ user: User; loggingOut: boolean; message: string }>()
defineEmits<{ logout: [] }>()
const displayName = ref(props.user.email)
const draftName = ref('')
const editingName = ref(false)
const profileBusy = ref(false)
const profileError = ref('')
const nameInput = ref<HTMLInputElement | null>(null)
async function loadProfile() {
  if (profileBusy.value) return
  profileBusy.value = true
  try {
    const data = await getJson<{ displayName: string }>('/api/me/profile')
    displayName.value = data.displayName
    profileError.value = ''
  } catch (cause) { profileError.value = cause instanceof Error ? cause.message : '用户名加载失败' }
  finally { profileBusy.value = false }
}
async function editName() {
  draftName.value = displayName.value
  editingName.value = true
  profileError.value = ''
  await nextTick()
  nameInput.value?.focus()
}
async function saveName() {
  if (profileBusy.value) return
  const name = draftName.value.trim()
  if (!name || [...name].length > 40) { profileError.value = '请输入 1–40 个字符的名字'; return }
  profileBusy.value = true
  profileError.value = ''
  try {
    const response = await fetch('/api/me/profile', { method: 'PATCH', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ display_name: name }) })
    const data = await response.json().catch(() => null)
    if (!response.ok || !data) throw new Error(typeof data?.detail === 'string' ? data.detail : '名字保存失败，请重试')
    displayName.value = data.displayName
    editingName.value = false
  } catch (cause) { profileError.value = cause instanceof Error ? cause.message : '名字保存失败，请重试' }
  finally { profileBusy.value = false }
}
type Kind = 'history' | 'favorites'
const selected = ref<Kind>('history')
const createList = () => ({ items: [] as SeriesCardItem[], page: 0, last: false, busy: false, error: '' })
const lists = reactive({ history: createList(), favorites: createList() })
const failed = reactive(new Set<string>())
const favoriteKeyword = ref('')
const appliedKeyword = ref('')
const versions = { history: 0, favorites: 0 }
let searchTimer: ReturnType<typeof setTimeout> | undefined
async function searchFavorites() {
  clearTimeout(searchTimer)
  const keyword = favoriteKeyword.value.trim()
  if (keyword.length > 200) return
  appliedKeyword.value = keyword
  await load('favorites', false, true)
}
watch(favoriteKeyword, () => {
  clearTimeout(searchTimer)
  // 输入一变化就让旧响应失效，避免防抖等待期间旧结果闪回。
  versions.favorites++
  lists.favorites.busy = true
  if (!favoriteKeyword.value.trim()) void searchFavorites()
  else searchTimer = setTimeout(() => { void searchFavorites() }, 300)
})
async function load(kind: Kind, more = false, reset = false) {
  const list = lists[kind]
  if (list.busy && !reset) return
  const version = ++versions[kind]
  const keyword = appliedKeyword.value
  list.busy = true
  list.error = ''
  try {
    // 从详情返回时保留已加载页数，一次替换列表，避免先清空造成高度跳变。
    const start = more ? list.page : 0
    const end = more ? start + 1 : reset ? 1 : Math.max(1, list.page)
    const items: SeriesCardItem[] = more ? [...list.items] : []
    let last = false
    let nextPage = start
    for (let page = start; page < end; page++) {
      const path = kind === 'favorites' && keyword
        ? `/api/search?favorites=true&q=${encodeURIComponent(keyword)}&page=${page}`
        : `/api/me/${kind}?page=${page}`
      const data = await getJson<{ items: SeriesCardItem[]; last: boolean }>(path)
      if (version !== versions[kind]) return
      items.push(...data.items)
      last = data.last
      nextPage = page + 1
      if (last) break
    }
    list.items = [...new Map(items.map(item => [item.id, item])).values()]
    list.page = nextPage
    list.last = last
  } catch (cause) {
    if (version === versions[kind]) list.error = cause instanceof Error ? cause.message : '加载失败，请重试'
  } finally { if (version === versions[kind]) list.busy = false }
}
function refresh() {
  void loadProfile()
  void load('history')
  if (appliedKeyword.value !== favoriteKeyword.value.trim()) void searchFavorites()
  else void load('favorites')
}
function stopPending() {
  clearTimeout(searchTimer)
  versions.history++
  versions.favorites++
  lists.history.busy = false
  lists.favorites.busy = false
}
onMounted(refresh)
onActivated(refresh)
onDeactivated(stopPending)
onUnmounted(stopPending)
</script>

<template>
  <main class="tab-page profile-page">
    <div class="profile-name-heading"><h1>{{ displayName }}</h1><button class="profile-name-edit" type="button" aria-label="修改用户名" title="修改用户名" :disabled="profileBusy || editingName" @click="editName"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 5 4 4M4 20l4-1 12-12a2.8 2.8 0 0 0-4-4L4 15Z" /></svg></button></div>
    <form v-if="editingName" class="profile-name-form" @submit.prevent="saveName"><label for="profile-name">用户名</label><div class="search-input-row"><input id="profile-name" ref="nameInput" v-model="draftName" required maxlength="40" autocomplete="nickname" :disabled="profileBusy" /><button class="text-button" type="submit" :disabled="profileBusy">{{ profileBusy ? '保存中…' : '保存' }}</button><button class="text-button" type="button" :disabled="profileBusy" @click="editingName = false; profileError = ''">取消</button></div></form>
    <p v-if="profileError" class="personal-hint" role="alert">{{ profileError }} <button v-if="!editingName" class="text-button" :disabled="profileBusy" @click="loadProfile">重试</button></p>
    <p class="account-email">{{ user.email }}</p>
    <button class="text-button" :disabled="loggingOut" @click="$emit('logout')">{{ loggingOut ? '正在退出…' : '退出登录' }}</button>
    <p v-if="message" role="alert">{{ message }}</p>
    <nav class="personal-tabs" aria-label="个人记录">
      <button class="personal-tab" :aria-pressed="selected === 'history'" @click="selected = 'history'">浏览记录</button>
      <button class="personal-tab" :aria-pressed="selected === 'favorites'" @click="selected = 'favorites'">我的收藏</button>
    </nav>
    <section v-for="kind in (['history', 'favorites'] as const)" v-show="selected === kind" :key="kind" :aria-label="kind === 'history' ? '浏览记录' : '我的收藏'" :aria-busy="lists[kind].busy">
      <form v-if="kind === 'favorites'" class="search-form" @submit.prevent="searchFavorites">
        <div class="search-input-row"><input v-model="favoriteKeyword" type="search" aria-label="搜索我的收藏" placeholder="输入关键词" maxlength="200" /><button v-if="favoriteKeyword" class="text-button" type="button" @click="favoriteKeyword = ''">清除</button></div>
      </form>
      <p class="personal-hint">{{ kind === 'history' ? '最近浏览的系列，最多保留 50 条' : '最近收藏的系列排在最前' }}</p>
      <p v-if="lists[kind].error" class="form-message" role="alert">{{ lists[kind].error }} <button class="text-button" :disabled="lists[kind].busy" @click="load(kind)">重试</button></p>
      <p v-if="!lists[kind].items.length && !lists[kind].error" class="empty-state">{{ lists[kind].busy ? '正在加载…' : kind === 'history' ? '暂无浏览记录' : appliedKeyword ? '收藏中没有匹配的系列' : '暂无收藏，点击系列详情中的星星即可收藏' }}</p>
      <div class="series-results">
        <SeriesResultCard v-for="item in lists[kind].items" :key="item.id" :item="item" :failed="failed.has(item.id)" @cover-error="failed.add(item.id)" />
      </div>
      <button v-if="lists[kind].page && !lists[kind].last" class="text-button load-more" :disabled="lists[kind].busy" @click="load(kind, true)">{{ lists[kind].busy ? '正在加载…' : '加载更多' }}</button>
    </section>
  </main>
</template>
