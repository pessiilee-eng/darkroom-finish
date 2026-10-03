# 本机操作

从本 Skill 目录运行命令；从其他工作目录调用时使用脚本的绝对路径。
以下路径是示意，必须替换为用户这次明确授权的实际文件与新工作区。

```bash
python3 -B scripts/darkroom.py doctor
python3 -B scripts/darkroom.py init --workspace /path/to/new-workspace
python3 -B scripts/darkroom.py ingest --workspace /path/to/new-workspace \
  --source /path/to/selected-photo.dng --authorization "用户关于这张照片本地修图的实际授权原文"
```

`ingest` 仅访问指定的一张原片，返回 `source_id`。原文件名不用于输出命名，
但原路径仍保存在私人工作区以便验证；不要把工作区提交或分享。

第一次先用 `examples/neutral.json` 做基线；有有效基线就复用，不重复占用次数。
编写单图 JSON，如 `{"exposure2012":"0.25","highlights2012":"-15"}`。
数值为无尾零的规范十进制字符串（`"0.5"`，不是 `"0.50"`）。白平衡枚举用 `AS_SHOT`；
不猜字段名，精确字段和范围在 `runtime/registries/adobe-operation-registry-v1.json`。

```bash
python3 -B scripts/darkroom.py prepare --workspace /path/to/new-workspace \
  --source-id SOURCE_ID_FROM_INGEST --parameters examples/neutral.json \
  --role baseline --intent "建立同引擎基线，检查现场光线与颜色"
python3 -B scripts/darkroom.py render --workspace /path/to/new-workspace \
  --plan PLAN_PATH_FROM_PREPARE
```

`prepare` 验证并预留一次尝试，返回冻结计划；`render` 使用该确切计划。
非基线修改必须先按 [知识调用](knowledge-workflow.md) 阅读资料并提供 `--knowledge-plan`。
`--role baseline` 只接受完全中性的参数，不接受局部/裁剪；`--role probe` 只接受脚本生成的固定合成 DNG 哈希，不能用于用户照片。
显式手工蒙版用 `--mask`，有限 DNG 裁剪用 `--geometry`；二者都需要知识计划绑定。
每张 RAW 按哈希在当前工作区默认最多三次（基线也算一次），失败不退款。
不能为检查可运行性反复 prepare；重复渲染一个已执行计划会被拒绝。
不要换工作区避开次数或历史失败。用户明确新增尝试时，底层 `darkroom.local_trial
authorize-window` 接口要求新授权原话、来源、同一源绑定和原因，每次仅加一次；
未耗尽或复用旧授权会拒绝。便捷接口没有自动追加功能。

出现失败先查看终端、`runs/` 与 Photoshop 实际状态；保留部分输出作为失败证据。
不自动删除记录、不强制关闭已有文档、不修改 Camera Raw 全局默认值。
若 Photoshop/ACR 弹窗或自动化许可阻塞，说明用户需完成的具体操作。

## 展示给 AI 的预览

先确认外发授权覆盖照片和当前供应商。全尺寸输出可能含 EXIF/XMP，不能直接上传。
使用 `scripts/preview.py` 可选工具重新编码 RGB JPEG，仅保留标准 sRGB ICC：

```bash
python3 -m pip install -r requirements-preview.txt
python3 -B scripts/preview.py --input /path/to/workspace/output/trial/PHOTO-frame.jpg \
  --output /path/to/new-preview.jpg
```

该工具不上传文件。检查预览真实像素和元数据后才送入获准的会话。
裁剪/100%细节另需精确授权并单独准备；1600 总览不能当作原生细节。

## 技术状态

`render_pass` 表示本次来源/参数完整性及同机重复 TIFF 像素检查通过。
`quality_acceptance_passed` 一直为 false：本版程序不判定审美，也不冒充用户验收。
实际看图结论与用户反馈另外记录到私人工作区，绑定输出哈希。
同机相同像素不证明原生读回、所有相机支持或跨机一致。
