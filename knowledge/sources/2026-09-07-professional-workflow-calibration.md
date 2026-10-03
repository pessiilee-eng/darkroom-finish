# 专业修图方法调研与当前流程校准

> 发布状态：`reference_proposed`。这是历史研究／方法候选，不是摄影师参数复原、已验证配方或新照片效果承诺。原始研究中的阅读、评分和执行声明没有随包携带验证证据，均不授予执行能力；使用前按当前工具和照片复核。
> 仅保留原创归纳和公开出处，不包含第三方图片、音视频、字幕全文、课程素材或预设；原作版权归各权利人，软件许可证不授予这些原作的权利。
> 历史笔记可能讨论合成、塑形或生成操作；这些仅是研究背景，不属于本 Skill 的非生成式执行范围。

日期：2026-09-07。状态：原创研究笔记，方法待本地实验；不是可执行技术卡、题材包冻结或专业成品验收。

## 1. 可落地的结论

采用三个环节：从署名完整案例提取决策规则；在许可及照片范围明确的练习素材上复演一个具体问题；在未参与调参的新照片上比较旧流程与新流程。前两者能学习方法，第三者才能提供迁移证据。

目前最重要的改进是：把意图放到操作选择之前；把脸部明暗、色偏、纹理和处理副作用分开诊断；色彩明确主从与保护对象；把局部和整组质量检查变成必经步骤。需要新后端能力的手法仍留研究状态，不能靠方法文档绕过执行准入。

“专业来源明确讲过”“本机操作有效”“新照片确实更好”是三种不同事实。没有独立真人同 RAW 比较，本项目仍不得声称达到真人高手水平；公开多解、同模型新会话检查和用户测试反馈都不能代替该证明。

## 2. 方法来源与实际证据

以下 P/C/T 来源的统一 `license_status` 为：公开可阅读的一手文字或署名教学材料；本文仅原创概括并链接，不主张取得原文、图片、动作或课程文件的再分发权。特殊素材限制另列。页面中的商品宣传不算质量证据；评论区第三方建议不升格为作者方法。

### P01｜Michael Woloszynowicz：全流程与局部后续校色

[Portrait and Beauty Retouching Workflow — Capture One](https://www.captureone.com/blog/portrait-and-beauty-retouching-workflow)。首发日未确认；正文明确讨论旧软件版本。

已读 RAW 准备、PS 修饰顺序、最终调色、系列比较和输出。PS 部分是概述，不是完整精修课程。作者在局部明暗处理后复核肤色色相和饱和度，并警告过强的肤色均一化会波及嘴唇、妆容、衣服或压平自然变化。

转化：明度修完必须回看彩色；基础母版与输出变化分开。其清理、提取主体和塑形操作不自动进入本项目。不能照搬旧版 Capture One 的数值到 ACR。

### P02｜Julia Kuzmenko McKim：局部 D&B 与辅助观察的陷阱

[The Ultimate Guide to the Dodge & Burn Technique, Part 3 — 作者署名于 Fstoppers](https://fstoppers.com/photoshop/ultimate-guide-dodge-burn-technique-part-3-curves-setup-more-9281)，2014-05-28。

已读完整方法长文。局部均衡与整体塑形的目的不同；微弱曲线、黑蒙版和低强度笔触逐渐建立修正。偏红皮肤可能被改变红色权重的黑白辅助层显示为偏暗，导致误提亮；处理后也可能产生色差。

转化：先分清色差与明暗差，交替观察彩色及辅助图；出现漂白、变平或形体失真就回退。只吸收保留现有体积的修饰，不导入身份塑形。没有证据表明本项目旧黑斑由该辅助层导致。

### P03｜Julia McKim：微小明暗过渡与观看尺度

[Dodge and Burn: Working with Micro Transitions — Retouching Academy](https://retouchingacademy.com/dodge-burn-working-with-micro-transitions/)。页面显示 2019-01-21。

正文可独立阅读，不依赖嵌入视频。将结构性光影和微小皮肤起伏区分，局部处理时交替检查缩放尺度。

转化：旅行小脸先解决正常观看就明显的问题；美容特写的修饰量不迁移为默认。只在极大缩放下更平整、缩小却失去面部体积，视为失败。

### P04｜Lulie Talmor：灰度辅助图的解释范围

[Black and White Conversions in Relation to Dodging and Burning — Retouching Academy](https://retouchingacademy.com/color-correction-lesson-preview-black-and-white-conversions-in-relation-to-dodging-and-burning/)。页面显示 2019-07-07，但已有 2014 年评论，原始发表时间未确认。

可读的是有完整比较说明的课程节选，不是整门课。作者比较不同灰度辅助方式，建议用灰色填充层的 Color 混合辅助观察，避免随意调整通道权重。

转化：辅助图只作诊断，不能独立作修好依据；须回看彩色和原图。文中的视觉生理解释不作为本项目工程依据。P02 引用本来源，两者不能算两份独立实验验证。

### P05｜Aaron Nace：基础皮肤修饰的范围控制

[Skin Retouching Basics in Photoshop — PHLEARN](https://phlearn.com/tutorial/skin-retouching-basics-photoshop/)，2019-01-29。

已读有步骤的正文和前后示例说明；未宣称完整观看视频，未下载练习文件。曲线与蒙版用于局部重阴影；过大范围修复可能破坏纹理并制造斑驳。

转化：优先有限的明暗和色彩修正，按实际用途决定深度。作者示范的毛发、细纹或其他对象移除不能自动准入本项目。

### P06｜Ben Willmore：分频的受控用途

[Picture Perfect with Frequency Separation — Adobe MAX 2021 L368，16 页公开讲义](https://static.rainfocus.com/adobe/am21/sess/1621286436023001jznn/LabWorkbook/MAX%202021-Frequency%20Separation_1633960815652001zo3s.pdf)。

讲义说明分离细节与较大尺度的色调后分别处理，分离尺度随照片变化；末段介绍可撤回的低频修饰。可读的是讲义，不代表看过完整现场课程。第 4 页明确练习图片仅用于本讲义练习，不能分享或分发。

转化：仅作为候选研究方法；先证明分离重组保持输入，再研究有限修正。不能把示范的位深相关数值直接移植；不能把墙面平滑、纹理替换或皮肤塑形作为本项目默认。当前没有此方法的执行准入。

### C01｜Mareike Keicher：颜色权重和系列关系

[Applying color harmonies in Capture One](https://www.captureone.com/blog/applying-color-harmonies-in-capture-one)。首发日未确认，页面存在迁移日期歧义，正文注明旧软件版本。

作者先考虑题材、用途、概念、主色、保护色和焦点，再组织色彩的面积、位置、明度及饱和度。系列可以混合色彩方案，但需共同故事；同步后仍逐张调整并保留自然肤色变化。

转化：意图写主色／辅助色／保护色及主要对比；不把调色简化为总饱和度。其商业服饰改色和具体比例不是旅行照片默认，也没有唯一正确配色。

### C02｜山田悠人：环境人像与京都夜景的主次

[Lightroom 人像与风景修饰 — Adobe 日本站](https://blog.adobe.com/jp/publish/2020/04/10/cc-adobe-stock-contributor-j-xico-lightroom-landscape-yamada-yuto-7)，2020-04-10。

署名作者逐步说明人像与京都五重塔夜景：基础调整后分别照顾主体和陪体，以局部明暗和清晰度组织视线，多次提醒避免过强。

转化：每个局部调整说明哪个区域该突出、哪个该退后；缩略图检查主次，细看过渡。文中脸部曝光和阴影的文字描述不足以支持精确数值；负清晰度、暗角并非每张必用。

### C03｜桐生彩希：夏日晴空和地表分开处理

[フォトレタッチの極意15：強い日射しにまぶしい夏空を再現 — Adobe 日本站](https://blog.adobe.com/jp/publish/2017/08/23/photo-retouch-gokui-15)，2017-08-23，来自作者在 COMMERCIAL PHOTO 的系列节选。

可读前后例、设计图说明和逐步操作。天空与地表分别处理，调整曝光／反差后再查蓝绿及中性色；Dehaze 会连带改变曝光和反差。

转化：夏日感要兼顾明亮、层次和蓝绿关系；检查局部交界与关键高光。缺失的云层细节不能靠本项目生成式补回。文中允许局部溢出是特定意图，不是所有照片的质量规则。

### C04｜桐生彩希：先设计光向和明暗区域

[レタッチの方針の立て方 — 玄光社／COMMERCIAL PHOTO](https://shuffle.genkosha.com/software/photoshop_navi/nature/9309.html)，2017-01-10。

阴天草地与树林案例包含原图、目标图、设计图和分步方法；依据已有光线组织前后景，再用裁剪调整明暗面积。文章允许个别阴影压暗，不能推成普遍截断要求。

转化：先写原有光向与空间关系，再定局部操作。样片有个人学习用途入口；本轮未下载，格式、字节和链接有效性未验证，不能称 RAW 基准，不能打包进共享 skill。

### C05｜Paul Reiffer：风格方向和强度分离

[Elevation – New Landscape & Cityscape Styles — 作者网站](https://www.paulreiffer.com/2022/04/elevation-new-landscape-cityscape-styles-exclusively-for-capture-one/)，2022-04-02。

已读适用场景、前后示例说明和使用建议；同时是销售预设的页面，不是完整免费精修课。作者强调基础白平衡、风格强度及逐图收尾。

转化：记录风格适用条件、强度和退出条件；夜景保留值得保留的暖灯，不机械全冷。未经购买或许可，不取得或复制其预设；不迁移其专属预设的数值。

### C06｜Baber Afzal：城市局部蒙版的人工复核

[See it from my perspective; Creative cityscapes editing — Capture One](https://www.captureone.com/blog/creative-cityscapes-editing)。首发日未确认；正文描述 2017 年 12 月拍摄，已有 2018 年评论。

署名作者解释迪拜雾中建筑从基础校正到颜色选择、局部蒙版修正和主次组织。颜色选择出的蒙版仍需处理漏选区域。

转化：检查边缘、玻璃和同色异物，不能凭蒙版生成成功就通过。作者叠加强清晰度追求的效果不适合直接复制到克制旅行风格；当前颜色范围蒙版仍不可执行。

### T01｜Adobe：RAW 配置文件也是基线的一部分

[Adjust color rendering in Camera Raw](https://helpx.adobe.com/camera-raw/desktop/edit-and-enhance-images/tone-and-color/adjust-color-rendering-camera-camera.html)，页面更新 2025-02-13。

官方明确 profile 决定色彩和影调基础，而且应用 profile 不改变其他滑块读数。

转化：学习复演和 A/B 比较都固定实际 profile、引擎与版本；相同滑块不意味着同一基线。新版 Adaptive 等功能不因文档出现就进入本机 ACR 16.5 流程。

### T02｜Adobe：细节要在相应尺度检查

[Sharpening and noise reduction in Camera Raw](https://helpx.adobe.com/camera-raw/desktop/using/sharpening-noise-reduction-camera-raw.html)，页面更新 2023-11-03。

官方要求至少 100% 观察锐化，说明 Amount、Radius、Detail、Masking 的不同作用；过大半径可能不自然。

转化：细节检查同时覆盖原尺寸和目标输出尺寸；不要让锐化扩大肤色斑块或噪点。文档说明不是当前执行器逐项验证结果。

### T03｜Adobe：面向实际用途校样

[Proofing colors in Photoshop](https://helpx.adobe.com/photoshop/using/proofing-colors.html)，页面更新 2023-05-24。

软打样模拟目标设备的色彩表现，可靠性取决于显示器、配置文件和环境光。

转化：屏幕分享检查对应输出文件；打印只在目标纸张／设备 profile 明确时进行相应校样，不宣称远程预览保证实际打印一致。

## 3. 无私人修图师时的五类学习素材

| 来源 | 已核实的能力 | 学习用途 | 访问、许可和当前限制 |
|---|---|---|---|
| B01 MIT–Adobe FiveK | 官方提供 5000 张 DNG、每张五个成片、Lightroom 设置及历史 | 同输入多种解法；基础影调方法复演 | 五位编辑者按官方说明为受 Lightroom 培训的艺术院校摄影学生，不是五位顶尖商业修图师。仅自身非商业研究；本轮未下载数据 |
| B02 Lightroom Community | 官方教程可读完整转录，说明 Play Edits、设置查看、保存预设和 Remix | 观察真实编辑步骤；条件允许时在应用内复演 | 官方明确不能下载他人照片；未核验本机账户与具体案例的访问，不是已接入的离线 RAW 库 |
| B03 Signature Edits Free RAW | 官方素材入口及详细许可可读 | 补充不同场景的练习原片 | 无每张对应专业答案的保证；具体文件未下载核验；禁止竞争图库、冒认作者，肖像等权利另有条件 |
| B04 PIXLS Play Raw | 类别规范及具体帖子提供 RAW、多人结果和 sidecar | 学习多解、取舍与失败讨论 | 逐帖许可和逐资产核验；社区编辑不自动具备专家资历；darktable XMP 不可当 Adobe XMP 直接用 |
| B05 PHLEARN | 免费／PRO 课程及部分练习文件访问条件可读 | 有完整示范时做定向课程练习 | 免费内容有限；PRO 内容未取得，不能称已学完；课程素材不随共享 skill 分发 |

来源和许可依据：

- B01：[FiveK 官方说明](https://data.csail.mit.edu/graphics/fivek/)、[Adobe 许可](https://data.csail.mit.edu/graphics/fivek/legal/LicenseAdobe.txt)、[Adobe–MIT 许可](https://data.csail.mit.edu/graphics/fivek/legal/LicenseAdobeMIT.txt)。2011 年项目；根代理直接打开目录遇体积限制，随后通过官方页的搜索索引复核描述，许可正文可直接读取；未核验数据文件字节。

- B02：[Adobe 官方教程，2026-06-01](https://www.adobe.com/learn/lightroom-cc/web/learn-photo-editing-lightroom-community)、[Remix 和预设 FAQ](https://helpx.adobe.com/lightroom/desktop/using/remix-recommended-presets-faq.html)。只核验文档；不上传用户照片求社区校准。

- B03：[素材入口](https://www.signatureedits.com/free-raw-photos/)、[完整许可](https://www.signatureedits.com/free-raw-license-terms/)。许可页面无明确版本日期，访问日为本笔记日期。共享时优先只提供来源链接与自写方法。

- B04：[类别规则](https://discuss.pixls.us/t/about-the-play-raw-category/11956)、[有色光人像案例，BY-NC-SA 4.0](https://discuss.pixls.us/t/portrait-with-coloured-light/26410)、[同 RAF 多解案例，BY-SA](https://discuss.pixls.us/t/how-would-you-edit-this/27932)。许可需在实际取样时再按目标资产复核，不存在类别级统一许可。

- B05：[访问帮助](https://phlearn.com/help-center/)、[使用条款](https://phlearn.com/terms-of-service/)。本轮未购买、未登录受限课程、未下载文件。

## 4. 工作流覆盖与缺口

| 需要校准的能力 | 本轮依据 | 现在应改变什么 | 未解决什么 |
|---|---|---|---|
| 意图与构图主次 | C01/C02/C04 | 操作前写主体、光向、颜色关系、保护对象 | 缺真实自动判断与裁剪效果验证 |
| RAW 基础和可回退性 | P01/T01 | 固定 profile 与引擎，保留基础版本 | 相机间差异、旧教程与当前后端映射 |
| 肤色和局部光影 | P01–P06 | 明暗／色偏／纹理／副作用分类；不同尺度检查 | 精细 D&B 执行器、不同肤色与小脸实测 |
| 晴日风景和空气感 | C03/C04 | 天空地表分开判断，调整后查连带影响 | 强逆光、雾天及夜景不共用规则 |
| 街拍和混合夜光 | C02/C05/C06 | 灯光关系、视觉焦点、蒙版边缘复核 | 极端 LED 色污染、运动模糊等样本未覆盖 |
| 系列一致性 | P01/C01/C05 | 共用表达意图，逐图修正，整组检查 | 十张完整交付尚未验证 |
| 细节与输出 | P01/T02/T03 | 100% 和最终尺寸双尺度检查 | 未进行实际打印和显示器校准 |

这是对当前试验的覆盖图，不是“行业全部好经验”的分母。中文视频教学池、作者完整课程、黑白、商品静物、纪实边界和更广肤色／光照仍有缺口。没有执行的逐帧视频学习不计入已读数量。

## 5. 方法冲突和不采纳项

- D&B 与分频处理不同问题，不统一宣布一种高级、另一种落后。当前优先分清成因与最小干预；分频研究必须服从纹理、形体和对象保留边界，不因公开教程而开通新操作。

- 不同作者有不同处理顺序。采纳“检查操作的连带影响”，不规定所有照片必须照同一滑块次序走完。进入像素修饰前应保留足够余地。

- C03/C04 的强反差与 C05 的柔和风格有不同适用情境；少量允许的截断不是所有照片的默认。保护区域与可接受变化要来自该照片的意图。

- C06 的重清晰度、P01 的肤色均一化和部分课程的对象移除，都不能直接变成全局默认。教程中的数值只证明该案例操作，不能由成片反推也不能跨引擎照搬。

- P02/P04、C03/C04存在来源关联。独立交叉印证按作者和证据链计，不能按链接数制造多数共识。
