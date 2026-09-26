# 无限逻辑助手 Web 页面优化方案

## 📊 当前状态分析

### 设计审查发现的问题

| 优先级 | 问题 | 当前值 | 目标值 |
|--------|------|--------|--------|
| 🔴 高 | 导航按钮对比度不足 | 1.07:1 | ≥ 4.5:1 |
| 🔴 高 | 输入框焦点不可见 | outline:none | 需要 :focus-visible |
| 🔴 高 | 麦克风按钮太小 | 16×16px | ≥ 44×44px |
| 🔴 高 | 开关控件缺少可访问名称 | 无 | 需要 aria-label |
| 🟡 中 | 部分文字太小 | 10px | ≥ 12px |
| 🟡 中 | 页脚行高不足 | 1.2 | ≥ 1.5 |
| 🟢 低 | 标题层级跳级 | h1→h3 | h1→h2→h3 |
| 🟢 低 | 间距不统一 | 15种值 | 统一到4px网格 |
| 🟢 低 | 字号种类过多 | 9种 | ≤ 6-8种 |

---

## 🎨 优化方案

### 方案一：保持深色主题，优化可用性（推荐）

保持现有的赛博朋克深色风格，专注于修复可用性问题。

#### 1. 修复对比度问题

```css
/* 导航按钮 - 提高文字对比度 */
.ah-nav-item.active {
  color: var(--brand-c2); /* 使用亮青色 */
  background: rgba(103, 232, 249, .12);
}

/* 次要文字 - 提高可读性 */
.text-2 { color: #b0bec5; } /* 从 #94a3b8 提高到 #b0bec5 */
```

#### 2. 修复焦点可见性

```css
/* 所有交互元素添加焦点样式 */
.ui-input:focus-visible,
.ui-button:focus-visible,
.ui-toggle:focus-visible {
  outline: 2px solid var(--brand-c2);
  outline-offset: 2px;
}
```

#### 3. 增大点击目标

```css
/* 麦克风按钮增大到 44px */
.ball-mic {
  width: 44px;
  height: 44px;
  padding: 10px;
}

/* 所有按钮最小尺寸 */
.ui-button {
  min-height: 44px;
  min-width: 44px;
}
```

#### 4. 统一间距和字号

```css
/* 统一到 4px 网格 */
:root {
  --sp-1: 4px;
  --sp-2: 8px;
  --sp-3: 12px;
  --sp-4: 16px;
  --sp-5: 20px;  /* 从 24px 调整 */
  --sp-6: 24px;  /* 从 32px 调整 */
  --sp-7: 32px;  /* 从 48px 调整 */
  --sp-8: 48px;  /* 从 64px 调整 */
}

/* 精简字号阶梯 */
:root {
  --fs-xs: 12px;
  --fs-sm: 14px;  /* 合并 13px */
  --fs-md: 16px;  /* 合并 14px */
  --fs-lg: 18px;
  --fs-xl: 24px;  /* 从 20px 调整 */
  --fs-2xl: 32px;
  --fs-3xl: 48px;
}
```

#### 5. 修复页脚行高

```css
.page-footer {
  line-height: 1.5; /* 从 1.2 提高 */
  padding: 16px 0;  /* 增加上下间距 */
}
```

---

### 方案二：切换到浅色主题（可选）

如果想要更清爽的视觉效果，可以切换到浅色主题。

#### 浅色主题令牌

```css
:root {
  /* 浅色背景 */
  --bg-0: #f8fafc;
  --bg-1: #ffffff;
  --bg-2: #f1f5f9;
  --bg-3: #e2e8f0;
  
  /* 深色文字 */
  --text-1: #1e293b;
  --text-2: #475569;
  --text-3: #94a3b8;
  
  /* 保持品牌色 */
  --brand-c1: #6366f1;
  --brand-c2: #06b6d4;
  --brand-c3: #10b981;
}
```

---

## 📐 布局优化

### 响应式改进

```css
/* 移动端优化 */
@media (max-width: 768px) {
  .hero {
    padding: 24px 16px;
    gap: 16px;
  }
  
  .cards {
    flex-direction: column;
  }
  
  .features {
    grid-template-columns: 1fr;
  }
}

/* 桌面端优化 */
@media (min-width: 1024px) {
  .hero {
    padding: 48px 32px;
    gap: 24px;
  }
  
  .cards {
    max-width: 900px;
  }
}
```

---

## 🎯 具体修改清单

### 文件修改列表

| 文件 | 修改内容 |
|------|----------|
| `tokens.css` | 统一间距、字号、颜色 |
| `app.css` | 添加焦点样式、增大点击目标 |
| `StartPage.vue` | 修复标题层级、调整间距 |
| `AppHeader.vue` | 修复对比度、添加可访问名称 |
| `UiButton.vue` | 增大最小尺寸 |
| `UiInput.vue` | 添加焦点样式 |
| `UiToggle.vue` | 添加 aria-label |

---

## 📸 预期效果

### 修复前后对比

| 项目 | 修复前 | 修复后 |
|------|--------|--------|
| 对比度 | 1.07:1 (不可读) | 4.5:1+ (清晰) |
| 焦点指示 | 无 | 蓝色轮廓 |
| 按钮尺寸 | 16px (难点击) | 44px (易点击) |
| 间距一致性 | 15种值 | 统一4px网格 |
| 可访问性 | 缺少标签 | 完整ARIA |

---

## 🚀 实施步骤

1. **第一步**：更新 `tokens.css` - 统一设计令牌
2. **第二步**：更新 `app.css` - 添加通用样式修复
3. **第三步**：更新组件 - 逐个修复 Vue 组件
4. **第四步**：测试验证 - 运行设计审查确认修复

---

## ✅ 验收标准

- [ ] WCAG 对比度 ≥ 4.5:1
- [ ] 所有交互元素有焦点样式
- [ ] 点击目标 ≥ 44×44px
- [ ] 间距统一到 4px 网格
- [ ] 字号阶梯 ≤ 8 种
- [ ] 标题层级连续
- [ ] 所有控件有可访问名称
