<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import LoginView from './components/LoginView.vue'
import HomeView from './components/HomeView.vue'
import SeriesView from './components/SeriesView.vue'
import ReaderView from './components/ReaderView.vue'
import BottomNav from './components/BottomNav.vue'
import SearchView from './components/SearchView.vue'
import { authRequest, type User } from './api/auth'
import { resetSearchState } from './searchState'

const hash = ref(window.location.hash)
const tabTransition = ref('page-static')
// 返回由页面层级决定，不再把浏览器历史中的阅读页当作系列的父页面。
// 0：主导航页面；1：系列详情；2：阅读器。
function pageLevel(value: string) {
  if (value.startsWith('#/books/')) return 2
  if (value.startsWith('#/series/')) return 1
  return 0
}
let parentTab = '#/'
try {
  const saved = sessionStorage.getItem('komgaread-parent-tab')
  if (saved && ['#/', '#/categories', '#/me'].includes(saved)) parentTab = saved
} catch { /* 存储不可用时回到主页。 */ }
function rememberTab(value: string) {
  if (!['#/', '#/categories', '#/me'].includes(value)) return
  parentTab = value
  try { sessionStorage.setItem('komgaread-parent-tab', value) } catch { /* 保留内存中的值。 */ }
}
rememberTab(hash.value || '#/')
function goBackFromSeries() {
  window.location.replace(parentTab)
}
function tabIndex(value: string) {
  return ['#/', '#/categories', '#/me'].indexOf(value || '#/')
}
function updateRoute() {
  const fromLevel = pageLevel(hash.value)
  const toLevel = pageLevel(window.location.hash)
  const from = tabIndex(hash.value)
  const to = tabIndex(window.location.hash)
  // 索引增大：向左滑动；索引减小：向右滑动。
  tabTransition.value = from >= 0 && to >= 0 && from !== to
    ? (to > from ? 'tab-slide-left' : 'tab-slide-right')
    : 'page-static'
  if (fromLevel > toLevel) tabTransition.value = 'series-back'
  rememberTab(window.location.hash)
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

function handleLogin(authenticatedUser: User) {
  resetSearchState()
  // 主动登录成功始终进入首页，不沿用登录前残留的详情／阅读地址。
  window.history.replaceState(null, '', '#/')
  hash.value = '#/'
  tabTransition.value = 'page-static'
  rememberTab('#/')
  window.scrollTo(0, 0)
  user.value = authenticatedUser
}

onMounted(async () => {
  try {
    user.value = await authRequest<User>('me')
  } catch {
    // 没有有效会话时显示登录表单，提交时再显示具体连接错误。
    user.value = null
    resetSearchState()
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
    resetSearchState()
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
  <SearchView v-else-if="user && activeTab === 'categories'" />
  <main v-else-if="user && activeTab === 'me'" :key="activeTab" class="tab-page">
    <h1>我</h1>

    <p class="account-email">{{ user.email }}</p>
    <button class="text-button" :disabled="loggingOut" @click="logout">{{ loggingOut ? '正在退出…' : '退出登录' }}</button>
    <p v-if="message" role="alert">{{ message }}</p>
  </main>
  <HomeView v-else-if="user" />
  <LoginView v-else @authenticated="handleLogin" />
  </Transition>
  </div>
  <BottomNav v-if="user && !checking && !route" :active="activeTab" />
</template>
