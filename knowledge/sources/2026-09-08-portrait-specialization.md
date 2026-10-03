# 人像专项：依据、可见标准与能力边界

> 发布状态：`reference_proposed`。这是历史研究／方法候选，不是摄影师参数复原、已验证配方或新照片效果承诺。原始研究中的阅读、评分和执行声明没有随包携带验证证据，均不授予执行能力；使用前按当前工具和照片复核。
> 仅保留原创归纳和公开出处，不包含第三方图片、音视频、字幕全文、课程素材或预设；原作版权归各权利人，软件许可证不授予这些原作的权利。
> 历史笔记可能讨论合成、塑形或生成操作；这些仅是研究背景，不属于本 Skill 的非生成式执行范围。

## 已有与新增资料

既有 [P01–P06](2026-09-07-professional-workflow-calibration.md) 的完整工作流、宏观／微观 D&B、辅助图陷阱、修复与分频讲义保留，不重新计为新增。下表新增 13 篇实读来源；另有 2 篇官方／研究资料用于系列与评测。文章数不是独立实验数，转载、同作者与合作作者不能重复计票。

| ID | 实读一手来源 | 在模块中的作用 |
|---|---|---|
| D01 | [Brian Siambi／Zoë Noble · Capture One 访谈](https://www.captureone.com/blog/editing-skin-tones) | 概念与原光线决定颜色，硬光和深肤色可以保留光泽及密度 |
| D02 | [濱田英明 · Lomography 五问](https://www.lomography.jp/magazine/98533-hideaki-hamada) | 普通表情、观察距离与亲密关系；不是数字滤镜参数 |
| D03 | [濱田英明 · amana 访谈](https://amana.jp/insights/5250/) | 旅行场景与观看者的关系；不自动裁成特写 |
| D04 | [Alex Webb · Leica 芝加哥访谈](https://leica-camera.blog/2012/02/23/leica-magnum-alex-webb-in-chicago/) | 街头阴影、歧义与图形关系；不要求所有面孔明亮 |
| D05 | [Joe McNally · Rangefinder 三例](https://rangefinderonline.com/news-features/profiles/master-of-light-joe-mcnally-dissects-three-environmental-portraits/) | 环境人像的手、物件和地点可以共享视觉重点；拍摄补光不等于后期可恢复 |
| D06 | [井上依子 · Adobe 日本修饰访谈](https://www.adobe.com/jp/creativecloud/roc/blog/photography/retouching-tips.html) | 用途约束修饰深度，脸与手颈一起判断 |
| R1 | [Pratik Naik · 公开八页指南](https://theportraitmasters.com/wp-content/uploads/2019/11/Pratiks-Retouching-Guide-PDF-download.pdf) | 问题与笔触尺度、过修回退、颜色收尾、辅助层采样风险 |
| R2 | [Julia Kuzmenko McKim · FS 原创长文](https://fstoppers.com/post-production/ultimate-guide-frequency-separation-technique-8699) | 分离尺度与形体／高光副作用；不以固定半径跨图套用 |
| R3 | [Aaron Nace · PHLEARN 去红斑案例](https://phlearn.com/tutorial/how-to-remove-redness-from-skin-in-photoshop/) | 颜色范围＋空间蒙版的逐步案例；已独立目验公开前后图 |
| R4 | [Michael Woloszynowicz · Selective Color 肤色匹配](https://fstoppers.com/photoshop/simple-and-accurate-way-match-skin-tones-selective-color-photoshop-33587) | 相近条件下参照匹配；正文未展开视频中完整数值计算 |
| R5 | [Jesús Ramirez · Adobe 细杂发修复](https://www.adobe.com/learn/photoshop/web/spot-healing-retouch-imperfections) | 公开转录的空白层、短笔触、边缘保护，未观看视频 |
| R6 | [Adobe · Healing Diffusion 参数对照](https://helpx.adobe.com/photoshop/using/healing-examples.html) | 固定区域与采样对照扩散，检查边界污染；旧版本案例 |
| R7 | [Adobe · ACR 颜色与影调](https://helpx.adobe.com/camera-raw/desktop/using/make-color-tonal-adjustments-camera.html) | 影调、剪切和颜色范围语义；新版文档不等于本机能力 |
| Q01 | [Capture One · Normalizing skin tones](https://support.captureone.com/hc/en-us/articles/360002598218-Normalizing-skin-tones) | 同人、相同部位和类似明暗参照；不取腮红／眼影作为统一目标 |
| Q02 | [Gao 等 · Quality-guided Skin Tone Enhancement，2024 v1](https://arxiv.org/html/2406.15848v1) | 肤色质量与偏好评价的边界，不引入模型或其数据集 |

作者、日期歧义、阅读媒介、正文支持与本项目推论、实际步骤及不采用部分见 方向研究（本地材料未随包分发） 和 技术研究（本地材料未随包分发）。记录的是完整正文／公开指南／出版方转录阅读；没有把视频目录、嵌入视频或其他作者的转述当成已蒸馏视频。Julia Trotti 教程仅有短引言、Michael 视频公式未核实，均保留缺口。

R3 文末将 Spot Healing 写成手工取样，和 R5 官方解释不一致；保留作者的颜色案例，但操作定义以官方为准。头部作者也需逐项核查，不整篇无条件收编。

## 主控实际看过的公开示例

以下只有网页公开展示图。2026-09-08 主控下载到临时目录并通过 view_image 查看，未重修、未取得练习 RAW／PSD，未随 skill 或手机站点分发。访问不等于获再分发许可。这里只保存原创观察与原页链接；不以几张示例宣称完成全面专业成片标定。

### R3：红斑变化可以明显，形体与肌理仍保留

目验了作者标注的 [Before](https://phlearn.com/wp-content/uploads/2024/04/top-image-before_e49f12.jpg) 与 [After](https://phlearn.com/wp-content/uploads/2024/04/top-image-after_c3e9fb.jpg)，展示尺寸均为 1024×971。

在本次显示尺度下，脸颊与鼻周的红色减轻，毛孔、眼镜下阴影、鼻翼和下颌体积仍可辨；结果偏暖，不能把这份暖度当所有人的目标。**借用的是“减轻目标色块而保留结构”的可见标准**。单凭前后外观不能证明每个局部只经历过一种操作，参数归因仍以正文为限；本次未作逐像素差分或教程复演。

### D01：深浅层次可以比增白更有表现力

目验了文中 [Zoë Noble 编辑器截图](https://learn.captureone.com/wp-content/uploads/sites/2/2019/10/02_editing-skin-tones_Zoe-Noble-copy.jpg)，显示深肤色人像及颜色面板。额头、肩部、胸前反光与暗部形成体积，彩色唇妆与皮肤分开，整体并未靠抬浅皮肤成立。这是外观观察；截图中的数值不能作为完整配方，更不能由零值推断“没有后期”。没有对应原片，不能评其修图提升幅度。

## 评测补充：不能把皮肤单独评分当整张人像质量

Q01 官方说明（更新 2024-06-25，实读正文）要求选择可比的皮肤位置，避开化妆主导区域。项目应用：整组统一检查脸／颈／手，但不同光照的部位不强行同色；不引入 Capture One Normalize 为现有自动化能力。

Q02 实读 v1 的数据、实验和局限相关章节，未下载数据／运行代码。研究肤色实验把脸从背景中分离，并限制亮度变化，适合研究颜色偏好，却不能覆盖人物与环境是否协调、光线塑形、皮肤纹理或完整人像质量。论文比较允许“相似”，没有证明存在唯一标准肤色。项目因此保留全图、细节和整组三级评估，把偏好与技术缺陷分别记录；不采用论文分数或其自报结果作为本 skill 成绩。
