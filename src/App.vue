<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import LoginView from './components/LoginView.vue'
import HomeView from './components/HomeView.vue'
import SeriesView from './components/SeriesView.vue'
import ReaderView from './components/ReaderView.vue'
import BottomNav from './components/BottomNav.vue'
import { authRequest, type User } from './api/auth'

const hash = ref(window.location.hash)
const tabTransition = ref('page-static')
let historyIndex = Number(window.history.state?.komgaNavIndex) || 0
window.history.replaceState({ ...window.history.state, komgaNavIndex: historyIndex }, '')
let returningFromSeries = false
function goBackFromSeries() {
  returningFromSeries = true
  if (historyIndex > 0) window.history.back()
  else window.location.hash = '#/'
}
function tabIndex(value: string) {
  return ['#/', '#/categories', '#/me'].indexOf(value || '#/')
}
function updateRoute() {
  const nextIndex = window.history.state?.komgaNavIndex
  const goingBack = typeof nextIndex === 'number' && nextIndex < historyIndex
  const leavingSeries = hash.value.startsWith('#/series/')
  historyIndex = typeof nextIndex === 'number' ? nextIndex : historyIndex + 1
  window.history.replaceState({ ...window.history.state, komgaNavIndex: historyIndex }, '')
  const from = tabIndex(hash.value)
  const to = tabIndex(window.location.hash)
  // 索引增大：向左滑动；索引减小：向右滑动。
  tabTransition.value = from >= 0 && to >= 0 && from !== to
    ? (to > from ? 'tab-slide-left' : 'tab-slide-right')
    : 'page-static'
  if (leavingSeries && (returningFromSeries || goingBack)) tabTransition.value = 'series-back'
  returningFromSeries = false
  hash.value = window.location.hash
  window.scrollTo(0, 0)
}
window.addEventListener('hashchange', updateRoute)
onUnmounted(() => window.removeEventListener('hashchange', updateRoute))
const route = computed(() => {
  const match = hash.value.match(/^#\/(series|books)\/([^/]+)$/)
  try { return match ? { type: match[1], id: decodeURIComponent(match[2]!) } : null }
  catch { return null }
})
const activeTab = computed(() => hash.value === '#/categories' ? 'categories' : hash.value === '#/me' ? 'me' : 'home')
const user = ref<User | null>(null)
const checking = ref(true)
const loggingOut = ref(false)
const message = ref('')

onMounted(async () => {
  try {
    user.value = await authRequest<User>('me')
  } catch {
    // 没有有效会话时显示登录表单，提交时再显示具体连接错误。
    user.value = null
  } finally {
    checking.value = false
  }
})

async function logout() {
  loggingOut.value = true
  message.value = ''
  try {
    await authRequest<void>('logout', {})
    user.value = null
  } catch (error) {
    message.value = error instanceof Error ? error.message : '退出失败，请重试'
  } finally {
    loggingOut.value = false
  }
}
</script>

<template>
  <div class="page-stage">
  <Transition :name="user && !checking ? (tabTransition === 'series-back' ? 'series-back' : route?.type === 'series' ? 'series-slide' : tabTransition) : 'page-static'">
  <main v-if="checking" class="login-page" role="status">正在检查登录状态…</main>
  <SeriesView v-else-if="user && route?.type === 'series'" :key="route.id" :series-id="route.id" @back="goBackFromSeries" />
  <ReaderView v-else-if="user && route?.type === 'books'" :key="route.id" :book-id="route.id" />
  <main v-else-if="user && activeTab !== 'home'" :key="activeTab" class="tab-page">
    <h1>{{ activeTab === 'categories' ? '分类' : '我' }}</h1>
    <p v-if="activeTab === 'categories'" class="intro">分类功能即将加入。</p>
    <template v-else>
      <p class="account-email">{{ user.email }}</p>
      <button class="text-button" :disabled="loggingOut" @click="logout">{{ loggingOut ? '正在退出…' : '退出登录' }}</button>
      <p v-if="message" role="alert">{{ message }}</p>
    </template>
  </main>
  <HomeView v-else-if="user" :logging-out="loggingOut" :logout-message="message" @logout="logout" />
  <LoginView v-else @authenticated="user = $event" />
  </Transition>
  </div>
  <BottomNav v-if="user && !checking && !route" :active="activeTab" />
</template>
