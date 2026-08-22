# dsh-xray — DeepSeek Harness 插件能力卡片

**一个 dsh 插件声明了什么,它的代码实际在做什么——每条结论都附代码行号。**

[English](README.md) · 简体中文

[![scan](https://github.com/unStone/dsh-xray/actions/workflows/scan.yml/badge.svg)](https://github.com/unStone/dsh-xray/actions/workflows/scan.yml)
[![plugins scanned](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Funstone.github.io%2Fdsh-xray%2Fdata.json&query=%24.scanned&label=plugins%20scanned&color=blue)](https://unstone.github.io/dsh-xray/registry.html)
[![license](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

**[🔍 插件注册表](https://unstone.github.io/dsh-xray/registry.html?lang=zh)** ·
**[📊 生态报告](https://unstone.github.io/dsh-xray/report.html?lang=zh)** ·
**[📈 能力等级图解](https://unstone.github.io/dsh-xray/levels.html)** ·
**[📖 插件机制说明](https://unstone.github.io/dsh-xray/report.html?doc=plugins&lang=zh)**

> **90%** 的插件带强能力面 · **80%** 能给 dsh 运行时本体打补丁 · **9,476** 个插件已扫描,每日刷新

## 为什么做这个

`dsh-plugin` 生态在一个多月内从 200 个仓库涨到 **9,700 以上**。插件是跑在你 Agent 运行时里的任意代码:它可以改写你的系统提示词(`system-prompt/assemble`)、拦截每一次 API 调用(`api/gate`)、起子进程、读取环境变量里的 `GITHUB_TOKEN`,甚至**给运行时本体打补丁**(`manifest.bundle.patch`)。而今天,安装之前没有任何东西会告诉你这些。

dsh-xray 静态扫描生态里的每一个插件,为每个插件发布一张**能力卡片**:

| 维度 | 举例 |
|---|---|
| 声明面 | `manifest`、注入的服务、注册的工具、监听的钩子 |
| 强能力 | 注入 `systemPrompt` / `apiProxy` / `subprocess`、`tools/pre-execute` 闸门、运行时补丁 |
| 敏感行为 | 发布代码中的 `exec` / `eval` / base64 解码、安装期脚本、外联域名、凭证类环境变量读取 |
| 透明度缺口 | 代码里用到了、manifest 里却没有的能力 |

每条标志都附 **file:line 证据**。等级 **C0–C3** 衡量的是能力面大小与透明度,**不是**恶意判定。C3 插件完全可能是正当的——只是它碰你的 Agent 之前,你应当知情。

## 特性

- **全生态覆盖** —— `dsh-plugin` 标签下的每一个仓库(9,700+),每日重扫。
- **能力卡片** —— 注入的服务、挂载的钩子、运行时补丁、外联域名、凭证类环境变量、安装期脚本,每项附 `file:line` 证据。
- **C0–C3 等级** —— 一眼看出能力面多大,以及强能力是否与敏感行为并存。
- **区分发布代码与测试代码** —— 风险标志只在发布代码上触发,`tests/` 里的夹具不会虚增评级。
- **确定性 manifest 选取** —— monorepo 中取插件自身的根 manifest,同一仓库两次扫描结果一致。
- **纯静态分析** —— 不执行任何代码,下载的压缩包是流式读取的,从不运行。
- **可嵌入徽章** —— 插件作者可以公开自己的能力卡片。
- **三语站点** —— 英文、简体中文、日本語,外加每个插件一个可被搜索引擎抓取的页面。

## 能力等级

[![能力等级](https://unstone.github.io/dsh-xray/og.png)](https://unstone.github.io/dsh-xray/levels.html)

**C0** 无显著能力面 · **C1** 常规(注册工具/服务、外联域名) · **C2** 强能力:提示词面、API 拦截、子进程、exec、凭证读取或安装脚本 · **C3** 强能力与敏感行为并存。

等级衡量的是**能力面大小与透明度,不是恶意判定**。C3 插件完全可能是正当的——桌面外壳确实需要子进程。[图解在这里](https://unstone.github.io/dsh-xray/levels.html)。

## 在 dsh 内部直接用

[dsh-xray-plugin](https://github.com/unStone/dsh-xray-plugin) 把查询送到你决定要不要装它的那一刻:

```sh
dsh plugin add https://github.com/unStone/dsh-xray-plugin/releases/download/v0.1.0/dsh-xray-plugin-0.1.0.tgz
```

> `tt-a1i/archify` 装了安全吗?

> 审计一下我装的这些插件。

## 徽章

插件作者:把你的能力卡片亮出来。

```markdown
[![dsh-xray](https://img.shields.io/endpoint?url=https%3A%2F%2Funstone.github.io%2Fdsh-xray%2Fbadge%2F<owner>__<repo>.json)](https://unstone.github.io/dsh-xray/registry.html#<owner>__<repo>)
```

## 自己跑

```bash
python scanner/discover.py all          # 按 topic:dsh-plugin 枚举全生态(需 gh 登录)
cd scanner && python pipeline.py all 24 # 下载 + 扫描,不用 git clone
python render_report.py                 # 把最新数字注入报告
python render_pages.py                  # 生成插件页、聚合页、sitemap、feed
```

产物:`data/scans/*.json`(完整卡片)、`docs/data.json`(站点数据)、`docs/badge/*.json`(徽章端点)、`docs/p/*.html`(每插件页面)。每日 GitHub Action 自动刷新全部内容。

## 方法与规则

- 只做静态分析,不执行任何代码。
- 发布代码与测试/开发代码分开归类,风险标志只在发布代码上触发。
- 误报?[提 issue](https://github.com/unStone/dsh-xray/issues)——卡片附有证据,争议可核对,规则在公开处修正。

## 路线图

- [x] 全生态覆盖 —— 9,736 个仓库,每日重扫
- [x] 安装内可用的配套插件
- [ ] 每日差异推送:你在用的插件,能力面发生了什么变化
- [ ] `cordis.patch.yml` 运行时补丁审计视图
- [ ] 多 harness 支持(Abu-Cowork、Claude Code 插件格式)
- [ ] 私有注册表 / 组织策略引擎(企业版)

## 协议

Apache-2.0 —— 见 [LICENSE](LICENSE)。`data/` 与 `docs/` 下的扫描数据同样以该协议发布。

## 更新日志

[改了什么、为什么改](https://unstone.github.io/dsh-xray/report.html?doc=changelog&lang=zh) —— 只记录方法与产品的变化;扫描结果每日自动刷新。
