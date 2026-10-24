/** 分组下拉的选项与分组类型。Grouped-select option and group types. */

/** 一个选项。One option. */
export interface GroupedOption {
  value: string
  label: string
  disabled?: boolean
}

/** 一组选项（组标题 + 选项）。One option group (header + options). */
export interface OptionGroup {
  label: string
  options: GroupedOption[]
}
