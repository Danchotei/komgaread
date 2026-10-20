<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import LoginView from './components/LoginView.vue'
import BottomNav from './components/BottomNav.vue'
import PageView from './components/PageView.vue'
import { authRequest, type User } from './api/auth'
import { resetSearchState } from './searchState'

const hash = ref(window.location.hash)
const tabTransition = ref('page-static')
const mainTabs = ['#/', '#/categories', '#/me']

// 层级只选择动画方向；返回目标由下面的站内页面栈决定。
function pageLevel(value: string) {
  if (value.startsWith('#/books/')) return 3
  if (value.startsWith('#/series/')) return 2
  if (value === '#/search') return 1
  return 0
}
let nextKey = 1
const generation = ref(0)
const pages = ref([{ key: nextKey++, hash: hash.value || '#/', scrollY: 0 }])
const currentPage = computed(() => pages.value[pages.value.length - 1]!)
let backRequested = false
let rootRequested = false
let transitioning = false
function recordScroll() {
  if (!transitioning && window.location.hash === hash.value) currentPage.value.scrollY = window.scrollY
}
function restoreScroll() {
  window.scrollTo({ top: currentPage.value.scrollY, behavior: 'instant' })
  transitioning = false
}
function goBack() {
  recordScroll()
  if (pages.value.length > 1) {
    backRequested = true
    window.location.hash = pages.value[pages.value.length - 2]!.hash
  } else navigateRoot('#/')
}
function navigateRoot(target: string) {
  resetSearchState()
  rootRequested = true
  if (target === hash.value) updateRoute()
  else window.location.hash = target
}
window.addEventListener('scroll', recordScroll, { passive: true })
window.addEventListener('app-back', goBack)
function tabIndex(value: string) {
  return mainTabs.indexOf(value || '#/')
}
function updateRoute() {
  transitioning = true
  const target = window.location.hash || '#/'
  if (rootRequested) {
    generation.value++
    pages.value = [{ key: nextKey++, hash: target, scrollY: 0 }]
  }
  else if (backRequested) pages.value.pop()
  else {
    pages.value.push({ key: nextKey++, hash: target, scrollY: 0 })
  }
  rootRequested = false
  backRequested = false
  const fromLevel = pageLevel(hash.value)
  const toLevel = pageLevel(target)
  const from = tabIndex(hash.value)
  const to = tabIndex(target)
  // 索引增大：向左滑动；索引减小：向右滑动。
  tabTransition.value = from >= 0 && to >= 0 && from !== to
    ? (to > from ? 'tab-slide-left' : 'tab-slide-right')
    : 'page-static'
  if (fromLevel > toLevel) tabTransition.value = 'series-back'
  else if (fromLevel < toLevel) tabTransition.value = 'series-slide'
  if (target === '#/search' && fromLevel === 0) tabTransition.value = 'search-down'
  if (hash.value === '#/search' && toLevel === 0) tabTransition.value = 'search-up'

  hash.value = target
  void nextTick(restoreScroll)
}
window.addEventListener('hashchange', updateRoute)
onUnmounted(() => {
  window.removeEventListener('scroll', recordScroll)
  window.removeEventListener('app-back', goBack)
  window.removeEventListener('hashchange', updateRoute)
})
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
const transitionName = computed(() => {
  if (!user.value || checking.value) return 'page-static'
  if (tabTransition.value === 'series-back') return 'series-back'
  if (route.value?.type === 'series') return 'series-slide'
  return tabTransition.value
})

function handleLogin(authenticatedUser: User) {
  resetSearchState()
  // 主动登录成功始终进入首页，不沿用登录前残留的详情／阅读地址。
  window.history.replaceState(null, '', '#/')
  hash.value = '#/'
  tabTransition.value = 'page-static'
  generation.value++
  pages.value = [{ key: nextKey++, hash: '#/', scrollY: 0 }]
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
    <main v-if="checking" class="login-page" role="status">正在检查登录状态…</main>
    <Transition v-else-if="user" :name="transitionName" @after-enter="restoreScroll">
      <KeepAlive :key="generation">
        <PageView :key="currentPage.key" :page-hash="currentPage.hash" :user="user" :logging-out="loggingOut" :message="message" :can-back="pages.length > 1" @back="goBack" @logout="logout" />
      </KeepAlive>
    </Transition>
    <LoginView v-else @authenticated="handleLogin" />
  </div>
  <BottomNav v-if="user && !checking && !route" :active="hash === '#/search' ? undefined : activeTab" @navigate="navigateRoot" />
</template>
