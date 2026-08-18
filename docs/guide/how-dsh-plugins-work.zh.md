# dsh 插件是怎么工作的

**读懂能力卡片所需的全部背景知识**

*[English](?doc=plugins&lang=en) · 面向刚接触 DeepSeek Harness 的人*

---

## 一句话版本

dsh 的设计信条是"一切皆插件"。它基于 Cordis 框架:插件往一个共享的**上下文对象 `ctx`** 上注册服务、监听事件,而 dsh 自己的核心功能——会话、工具、LLM 适配——也都是用同一套机制写的插件。

这意味着:**插件和内核之间没有等级差**。你装的第三方插件,用的是和官方模块完全相同的接口。

---

## 插件长什么样

最小的插件就是一个导出 `apply` 函数的模块:

```ts
export const name = 'my-plugin'
export const inject = ['tools', 'sessions']   // 我需要这些服务

export function apply(ctx: Context) {
  ctx.tools.register(/* ... */)
  ctx.on('session/event', (e) => { /* ... */ })
}
```

三件事值得注意:

| 元素 | 作用 | 常被误解为 |
|---|---|---|
| `inject` | 声明依赖哪些服务,决定加载顺序 | ❌ 权限申请 |
| `ctx.xxx` | 按 key 拿到服务,不用 import | — |
| `ctx.on(...)` | 挂钩子,可以观察也可以改写 | — |

`inject` 是本文最重要的一点:它解决的是"谁先加载",**不是"允许你做什么"**。插件加载后能拿到它声明的全部服务,没有运行时强制边界。

---

## `ctx` 上都有什么

服务占据稳定的命名空间,插件按 key 发现彼此。常见的几个:

| 服务 | 能力 |
|---|---|
| `ctx.tools` | 注册工具、介入工具执行流水线 |
| `ctx.llm` | 模型适配器、流式响应 |
| `ctx.sessions` | 会话日志 |
| `ctx.systemPrompt` | 系统提示词的组装 |
| `ctx.apiProxy` | API 请求的代理层 |
| `ctx.subprocess` | 起子进程 |
| `ctx.approval` | 向用户征求确认 |
| `ctx.sandbox` | 沙箱后端(如 `dsh-bash-sandbox`) |

后面四个是我们在能力卡片里标为"强能力"的原因——它们分别对应:改写模型看到的东西、坐在你和模型之间、执行系统命令。

---

## 一次对话里发生了什么

```
turn/start → agent/pre-step → step/start → llm/stream → tool/call* → step/end → turn/end
```

一个 **step** 就是"一次模型请求 + 它调用的工具";一个 **turn** 包含零到多个 step。

事件分四种分发方式,差别很关键:

| 方式 | 行为 | 插件能做什么 |
|---|---|---|
| `emit` | 广播,不等待 | 只能观察 |
| `parallel` | 并发,等待全部完成 | 观察 + 异步副作用 |
| `serial` | 顺序执行,有返回值 | 可以影响结果 |
| `waterfall` | 中间件链,层层包裹 | **可以改写数据本身** |

`waterfall` 是插件能"改写"而不只是"旁观"的原因。挂在 `system-prompt/assemble` 上的插件,可以在提示词交给模型之前重写它——而你在界面上看到的对话内容不会有任何变化。

---

## 会话日志:模型看到的一切

dsh 有一条硬性不变量:**模型可见即已记录**。

会话日志是 append-only 的,`deriveMessages()` 从日志投影出模型看到的历史。想给模型多喂点东西,就必须往日志里加一条记录,没有绕过的路径。

这个设计很干净——它让"模型到底看到了什么"永远可审计。也正是因为有它,`system-prompt/assemble` 这类钩子才格外值得关注:它们是少数能在投影之外影响模型输入的地方。

---

## 权限:目前的真实状况

dsh **有**一套工具级的运行时批准机制:

```ts
ctx.on('tools/pre-execute', () => ({ kind: 'ask', reason: '...' }))
// 或 { kind: 'deny', reason: '...' }
```

插件可以拦住一次工具调用,让用户确认或直接拒绝。配合 `ctx.approval` 和 `ctx.sandbox`,工具执行这一层的把关是完整的。

**但插件安装这一层没有对应的东西。**

装一个插件时:

- manifest 里没有任何字段描述它要用什么能力
- 没有安装时的权限提示
- 没有运行时的能力边界强制
- `manifest.bundle.patch` 甚至允许它给 dsh 本体打补丁(`cordis.patch.yml`)

所以说"插件越权"是不成立的——没有可越的权限。工具调用被严格把关,而授予插件这一切能力的那一步,反而是无声的。

---

## 所以能力卡片在做什么

dsh-xray 静态扫描每个插件的发布代码,把上面这些东西列出来:它拿了哪些服务、挂了哪些钩子、是否打补丁、读哪些环境变量、有没有安装期脚本——每条都附代码行号。

这不能替代权限模型,只是在还没有权限模型的这段时间里,把信息摆到台面上。

- [能力等级 C0–C3 图解](levels.html)
- [生态报告:dsh 插件生态还没有权限模型](?doc=report)
- [插件注册表](registry.html)

*本文依据 dsh 官方文档(architecture、cordis-primer、capability-seams、extension-cookbook)与实际扫描结果写成。发现错误请[提 issue](https://github.com/unStone/dsh-xray/issues)。*
