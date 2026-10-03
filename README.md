# Darkroom Finish

用自然语言决定一张照片要怎样表达，让 AI 规划调整，由本机 Photoshop / Camera Raw
执行并保留可核验的参数与前后对照。照片和工作记录默认留在自己的电脑。

**0.1.0-alpha.1：实验版。** 面向 macOS 上的单张 RAW，全局影调、颜色与曲线。
不保证专业成片、所有相机格式或跨机相同像素。真实第二台电脑验收尚待完成。
此仓库不包含作者照片、私人配方、账户信息、运行历史或第三方摄影素材。

## 摄影师知识库是否包含在内

本版公开的是独立修图 Skill 和执行内核，**不是原私人研究系统的完整复制**。
历史摄影师档案、具体作品目标库、教程笔记、参考图及个人试修配方未随包发布；
保留的是重新编写的通用画面判断与操作规则。因此不能宣传为“内置全部摄影师风格库”
或保证复现私人项目的全部效果。处理范围与后续知识包原则见 [知识库边界](docs/KNOWLEDGE-SCOPE.md)。

## 需要什么

- macOS、自己安装并可用的 Photoshop 和 Camera Raw；Adobe 不包含在本项目中。
- Python 3.11 或以上。核心流程只用 Python 标准库，不需要 Node、NumPy、API Key。
- 能执行本机命令并在获准后看图的 AI 助手。Codex Skill 入口是根目录 `SKILL.md`；
  其他助手可以读取同一入口，但其自动发现与权限行为未逐一验证。
- 渲染时 macOS 可能要求允许终端/AI 应用控制 Photoshop。`doctor` 不会替你授予权限。

## 安装

下载本仓库 ZIP，解压为 `darkroom-finish`。不要只复制 `SKILL.md`。
Codex 可将整个文件夹放进项目的 `.agents/skills/darkroom-finish/`；已有同名技能时
先选择新的测试项目，不覆盖原技能。没有自动发现时，明确让助手读取该文件的绝对路径。

在解压目录运行：

```bash
python3 -B scripts/darkroom.py doctor
python3 -B -m unittest discover -s tests -v
```

多个 Photoshop 版本或自定义安装位置可显式选择：

```bash
python3 -B scripts/darkroom.py doctor --photoshop-app "/Applications/Adobe Photoshop 2026/Adobe Photoshop 2026.app"
```

新电脑先按 [验证指南](docs/TESTING.md) 完成合成探针，再处理自己的照片。

## 使用

可以对助手说：

> 用 darkroom-finish 帮我修这张 RAW。保持现场光线和自然颜色，先给我一版，
> 告诉我做了什么和仍有什么问题。只访问我给你的这个文件。

助手会执行 [本机操作](references/local-workflow.md)。新建的工作区要放在安装目录之外，
也不要放到照片原目录中。工作区包含私人照片、参数和授权文字，不要提交到 Git。
程序只检查授权记录的一致性，助手仍须判断实际用户指令是否覆盖本次操作。

输出包括 TIFF、JPEG、XMP 配方、源哈希和同机重放证据。输出文件可能带照片元数据；
**本地输出不是可直接公开的文件**。如需把预览交给云端 AI，用文档中的专用去元数据导出，
并取得对应授权。分享或发布照片由照片所有者自己决定。

## 当前限制

便捷入口接受 NEF/DNG/CR2/CR3/ARW/RAF/ORF/RW2/PEF 扩展名；实际解码能力依赖
Camera Raw 的相机支持，不能把扩展名准入当作全部型号测试通过。普通 JPEG 输入不在首版范围。
基础编译器的手工蒙版和有限原生裁剪留作进阶接口，不承诺自动人像精修。
初始与修正总计默认最多三次计划；缺失输出、原片变化或篡改均停止，不自动无限重试。

`rendered` 不代表用户满意。效果、安装可用性和参数实际生效分别检查。
这里不会扫描相册、连接私人网站、自动外发照片或调用其他供应商模型。

采用 [MIT 许可证](LICENSE)，见 [验证状态](docs/RELEASE-STATUS.md)。
请勿把本地工作区或真实照片附在公开 issue 中。
