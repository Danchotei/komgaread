<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import LoginView from './components/LoginView.vue'
import BottomNav from './components/BottomNav.vue'
import PageView from './components/PageView.vue'
import SetupView from './components/SetupView.vue'
import { authRequest, type User } from './api/auth'
import { setupRequest, type SetupStatus } from './api/setup'
import { resetSearchState } from './searchState'

const hash = ref(window.location.hash)
const tabTransition = ref('page-static')
const mainTabs = ['#/', '#/categories', '#/me']
const pageStage = ref<HTMLElement | null>(null)
const stageHeight = ref<number | null>(null)

// 动画期间固定布局高度，避免旧页面脱离文档流或内容加载导致容器塌缩。
function lockStageHeight() {
  stageHeight.value = Math.max(pageStage.value?.scrollHeight || 0, window.innerHeight)
}
function finishTransition() {
  stageHeight.value = null
  void nextTick(restoreScroll)
}

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
  lockStageHeight()
  transitioning = true
  const target = window.location.hash || '#/'
  const returning = backRequested
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
  // 点击系列封面弹出详情，返回时收起详情；搜索入口沿用同一套效果。
  if (target.startsWith('#/series/') && !returning) tabTransition.value = 'card-open'
  if (target === '#/search') tabTransition.value = 'card-open'
  if (hash.value.startsWith('#/series/') && returning) tabTransition.value = 'card-close'
  if (hash.value === '#/search' && (toLevel === 0 || returning)) tabTransition.value = 'card-close'

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
const setupStatus = ref<SetupStatus | null>(null)
const startupError = ref('')
const loggingOut = ref(false)
const message = ref('')

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

async function checkStartup() {
  checking.value = true
  startupError.value = ''
  try {
    setupStatus.value = await setupRequest<SetupStatus>()
    if (setupStatus.value.configured) {
      try { user.value = await authRequest<User>('me') }
      catch { user.value = null; resetSearchState() }
    }
  } catch (cause) {
    startupError.value = cause instanceof Error ? cause.message : '启动检查失败'
  } finally {
    checking.value = false
  }
}
onMounted(checkStartup)

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
  <div ref="pageStage" class="page-stage" :style="stageHeight === null ? undefined : { height: `${stageHeight}px`, overflow: 'clip' }">
    <main v-if="checking" class="login-page" role="status">正在检查服务状态…</main>
    <main v-else-if="startupError" class="login-page"><div class="login-container"><p class="form-message" role="alert">{{ startupError }}</p><button class="submit-button" @click="checkStartup">重试连接</button></div></main>
    <SetupView v-else-if="setupStatus && !setupStatus.configured" @configured="checkStartup" />
    <Transition v-else-if="user" :name="tabTransition" @after-enter="finishTransition" @enter-cancelled="finishTransition">
      <KeepAlive :key="generation">
        <PageView :key="currentPage.key" :page-hash="currentPage.hash" :user="user" :logging-out="loggingOut" :message="message" :can-back="pages.length > 1" @back="goBack" @logout="logout" />
      </KeepAlive>
    </Transition>
    <LoginView v-else @authenticated="handleLogin" />
  </div>
  <BottomNav v-if="user && !checking && !startupError && !route" :active="hash === '#/search' ? undefined : activeTab" @navigate="navigateRoot" />
</template>
