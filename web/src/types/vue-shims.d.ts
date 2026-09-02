/**
 * Vue 单文件组件类型声明
 * Type declarations for Vue Single File Components
 */
declare module '*.vue' {
  /** 从 Vue 导入组件定义类型 / Import component definition type from Vue */
  import type { DefineComponent } from 'vue'
  /** Vue 组件实例 / Vue component instance */
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>
  /** 默认导出 Vue 组件 / Default export Vue component */
  export default component
}
