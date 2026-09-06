---
name: git-push-github
description: 提交代码到 GitHub。当用户说"提交"、"push"、"commit"、"推上去"、"同步"时使用此 skill。本项目直接推 main 分支到 GitHub，不走 Gerrit。
---

# Git Push to GitHub

## 适用场景

本项目 (Shocking-VRChat) 直接推送到 GitHub main 分支，**不使用 Gerrit**。

触发词："提交"、"push"、"commit"、"推上去"、"同步到git"、"git push"

## 推送流程

```bash
# 1. 暂存文件（指定具体文件，不要用 git add .）
git add <files>

# 2. 提交（英文 commit message，conventional commit 格式）
git commit -m "<type>: <description>"

# 3. 推送到 GitHub
git push
```

三步连续执行，commit 后不要停下来问是否 push。

## Commit Message 格式

使用 conventional commits：

```
<type>: <short description>

<optional body>
```

### Type 选择

| Type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修复 bug |
| `refactor` | 重构（不改变行为） |
| `docs` | 文档更新 |
| `style` | 代码格式（不影响功能） |
| `perf` | 性能优化 |
| `test` | 测试相关 |
| `chore` | 构建/工具/依赖变更 |

### 规则

- **标题**：英文，70 字符以内，不加句号
- **正文**：可选，用于解释 why/what，英文
- **不要加** Change-Id（这不是 Gerrit）
- **不要加** GEN tag
- commit message 描述具体改了什么，不要写废话

### 示例

```
feat: add wave preview to mode config pages

Added WavePreview.vue component that renders preset waveform
with wave_scale and texture_floor applied. Integrated into
ModeShock, ModeDistance, ModeTouch pages.
```

```
fix: strength limit not pushed to device immediately
```

```
refactor: merge curve editor into distance mode page
```

## 暂存文件规则

- **指定具体文件**，不要用 `git add .` 或 `git add -A`
- 检查 `git status` 确认只提交相关文件
- 不要提交 `node_modules/`、`dist/`、`__pycache__/` 等
- `static/` 目录在 `.gitignore` 中，不需要提交

## 禁止操作

- ❌ `git push --force`
- ❌ `git reset --hard`
- ❌ `git push origin v*`（不要随便推 tag，除非用户明确说"发布"或"打 tag"）
- ❌ `git add .`（太危险）

## Tag / Release

**仅在用户明确要求时**才打 tag：

```bash
git tag -a v0.x.x -m "v0.x.x: description"
git push origin v0.x.x
```

用户会说"发布"、"打 tag"、"release" 等词。其他情况不要主动推 tag。

## 推送前检查

1. Python 编译通过：`python3 -c "import py_compile; py_compile.compile('shocking_vrchat.py', doraise=True)"`
2. 前端构建通过：`cd frontend && node node_modules/.bin/vue-tsc --noEmit && node node_modules/.bin/vite build`
3. 如果只改了后端，只需检查 Python 编译
4. 如果只改了前端，只需检查前端构建
