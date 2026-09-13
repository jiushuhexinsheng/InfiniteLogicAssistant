<template>
  <!-- 状态胶囊：贴在悬浮球内侧，把「双击唤醒 / 聆听中…」这类状态带到球边上。
       Status pill: sits on the ball's inner side, carrying copy such as
       "双击唤醒" / "聆听中…" right next to the ball. -->
  <div
    class="status-pill"
    :class="[`tail-${side}`, { hidden: !visible }]"
    :style="pillStyle"
    role="status"
    :aria-label="label"
  >
    <!-- 尖角：指向球心，让胶囊与球读作一个整体。Tail: points at the ball so the two read as one unit. -->
    <span class="sp-tail"></span>
    <!-- 声波条：只有麦克风在收音的状态才出现。Sound bars: only while the mic is live. -->
    <span v-if="showEq" class="sp-eq"><i></i><i></i><i></i><i></i></span>
    <!-- 状态圆点与图标：颜色取自状态视觉。Status dot and icon, coloured by the state visual. -->
    <span class="sp-dot"></span>
    <Icon :name="visual.icon" :size="13" class="sp-ico" />
    <span class="sp-text">{{ label }}</span>
  </div>
</template>

<script setup lang="ts">
/**
 * 状态胶囊组件：悬浮球收起时，助手状态显示在球旁边。
 * Status pill component: shows the assistant state beside the ball while the panel is collapsed.
 */
import { computed } from 'vue'
import Icon from '../Icon.vue'
import { resolveStateLabel } from '../../composables/useAssistantVisuals'
import type { StateVisual } from '../../composables/useAssistantVisuals'
import type { AsstState } from '../../composables/useAssistant'

/**
 * 组件属性定义。Component props definition.
 * @property visual - 状态对应的视觉配置（图标/文案/颜色）。Visual config for the state (icon/copy/colour).
 * @property state - 助手当前状态。Current assistant state.
 * @property wakeHint - 唤醒词提示文案（可多个），用于拼装聆听提示。Wake hint used in the listening copy.
 * @property visible - 是否显示；面板展开时为 false（面板头部已有状态显示）。
 *   Whether to show; false while the panel is expanded, since the panel header already shows the state.
 * @property side - 球所在的一侧，决定尖角朝哪边。Which side the ball is on, which sets the tail direction.
 */
const props = defineProps<{
  visual: StateVisual
  state: AsstState
  wakeHint: string
  visible: boolean
  side: 'left' | 'right'
}>()

/** 文案为空的状态在这里兜底：胶囊没有别的载体，空着就等于没有提示。
 *  States whose shared label is empty fall back here — the pill has no other surface, so an
 *  empty label would show nothing at all. */
const LABEL_FALLBACK: Partial<Record<AsstState, string>> = { responding: '回复中…' }

/** 需要声波条的状态：正在收音的三种。States that show sound bars (the mic is live). */
const EQ_STATES: AsstState[] = ['listening', 'recording', 'awaiting_answer']

/** 胶囊文案。Pill copy. */
const label = computed(() => resolveStateLabel(props.visual, props.wakeHint) || LABEL_FALLBACK[props.state] || '')

/** 是否显示声波条。Whether the sound bars are shown. */
const showEq = computed(() => EQ_STATES.includes(props.state))

/**
 * 把 #rgb / #rrggbb 转成带透明度的 rgba()，用于状态色描边与光晕。
 * Convert #rgb/#rrggbb into rgba() with alpha, for the state-coloured border and glow.
 * @param hex - 十六进制颜色。Hex colour.
 * @param alpha - 透明度（0~1）。Alpha from 0 to 1.
 * @returns rgba() 字符串；颜色无法解析时原样返回。An rgba() string, or the input when unparsable.
 */
function withAlpha(hex: string, alpha: number): string {
  const body = hex.replace('#', '')
  const full = body.length === 3 ? body.split('').map((c) => c + c).join('') : body
  if (full.length !== 6) return hex
  const n = parseInt(full, 16)
  if (Number.isNaN(n)) return hex
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
}

/** 胶囊样式：状态色以 CSS 变量注入，供描边/圆点/图标/声波条共用。
 *  Pill style: the state colour goes in as CSS variables, shared by the border, dot, icon and bars. */
const pillStyle = computed(() => ({
  '--sp-color': props.visual.color,
  '--sp-border': withAlpha(props.visual.color, 0.45),
  '--sp-glow': withAlpha(props.visual.color, 0.35),
}))
</script>

<style scoped>
/* 胶囊主体：玻璃底 + 状态色描边，尺寸与球的高光节奏保持一致。 */
.status-pill {
  position: relative;
  display: flex;
  align-items: center;
  gap: 7px;
  height: 32px;
  padding: 0 12px;
  border-radius: var(--r-full);
  background: var(--panel-bg);
  border: 1px solid var(--sp-border);
  backdrop-filter: blur(12px) saturate(140%);
  -webkit-backdrop-filter: blur(12px) saturate(140%);
  box-shadow: var(--shadow-2);
  white-space: nowrap;
  /* 纯展示：不吃鼠标事件，免得挡住球旁边的页面内容。Display only: never swallows pointer events. */
  pointer-events: none;
  transition: opacity var(--dur-base) var(--ease-out), transform var(--dur-base) var(--ease-out);
}
/* 面板展开：淡出让位（保留占位，球的位置不跳）。Expanded: fades out in place so the ball does not jump. */
.status-pill.hidden { opacity: 0; transform: translateY(4px); }

/* 尖角：8px 方块转 45°，只保留朝外的两条边。Tail: an 8px square rotated 45°, keeping only the outer edges. */
.sp-tail {
  position: absolute;
  width: 8px;
  height: 8px;
  background: var(--panel-bg);
  transform: rotate(45deg);
}
.status-pill.tail-right .sp-tail {
  right: -4px;
  top: 50%;
  margin-top: -4px;
  border-top: 1px solid var(--sp-border);
  border-right: 1px solid var(--sp-border);
}
.status-pill.tail-left .sp-tail {
  left: -4px;
  top: 50%;
  margin-top: -4px;
  border-bottom: 1px solid var(--sp-border);
  border-left: 1px solid var(--sp-border);
}

/* 状态圆点与图标。Status dot and icon. */
.sp-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--sp-color);
  box-shadow: 0 0 8px var(--sp-glow);
  flex: 0 0 7px;
}
.sp-ico { color: var(--sp-color); flex: 0 0 auto; }
.sp-text { font-size: var(--fs-xs); color: var(--text-1); }

/* 声波条：只在使用状态色，跟随胶囊呼吸。Sound bars, drawn in the state colour. */
.sp-eq {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  height: 14px;
  flex: 0 0 auto;
}
.sp-eq i {
  width: 3px;
  height: 5px;
  border-radius: 1px;
  background: var(--sp-color);
  animation: sp-eq 1s ease-in-out infinite;
}
.sp-eq i:nth-child(2) { animation-delay: 0.15s; }
.sp-eq i:nth-child(3) { animation-delay: 0.3s; }
.sp-eq i:nth-child(4) { animation-delay: 0.45s; }
@keyframes sp-eq {
  0%, 100% { height: 4px; }
  50% { height: 14px; }
}
</style>
