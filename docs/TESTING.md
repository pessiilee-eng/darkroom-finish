# 安装与换机验证

三件事分开：程序能用、参数确实生效、照片修得好。自动测试只覆盖前两者的一部分。

## 不使用 Adobe 的测试

在解压目录用 Python 3.11+：

```bash
python3 -B -m unittest discover -s tests -v
python3 -B scripts/knowledge.py verify
python3 -B scripts/knowledge.py search "负空间"
```

标准库测试在独立临时工作区运行，使用无照片内容的测试字节。去元数据预览测试需要
`requirements-preview.txt`；未装时会明确 SKIP，不应记录为预览测试通过。
推荐在虚拟环境安装可选依赖，不修改系统 Python：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-preview.txt
.venv/bin/python -B -m unittest discover -s tests -v
```

## 真实 Adobe 探针

先运行 `scripts/darkroom.py doctor`，再选择一个不存在的目录：

```bash
python3 -B scripts/probe.py --directory /path/to/new-synthetic-probe
```

这会实际控制 Photoshop，生成自己的 DNG 色块，显影中性版、曝光 +0.5 版、手工画笔版，
并在单独的合成测试工作区检查有限原生裁剪。每版重复导出 TIFF，检查源文件未变、
无原目录旁车、重复像素相等、调整后亮度上升，以及裁剪尺寸兑现。
报告保存在该目录的 `probe-report.json`。它不证明真实相机、全部操作或画质通过。
若应用失去响应，不要自动强退或关闭用户其他文档。

## 第二台 Mac

只复制本发布包，不复制作者电脑环境、用户照片或私人工作区。
记录系统/芯片、Python、Photoshop/ACR 版本、执行入口和实际耗时；按上面命令
完成测试与探针，再由测试者自己提供一张获准 RAW 做基线和一次明显调整。

- 安装过程没有依赖作者路径、私有工具或手动补文件。
- 能检索并读取完整档案和方向；复制知识快照后断开原安装位置，已有运行依赖仍完整。
- 基线外修改必须提供该照片的知识计划；错误源哈希、知识改动、不存在的方法或漏绑定操作均拒绝。
- 原文件哈希与源目录内容不变；所有生成文件留在指定工作区。
- 基线和调整均能出图，参数方向生效；核对色彩、方向与必要原生细节。
- 失败与缺权限时准确停止，无自动上传、越界写入、覆盖原片或无限重试。
- 可选预览没有 EXIF/GPS/XMP/注释，长边最多 1600，实际像素非全黑。

换机后的新工作区需重新生成计划；旧计划绑定本机 Python 与依赖，不直接拷贝运行。
用户照片不应附在公开 issue；分享诊断时去掉源路径、用户名、授权文字及照片哈希。
在没有完成此实测前保持“第二台机器未验证”。不同 ACR/profile 的出图不承诺字节相同。
