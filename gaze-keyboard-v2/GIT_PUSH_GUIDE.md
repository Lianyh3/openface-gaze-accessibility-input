# Git 提交与推送指南（gaze-keyboard-v2）

> 目标：将当前阶段成果（文档 + 代码骨架）稳定提交并推送。

## 1. 提交前检查

在仓库根目录执行：

```bash
git status
```

确认需要提交的范围包含：
- `gaze-keyboard-v2/` 下新增或修改文件

可选快速验证：

```bash
cd gaze-keyboard-v2/project
python scripts/smoke_test_pipeline.py
python scripts/smoke_test_runtime.py
```

---

## 2. 建议提交信息（首选）

```text
feat: scaffold realtime gaze keyboard v2 with ai suggestion pipeline
```

可选更细粒度（如果你准备拆分多次提交）：

1. `docs: add v2 solution and implementation status docs`
2. `feat: add realtime csv polling runtime and keyboard mvp`
3. `feat: add ai suggestion engine with codex client and fallback`

---

## 3. 提交命令（单次提交）

在仓库根目录执行：

```bash
git add gaze-keyboard-v2
git commit -m "feat: scaffold realtime gaze keyboard v2 with ai suggestion pipeline"
```

---

## 4. 推送命令

若当前分支尚未关联远端：

```bash
git push -u origin <your-branch-name>
```

若已关联：

```bash
git push
```

---

## 5. 推送后自检

1. 打开远端仓库确认文件完整；
2. 确认以下文档可见：
   - `gaze-keyboard-v2/README.md`
   - `gaze-keyboard-v2/AGENT.md`
   - `gaze-keyboard-v2/IMPLEMENTATION_STATUS.md`
   - `gaze-keyboard-v2/GIT_PUSH_GUIDE.md`
3. 在提交描述中注明：
   - 采用 B 方案（CSV 轮询）
   - MVP 闭环已可运行
   - AI 模块已接入且可降级

---

## 6. 注意事项

1. 不要提交 API Key；
2. 建议 `.gitignore` 排除 `logs/` 运行日志；
3. 若推送失败，优先检查远端权限与分支保护规则。
