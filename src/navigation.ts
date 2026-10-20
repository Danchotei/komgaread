/** 只更新站内历史，不触发浏览器的默认 hash 片段导航或自动滚动。 */
export function navigateTo(target: string, replace = false) {
  if (target === (window.location.hash || '#/')) return
  if (replace) window.history.replaceState(null, '', target)
  else window.history.pushState(null, '', target)
  window.dispatchEvent(new CustomEvent('app-navigate', { detail: { replace } }))
}
