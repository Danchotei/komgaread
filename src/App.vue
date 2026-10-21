<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import LoginView from './components/LoginView.vue'
import BottomNav from './components/BottomNav.vue'
import PageView from './components/PageView.vue'
import SetupView from './components/SetupView.vue'
import AppHeader from './components/AppHeader.vue'
import { authRequest, type User } from './api/auth'
import { setupRequest, type SetupStatus } from './api/setup'
import { resetSearchState } from './searchState'
import { navigateTo } from './navigation'

const hash = ref(window.location.hash)
const tabTransition = ref('page-static')
const mainTabs = ['#/', '#/categories', '#/me']
const pageStage = ref<HTMLElement | null>(null)
const stageHeight = ref<number | null>(null)
let animatedNavigation = false
// 页面栈已保存滚动位置，避免浏览器再自动恢复一次导致跳动。
const previousScrollRestoration = window.history.scrollRestoration
window.history.scrollRestoration = 'manual'

// 动画期间固定布局高度，避免旧页面脱离文档流或内容加载导致容器塌缩。
function lockStageHeight() {
  stageHeight.value = Math.max(pageStage.value?.scrollHeight || 0, window.innerHeight)
}
function finishTransition() {
  if (!animatedNavigation) return
  animatedNavigation = false
  stageHeight.value = null
  void nextTick(restoreScroll)
}

// 层级只选择动画方向；返回目标由下面的站内页面栈决定。
function pageLevel(value: string) {
  if (value.startsWith('#/books/')) return 3
  if (value.startsWith('#/series/')) return 2
  if (value === '#/search' || value.startsWith('#/browse/')) return 1
  return 0
}
let nextKey = 1
const generation = ref(0)
const pages = ref([{ key: nextKey++, hash: hash.value || '#/', scrollY: 0 }])
type PageEntry = (typeof pages.value)[number]
const historySession = `${Date.now()}-${Math.random()}`
const savedPages = new Map<number, PageEntry>()
let historyTarget: PageEntry[] | null = null
function markHistory() {
  for (const page of pages.value) savedPages.set(page.key, page)
  // 只存页面标识，结果和滚动位置仍保留在站内内存中。
  window.history.replaceState({ ...window.history.state, komgaNavigation: {
    session: historySession, keys: pages.value.map(page => page.key),
  } }, '')
}
markHistory()
const currentPage = computed(() => pages.value[pages.value.length - 1]!)
let backRequested = false
let rootRequested = false
let transitioning = false
function recordScroll() {
  if (!transitioning && window.location.hash === hash.value) currentPage.value.scrollY = window.scrollY
}
function restoreScroll() {
  if (Math.abs(window.scrollY - currentPage.value.scrollY) > 1) {
    window.scrollTo({ top: currentPage.value.scrollY, behavior: 'instant' })
  }
  transitioning = false
}
function goBack() {
  if (backRequested) return
  recordScroll()
  if (pages.value.length > 1) {
    backRequested = true
    window.history.back()
  } else navigateRoot('#/')
}
function navigateRoot(target: string) {
  resetSearchState()
  rootRequested = true
  if (target === hash.value) updateRoute()
  else navigateTo(target)
}
function handlePageLink(event: MouseEvent) {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
  const link = event.target instanceof Element ? event.target.closest('a') : null
  const target = link?.getAttribute('href')
  if (!target?.startsWith('#/') || link?.hasAttribute('download') || (link?.target && link.target !== '_self')) return
  event.preventDefault()
  recordScroll()
  navigateTo(target)
}
window.addEventListener('scroll', recordScroll, { passive: true })
window.addEventListener('app-back', goBack)
function tabIndex(value: string) {
  return mainTabs.indexOf(value || '#/')
}
function updateRoute(event?: Event) {
  const target = window.location.hash || '#/'
  // 浏览器后退会先触发 popstate，再触发 hashchange；同一次导航只处理一次。
  if (target === (hash.value || '#/') && !rootRequested && !historyTarget) return
  const restoredPages = historyTarget
  historyTarget = null
  const browserNavigation = restoredPages !== null && !backRequested
  animatedNavigation = !browserNavigation
  if (animatedNavigation) lockStageHeight()
  else stageHeight.value = null
  transitioning = true
  const returning = backRequested || (restoredPages !== null && restoredPages.length < pages.value.length)
  if (rootRequested) {
    generation.value++
    savedPages.clear()
    pages.value = [{ key: nextKey++, hash: target, scrollY: 0 }]
  }
  else if (restoredPages) pages.value = restoredPages
  else if (event instanceof CustomEvent && event.detail?.replace) {
    pages.value.splice(-1, 1, { key: nextKey++, hash: target, scrollY: 0 })
  }
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
  if (target.startsWith('#/browse/') && !returning) tabTransition.value = 'card-open'
  if (hash.value.startsWith('#/series/') && returning) tabTransition.value = 'card-close'
  if (hash.value === '#/search' && (toLevel === 0 || returning)) tabTransition.value = 'card-close'
  if (hash.value.startsWith('#/browse/') && returning) tabTransition.value = 'card-close'
  // 系统返回手势／浏览器前后退已有原生过渡，不叠加网页动画。
  if (browserNavigation) tabTransition.value = 'page-static'

  hash.value = target
  // 已恢复的历史条目已有标识，无需重复写入。
  if (!restoredPages) markHistory()
  void nextTick(restoreScroll)
}
function handlePopState(event: PopStateEvent) {
  const state = event.state?.komgaNavigation
  if (!state || !Array.isArray(state.keys)) return
  const restored = state.session === historySession
    ? state.keys.map((key: number) => savedPages.get(key))
    : []
  if (restored.length && restored.every((page: PageEntry | undefined) => page)) {
    historyTarget = restored as PageEntry[]
  } else {
    // 底部导航或刷新已清除缓存时，仅打开目标页，不恢复过期的页面栈。
    generation.value++
    savedPages.clear()
    historyTarget = [{ key: nextKey++, hash: window.location.hash || '#/', scrollY: 0 }]
  }
  updateRoute()
}
window.addEventListener('popstate', handlePopState)
window.addEventListener('hashchange', updateRoute)
window.addEventListener('app-navigate', updateRoute)
// 阅读期间只保留一个章节历史条目，其前一个条目固定为所属系列。
function prepareReaderHistory(event: Event) {
  const { bookHash, seriesHash } = (event as CustomEvent<{ bookHash: string; seriesHash: string }>).detail
  if (hash.value !== bookHash) return
  if (pages.value[pages.value.length - 2]?.hash === seriesHash) return
  const reader = currentPage.value
  pages.value.splice(-1, 1, { key: nextKey++, hash: seriesHash, scrollY: 0 })
  window.history.replaceState(null, '', seriesHash)
  markHistory()
  pages.value.push(reader)
  window.history.pushState(null, '', bookHash)
  markHistory()
}
window.addEventListener('app-reader-ready', prepareReaderHistory)
onUnmounted(() => {
  window.history.scrollRestoration = previousScrollRestoration
  window.removeEventListener('scroll', recordScroll)
  window.removeEventListener('app-back', goBack)
  window.removeEventListener('hashchange', updateRoute)
  window.removeEventListener('app-navigate', updateRoute)
  window.removeEventListener('app-reader-ready', prepareReaderHistory)
  window.removeEventListener('popstate', handlePopState)
})
const route = computed(() => {
  const match = hash.value.match(/^#\/(series|books)\/([^/]+)$/)
  try { return match ? { type: match[1], id: decodeURIComponent(match[2]!) } : null }
  catch { return null }
})
const activeTab = computed(() => hash.value === '#/categories' || hash.value.startsWith('#/browse/') ? 'categories' : hash.value === '#/me' ? 'me' : 'home')
const user = ref<User | null>(null)
const checking = ref(true)
const setupStatus = ref<SetupStatus | null>(null)
const startupError = ref('')
const loggingOut = ref(false)
const message = ref('')
const showAppHeader = computed(() => !!user.value && !checking.value && !startupError.value && route.value?.type !== 'books')

function handleLogin(authenticatedUser: User) {
  resetSearchState()
  // 主动登录成功始终进入首页，不沿用登录前残留的详情／阅读地址。
  window.history.replaceState(null, '', '#/')
  hash.value = '#/'
  tabTransition.value = 'page-static'
  generation.value++
  pages.value = [{ key: nextKey++, hash: '#/', scrollY: 0 }]
  savedPages.clear()
  markHistory()
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
  <!-- 公共抬头位于过渡和页面缓存外，除阅读页外保持同一个实例。 -->
  <div v-if="showAppHeader" class="app-header-shell" @click="handlePageLink"><AppHeader /></div>
  <div ref="pageStage" class="page-stage" :class="{ 'has-app-header': showAppHeader }" :style="stageHeight === null ? undefined : { height: `${stageHeight}px`, overflow: 'clip' }" @click="handlePageLink">
    <main v-if="checking" class="login-page" role="status">正在检查服务状态…</main>
    <main v-else-if="startupError" class="login-page"><div class="login-container"><p class="form-message" role="alert">{{ startupError }}</p><button class="submit-button" @click="checkStartup">重试连接</button></div></main>
    <SetupView v-else-if="setupStatus && !setupStatus.configured" @configured="checkStartup" />
    <!-- 无动画导航必须关闭 CSS 过渡，不能仅使用没有样式的 page-static 名称。 -->
    <Transition v-else-if="user" :name="tabTransition" :css="tabTransition !== 'page-static'" @after-enter="finishTransition" @enter-cancelled="finishTransition">
      <KeepAlive :key="generation">
        <PageView :key="currentPage.key" :page-hash="currentPage.hash" :user="user" :logging-out="loggingOut" :message="message" :can-back="pages.length > 1" @back="goBack" @logout="logout" />
      </KeepAlive>
    </Transition>
    <LoginView v-else @authenticated="handleLogin" />
  </div>
  <BottomNav v-if="user && !checking && !startupError && !route" :active="hash === '#/search' ? undefined : activeTab" @navigate="navigateRoot" />
</template>
