/**
 * 锚定弹层的共享行为 —— UiSelect 与 UiCombobox 此前各有一份逐行重复的实现。
 *
 * Shared behaviour of an anchored panel — UiSelect and UiCombobox each used to carry a
 * line-by-line duplicate of this.
 *
 * 覆盖：定位（下方空间不足上翻）、外点关闭、滚动关闭（含打开宽限期）、resize 关闭、
 * 键盘循环导航、全局监听随开随挂。**不**覆盖两者的领域逻辑 —— 选项从哪来、怎么过滤、
 * 选中意味着什么、键盘按键如何解释，那些留在各自组件里（它们的差异是刻意的）。
 *
 * Covers: positioning (flip up when short below), close-on-outside-pointerdown,
 * close-on-scroll (with the open grace period), close-on-resize, wrap-around keyboard
 * navigation, and attach-while-open global listeners. It deliberately does NOT cover either
 * component's domain logic — where options come from, how they filter, what picking means,
 * how keys are interpreted. Those stay in the components, because they differ on purpose.
 */
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

/** 面板与锚点之间的间距（px）。Gap between the panel and its anchor, in px. */
const GAP = 4

/** 面板最大高度（px）—— 与弹层 CSS 的 `max-height` 一致，参与上翻判定的空间预算。
 *  Panel max height in px — mirrors the panel CSS `max-height`; the space budget for the flip decision. */
const PANEL_MAX = 260

/** 打开后放行「非用户意图滚动」的宽限期（ms）。见 `onScroll` 的注释。
 *  Grace period (ms) after opening during which non-user-intent scrolls are ignored. See `onScroll`. */
const OPEN_GRACE_MS = 300

/** useAnchoredPanel 的依赖注入项：调用方必须提供的那几件事。
 *  What the caller must supply to useAnchoredPanel. */
export interface AnchoredPanelDeps {
  /** 锚点元素（触发器 / 输入框）；面板据此定位。Anchor element (trigger / input) the panel is positioned against. */
  anchor: () => HTMLElement | undefined | null
  /** 组件外层容器：用于「按下落在我身上」的判定。The component's outer wrapper (the "press landed on me" check). */
  wrap: () => HTMLElement | undefined | null
  /** 当前选项总数（键盘循环导航用）。Current option count (for wrap-around keyboard navigation). */
  count: () => number
  /** 面板 id 前缀；实例内补随机后缀保证唯一。Panel id prefix; a random suffix keeps it unique per instance. */
  idPrefix: string
}

/**
 * 建立锚定弹层的共享状态与操作。Set up the shared state and actions of an anchored panel.
 *
 * @param deps 依赖注入项。Injected dependencies.
 * @returns 状态（`open`/`flipUp`/`menuStyle`/`activeIndex`/`listId`）与操作（`show`/`close`/`place`/`move`/`scrollActive`）。
 *   State and actions.
 */
export function useAnchoredPanel(deps: AnchoredPanelDeps) {
  /** 面板唯一 id（每条选项的 id 也由它派生：`${listId}-${i}`）。Panel id; option ids derive from it. */
  const listId = `${deps.idPrefix}-${Math.random().toString(36).slice(2, 8)}`

  /** 面板开合。Panel open state. */
  const open = ref(false)
  /** 空间不足时向上翻转。Flip upward when space runs short. */
  const flipUp = ref(false)
  /** 面板定位样式（fixed，锚定锚点）。Panel position (fixed, anchored). */
  const menuStyle = ref<Record<string, string>>({})
  /** 键盘活动项索引。Keyboard-active option index. */
  const activeIndex = ref(0)
  /** 打开时刻（毫秒）：滚动宽限期的基准。Open timestamp (ms): the grace-period anchor. */
  let openedAt = 0

  /**
   * 取面板元素 —— 按 id 从 DOM 查。
   *
   * 面板由 `UiPopoverPanel` 渲染且**始终**带 `:id="listId"`，所以这里不必把它的 ref 回传给
   * 组合式（组件与组合式之间传 ref 会把「谁渲染面板」的耦合摊到两处，且要处理挂载前为空）。
   *
   * The panel element, resolved by id from the DOM. UiPopoverPanel always renders
   * `:id="listId"`, so no ref has to be threaded back from the component — which would spread
   * the "who renders the panel" coupling over two places and still return undefined pre-mount.
   *
   * @returns 面板元素（未渲染时为 null）。The panel element (null when not rendered).
   */
  function menuEl(): Element | null {
    return document.getElementById(listId)
  }

  /** 把键盘活动项滚进可视区（面板 max-height 可滚）。Scroll the keyboard-active item into view. */
  function scrollActive() {
    nextTick(() => {
      document.getElementById(`${listId}-${activeIndex.value}`)?.scrollIntoView?.({ block: 'nearest' })
    })
  }

  /**
   * 定位面板（锚定锚点；下方空间不足则上翻）。Position the panel (anchor; flip up when short below).
   */
  function place() {
    const el = deps.anchor()
    if (!el || typeof el.getBoundingClientRect !== 'function') return
    const r = el.getBoundingClientRect()
    const spaceBelow = window.innerHeight - r.bottom
    const spaceAbove = r.top
    flipUp.value = spaceBelow < Math.min(PANEL_MAX + 8, spaceAbove) && spaceAbove > spaceBelow
    menuStyle.value = {
      left: `${Math.round(r.left)}px`,
      width: `${Math.round(r.width)}px`,
      ...(flipUp.value
        ? { bottom: `${Math.round(window.innerHeight - r.top + GAP)}px` }
        : { top: `${Math.round(r.bottom + GAP)}px` }),
    }
  }

  /**
   * 打开面板并立即定位。Open the panel and position it right away.
   *
   * @param index 活动项初始索引。Initial active index.
   * @param scroll 是否把活动项滚进可视区 —— UiSelect 打开即定位选中项，UiCombobox 不滚。
   *   Whether to scroll the active item into view: UiSelect anchors on the selected item, UiCombobox does not.
   */
  function show(index: number, scroll = false) {
    open.value = true
    openedAt = performance.now()
    activeIndex.value = index
    place()
    if (scroll) scrollActive()
  }

  /** 关闭面板。Close the panel. */
  function close() {
    open.value = false
  }

  /**
   * 移动键盘活动项（带循环）。Move the keyboard-active item (wrap-around).
   *
   * @param d 步进方向（±1）。Step direction (±1).
   */
  function move(d: number) {
    const n = deps.count()
    if (!n) return
    activeIndex.value = (activeIndex.value + d + n) % n
    scrollActive()
  }

  /**
   * 外部指针按下关闭（面板挂在 body 下，不在组件树内，需单独判断）。
   * Close on outside pointerdown (the panel lives under body, not in the component tree).
   *
   * @param e 指针事件。Pointer event.
   */
  function onDocPointer(e: PointerEvent) {
    const t = e.target as Node
    if (deps.wrap()?.contains(t)) return
    if (menuEl()?.contains(t)) return
    close()
  }

  /**
   * 滚动关闭面板，但要排除两类「非用户意图」的滚动：
   *
   * 1. 面板自身滚动（max-height 可滚；打开时 scrollIntoView 定位选中项会触发）；
   * 2. **打开瞬间的焦点/连锁滚动** —— 浏览器为了让被点控件进入视口而微滚祖先容器
   *    （.console-settings 这类 overflow 容器），该滚动是异步分帧的，发生在监听挂载之后，
   *    不排除的话「点开即关」，且只在视口较满的页面（控制台）复现，极难排查。
   *
   * Closes on scroll but excludes two non-user-intent cases: (1) the panel's own scrolling
   * (scrollIntoView on open); (2) the *focus scroll* the browser performs right after opening
   * (asynchronously, after listeners attach) to bring the clicked control into view inside
   * overflow containers like .console-settings — without the grace period the panel closes the
   * instant it opens, only on fuller pages.
   *
   * @param e 滚动事件。Scroll event.
   */
  function onScroll(e: Event) {
    const t = e.target
    const menu = menuEl()
    // 面板内部滚动：放行。Scroll inside the panel: pass.
    if (menu && t instanceof Node && menu.contains(t)) return
    // 打开宽限期内的焦点/连锁滚动：放行。Focus/chain scrolls within the grace period: pass.
    if (performance.now() - openedAt < OPEN_GRACE_MS) return
    if (open.value) close()
  }

  /** 窗口缩放：锚点失效，直接关闭。Resize invalidates the anchor: close immediately. */
  function onResize() {
    if (open.value) close()
  }

  /** 摘除全局监听（关闭时与卸载时共用）。Detach the global listeners (shared by close and unmount). */
  function detach() {
    document.removeEventListener('pointerdown', onDocPointer)
    window.removeEventListener('scroll', onScroll, true)
    window.removeEventListener('resize', onResize)
  }

  onBeforeUnmount(detach)

  // 打开时挂全局监听，关闭时摘除（随开随挂）。Attach global listeners while open, detach when closed.
  watch(open, (v) => {
    if (v) {
      document.addEventListener('pointerdown', onDocPointer)
      window.addEventListener('scroll', onScroll, true)
      window.addEventListener('resize', onResize)
    } else {
      detach()
    }
  })

  return { open, flipUp, menuStyle, activeIndex, listId, place, show, close, move, scrollActive }
}
