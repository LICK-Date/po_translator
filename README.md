# PO LLM Translator

[English](#english) | [中文说明](#中文说明)

---

<a id="english"></a>
## English

An industrial-grade, LLM-assisted localization tool specifically engineered for GNU gettext `.po` and `.pot` files. Built for game developers, software engineers, and professional localization teams who require deterministic safety, zero placeholder corruption, and crash-resilient throughput.

### 🌟 Key Features

- **Lossless & Safe PO I/O**:
  - High-fidelity roundtrip parsing based on `polib` (preserves header comments, developer notes, occurrences, flags, and plurals).
  - Atomic write mechanism (writes to temporary file, validates structure, creates `.bak` backup, then performs atomic file replacement).
- **Bulletproof Placeholder Engine**:
  - Automatically identifies and safeguards printf (`%s`, `%02d`), Python format (`{name}`, `{0}`), HTML/XML tags (`<b>`, `<a href="...">`), escape characters (`\n`, `\t`), and custom game variables (`${gold}`, `{{item}}`, `[PLAYER]`, `<HERO>`).
  - Strict bidirectional validation ensures no placeholders are missing, duplicated, or corrupted into translated strings (e.g. preventing `{username}` from becoming `{用户名}`).
- **OpenAI-Compatible Async Network Layer**:
  - Compatible with any standard OpenAI-compatible API (DeepSeek, OpenAI, Ollama, vLLM, OpenRouter, Groq, etc.).
  - Dual-track composite rate limiter (concurrency semaphore + 60s sliding window RPM throttle).
  - Exponential backoff retry with jitter for 429 and 5xx errors; immediate circuit breaking on 401/403 authorization failures.
- **Automated Quality Validation & Repair**:
  - Multi-stage deterministic validator chain (placeholder integrity, empty translation check, abnormal length ratio expansion).
  - Built-in lightweight repairer attempting targeted placeholder restoration before flagging for human review.
- **Intelligent Terminology & Glossary Engine**:
  - Hybrid term extractor combining CJK N-gram and English Title Case frequency analysis with stopword pruning.
  - LLM-assisted structured candidate filtering and automatic terminology alignment.
  - Strict priority hierarchy: `User Locked > Imported > Reviewed LLM > Auto Candidate`.
  - On-demand batch matching: only injects terms relevant to the current batch to minimize token overhead.
- **SQLite Persistence & Crash-Resilient Resume**:
  - High-performance SQLite database with Write-Ahead Logging (WAL) and foreign keys enabled.
  - Multi-dimensional SHA256 Translation Memory (TM) cache preventing duplicate LLM calls on identical strings.
  - Batch-level transaction checkpoints: interrupted jobs can be resumed immediately with 0 redundant re-translation costs.
- **Modern PySide6 Desktop GUI**:
  - Virtual-scrolling Model/View architecture capable of smoothly navigating 10,000+ entries.
  - Three-pane layout: searchable/filterable list on the left, context/source viewer on the top right, and manual translation editor with live saving on the bottom right.
  - Fully asynchronous `QThread` workers ensuring the user interface never freezes.
  - Visual glossary editor with one-click AI term discovery.
  - Secure settings modal with password masking and live connectivity verification.

---

### 🚀 Quick Start

#### Requirements
- Python **3.12+**
- Windows, macOS, or Linux

#### Installation
```bash
# Clone the repository
git clone https://github.com/your-username/TranslateAgent.git
cd TranslateAgent

# Install in editable mode
pip install -e .
```

---

### 💻 Command Line Interface (CLI)

#### 1. Analyze PO File Statistics
Inspect translation completion, fuzzy items, and total entries without modifying the file:
```bash
po-translator analyze path/to/messages.po
```

#### 2. Translate PO File
Translate an input `.po` or `.pot` file using any OpenAI-compatible provider:

```bash
# Using DeepSeek API
po-translator translate path/to/game.po \
    --source en \
    --target zh-CN \
    --base-url https://api.deepseek.com/v1 \
    --api-key sk-your-key-here \
    --model deepseek-chat \
    --mode quality \
    -o path/to/game.translated.po \
    --overwrite
```

#### CLI Arguments Reference:
- `file`: Path to the target `.po` or `.pot` file.
- `-s, --source`: Source language code (default: `en`).
- `-t, --target`: Target language code (default: `zh-CN`).
- `-o, --output`: Output file path (defaults to `<name>.translated.po`).
- `--base-url`: OpenAI-compatible API base URL (default: `https://api.openai.com/v1`).
- `--api-key`: API Key (can also be read from `OPENAI_API_KEY` environment variable).
- `--model`: Model identifier (default: `gpt-4o`).
- `--mode`: Pipeline mode (`fast`, `quality`, or `smart`).
- `--overwrite`: Allow overwriting an existing output file.

---

### 🖥️ Desktop GUI Application

Launch the desktop client with:
```bash
po-translator-gui
```

#### GUI Highlights:
1. **Open & Save**: Open any `.po` or `.pot` file via the menu or shortcut; save changes directly or export to a new file.
2. **Real-time Status Counters**: Track `Total | Translated | Cached | Review | Failed` dynamically in the status bar.
3. **Filtering & Search**:
   - Filter entries by status (`Pending`, `Translated`, `Review Required`, `Failed`, `Cached`, `Skipped`).
   - Real-time search across `msgid`, `msgstr`, context (`msgctxt`), and comments.
4. **Interactive Editor**: Inspect complete developer notes and occurrences; edit translations manually and click **Save Edit** to commit.
5. **Glossary Manager**: Open via **Glossary** to view, add, delete, import, lock terms, or click **Auto-Discover Terms via AI** to extract project keywords automatically.
6. **Settings**: Configure base URL, API key, model name, concurrency, and RPM limits. Click **Test Connection** to test network reachability securely.

---

### 🧪 Testing & Code Quality

The project comes with a comprehensive test suite (72 unit and integration tests) and strict Ruff linting compliance.

```bash
# Run static code analysis
ruff check src tests

# Run all test suites
pytest -v
```

---

<br/>

---

<a id="中文说明"></a>
## 中文说明

面向 GNU gettext `.po` 与 `.pot` 本地化文件的工业级大语言模型辅助翻译系统。专为游戏开发、软件研发及专业本地化交付场景设计，遵循“确定性处理由程序负责，语义判断由 LLM 负责”的工程原则。

### 🌟 核心特性

- **高保真与安全持久化（PO I/O）**：
  - 基于 `polib` 深度解析与重构，无损保留文件头注释、开发者注释（`#.`）、行号定位（`#:`）、Flags 标记、复数形态（`msgid_plural`）。
  - **原子写盘机制**：先写入临时文件，结构校验通过后自动生成 `.bak` 备份文件，最后执行操作系统级原子替换，杜绝断电或崩溃损坏源文件。
- **高精度占位符保护引擎（Placeholder Engine）**：
  - 自动识别并守护 printf（`%s`, `%02d`）、Python format（`{name}`, `{0}`）、HTML/XML 标签（`<b>`, `<a href="...">`）、转义字符（`\n`, `\t`）及自定义游戏变量（`${gold}`, `{{item}}`, `[PLAYER]`, `<HERO>`）。
  - 双向强一致校验：防止大模型遗漏、多译、篡改占位符变量名（如严防 `{username}` 被翻译为 `{用户名}`）。
- **OpenAI 兼容高可用异步网络层**：
  - 原生支持所有兼容 OpenAI 协议的模型提供商（DeepSeek、OpenAI、Ollama、vLLM、OpenRouter 等）。
  - **双轨复合限流器**：并发信号量与 60 秒滑动窗口请求频率（RPM）双轨限制。
  - 指数退避与抖动重试机制，自适应处理 429 与 5xx 网络瞬断；401/403 鉴权失败立即熔断，不浪费配额。
- **自动化质量校验网与轻量修复**：
  - 多阶段确定性校验链：占位符一致性校验、空译文拦截、异常长度膨胀率检查。
  - 内置轻量级修复引擎：译文存在轻微占位符瑕疵时自动修复，修复失败降级标记需人工复核。
- **智能术语库与上下文发现系统**：
  - 混合术语提取：支持 CJK N-gram 词频统计与英文 Title Case 提取，内置常见停用词清洗。
  - LLM 结构化筛选与自动对齐翻译。
  - 严格的不可篡改优先级：`用户锁定 > 导入术语 > 已审核 LLM 术语 > 算法候选`。
  - 按需动态注入：按批次提取相关术语注入提示词，大幅降低 Token 开销。
- **SQLite WAL 事务持久化与断点续译**：
  - 内置 SQLite 数据库，开启 Write-Ahead Logging（WAL）与外键约束。
  - 多维 SHA256 翻译记忆库（TM）：完全匹配的历史条目直接命中缓存跳过 LLM。
  - 批次级事务落盘：翻译意外中断后重新启动自动跳过已完成条目，零重复开销。
- **现代 PySide6 桌面 GUI 客户端**：
  - Qt Model/View 架构虚拟滚动，万级条目毫秒级顺滑渲染。
  - 三栏布局：左侧条目检索与状态筛选列表，右上侧原文与上下文查看，右下侧译文即时编辑与人工修正。
  - `QThread` 异步后台线程解耦，翻译过程中界面响应敏捷、绝不卡顿假死。
  - 可视化术语管理界面，支持一键“AI 自动提炼术语”。
  - 独立设置中心：密码掩码保护 API Key，免暴露一键连通性测试。

---

### 🚀 快速上手

#### 环境要求
- Python **3.12+**
- 操作系统：Windows / macOS / Linux

#### 安装步骤
```bash
# 克隆代码仓库
git clone https://github.com/your-username/TranslateAgent.git
cd TranslateAgent

# 推荐在虚拟环境中以开发模式安装
pip install -e .
```

---

### 💻 命令行使用说明（CLI）

安装完成后，系统自动注册 `po-translator` 命令行工具：

#### 1. 静态分析 PO 文件
快速查看条目总量、未翻译数、模糊词条数等：
```bash
po-translator analyze path/to/messages.po
```

#### 2. 执行自动翻译
指定翻译的语言、模型端点与 API 凭据：
```bash
# 以 DeepSeek 官方 API 为例
po-translator translate path/to/game.po \
    --source en \
    --target zh-CN \
    --base-url https://api.deepseek.com/v1 \
    --api-key sk-your-key-here \
    --model deepseek-chat \
    --mode quality \
    -o path/to/game.translated.po \
    --overwrite
```

#### 参数详解：
- `file`：待翻译的目标 `.po` 或 `.pot` 文件路径。
- `-s, --source`：源语言代码（默认：`en`）。
- `-t, --target`：目标语言代码（默认：`zh-CN`）。
- `-o, --output`：输出文件路径（默认为 `<原文件名>.translated.po`）。
- `--base-url`：OpenAI 兼容 API 端点（默认：`https://api.openai.com/v1`）。
- `--api-key`：API 密钥（未填时优先读取环境变量 `OPENAI_API_KEY`）。
- `--model`：调用的模型名称（默认：`gpt-4o`）。
- `--mode`：流水线模式（`fast`、`quality`、`smart`）。
- `--overwrite`：允许覆盖已存在的输出文件。

---

### 🖥️ 桌面图形界面（GUI）

终端执行以下命令直接拉起图形化客户端：
```bash
po-translator-gui
```

#### 桌面端功能指引：
1. **文件载入与保存**：点击菜单栏“File”->“Open PO File”载入文件；修改后点击“Save”或“Save As”安全导出。
2. **实时进度与统计**：底部状态栏实时呈现 `Total | Translated | Cached | Review | Failed` 各维度条目数统计。
3. **精准检索与过滤**：
   - 下拉菜单按状态快速过滤（待翻译、需审核、失败、已翻译等）。
   - 搜索框支持对原文、译文、上下文标识（`msgctxt`）及注释进行全局快速检索。
4. **人工审校与即时保存**：选中行后右侧展示完整提取注释与代码行号定位；支持在右下方文本框直接修改译文并点击“Save Edit”即时提交更新。
5. **术语可视化管理**：点击主界面“Glossary”弹窗管理项目术语，支持新增、编辑、锁定保护，或点击“Auto-Discover Terms via AI”让模型自动提炼全篇核心术语。
6. **参数设置与连通测试**：在“Settings”中配置 Base URL 与 Key，点击“Test Connection”实时检测服务可达性与鉴权状态。

---

### 🧪 测试套件与代码规范

项目内置完善的测试用例及严格的静态检查：

```bash
# 代码静态规范检测
ruff check src tests

# 执行全量自动化单元与集成测试（72 个用例）
pytest -v
```

---

### 📄 开源许可证

本项目基于 [MIT License](LICENSE) 开源发布。
