import { shallowRef } from 'vue'

// 临时排查 iOS 返回闪烁；普通访问不采集、不写入存储。
export const navigationDebugEnabled = new URLSearchParams(window.location.search).get('navdebug') === '1'
export const navigationDebugLines = shallowRef<string[]>([])

export function traceNavigation(event: string, detail: Record<string, unknown> = {}) {
  if (!navigationDebugEnabled) return
  const stage = document.querySelector<HTMLElement>('.page-stage')
  const pages = Array.from(stage?.querySelectorAll<HTMLElement>(':scope > .cached-page') || [])
  const data = {
    ms: Math.round(performance.now()), event,
    route: window.location.hash.split('/')[1] || 'home',
    viewport: Math.round(window.visualViewport?.height || window.innerHeight),
    innerHeight: window.innerHeight, y: Math.round(window.scrollY),
    stage: stage ? Math.round(stage.getBoundingClientRect().height) : null,
    locked: !!stage?.style.height,
    pages: pages.map(page => ({ height: Math.round(page.getBoundingClientRect().height), classes: page.className })),
    ...detail,
  }
  navigationDebugLines.value = [...navigationDebugLines.value.slice(-119), JSON.stringify(data)]
}
