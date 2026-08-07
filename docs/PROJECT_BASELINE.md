# SLMAgent 项目决策基线

> 状态说明：本文档用于在人员、Agent、对话窗口或开发环境切换后，继续保持 SLMAgent 项目的产品目标、技术边界、关键决策和实施顺序一致。它既是后续开发的总指导文档，也是比赛汇报、项目复盘和个人项目经历沉淀的基础材料。

本文严格区分以下状态：

- **已经确认的设计决策**：团队已经讨论并决定采用的方向。
- **计划实施**：尚未开发或部署，但已经进入实施范围。
- **待实测确认**：必须租用服务器、下载权重和运行模型后才能确定。
- **二期设想**：不属于当前 P0 MVP 的验收范围。

截至本文档编写时，SLMAgent 尚未完成真实模型部署，文中不得把计划能力写成已经实现的功能，也不得虚构推理速度、显存占用、成功率或生成质量。

---

## 2. 项目名称与核心定义

### 2.1 项目名称

**SLMAgent — Simple Local Media Agent**

中文可表述为：简易本地化智能视听创作智能体。

这里的 “Local” 指图像和视频生成模型运行在团队可控制的自托管服务器中，不要求必须运行在个人电脑，也不等同于完全离线。DeepSeek 文本模型首版仍通过 API 调用。

由于 SLM 在行业中也常指 Small Language Model，对外首次介绍时必须同时写出 Simple Local Media Agent 全称，避免歧义。

### 2.2 一句话定位

SLMAgent 是一套基于 LangGraph 工作流、Agent Skill、自托管 FLUX 图像模型和 MiniMax-H3 视频模型的视听创作 MVP，用于验证从创作需求或完整剧本输入，到关键帧、视频和简化成片输出的全自动生成链路。

### 2.3 当前项目性质

当前项目不是成熟商业产品，也不以高并发和完整内容生产平台为目标。现阶段的核心任务是：

1. 验证 FLUX.2 Klein 9B 与 MiniMax-H3 Base FL2VA 能否在自托管服务器上稳定运行；
2. 验证 DeepSeek、LangGraph、Skill、图像模型和视频模型能否形成完整工作流；
3. 验证结构化分镜、首尾关键帧和视频提示词能否在不同模型之间可靠传递；
4. 形成可复现、可追踪、可交接的部署与运行方法；
5. 为后续广告、宣传片、短剧、漫剧等场景扩展建立技术底座。

---

## 3. MVP 目标与范围

### 3.1 P0 目标

用户输入项目 Brief 或完整剧本，并可上传参考图片；系统全自动完成：

理解需求 → 创意策划 → 镜头拆解 → 生成图像提示词 → FLUX 生成首尾关键帧 → 自动基础质量检查 → 生成 H3 视频提示词 → H3 生成 5 秒、16:9、768p 视频 → FFmpeg 检查、转码和导出 → 保存完整项目记录

P0 的完成标准是完整链路能够跑通并输出一段大致符合要求的 5 秒宣传镜头。当前以验证为主，不预先承诺商业级画质、固定成功率和固定生成时长。

### 3.2 推荐首个演示案例

- 主题：智影 AIGC 创作平台产品宣传镜头
- 类型：科技感产品/项目宣传片
- 时长：5 秒
- 比例：16:9
- 输出：本地 768p
- 生成方式：FLUX 生成首尾帧，H3 使用首尾帧约束生成视频
- 后期：FFmpeg 完成基本转码与输出

### 3.3 暂不纳入 P0 的能力

- 多用户高并发
- 完整一分钟宣传片
- 完整短剧或漫剧批量生产
- 复杂数字人和精确口型
- 自动配音、专业配乐和复杂混音
- H3 Ref2VA
- H3 官方托管的 2K 增强链路
- 多个独立智能体协商
- 商业生产级账号、权限、计费和审计后台
- 无人工保障的无限自动重试

---

## 4. 目标用户与使用场景

MVP 主要面向需要验证 AIGC 视听工作流的：

- 高校创新创业与科研团队
- 小型广告、宣传片和内容工作室
- AIGC 工具与 Agent 工作流研究者
- 希望尝试私有化图像、视频生成的创作团队

首个场景优先采用产品广告或项目宣传片。短剧、漫剧、电影和动画属于后续可扩展场景。

---

## 5. 用户交互与产品功能

### 5.1 创作模式

Gradio 首版提供两种入口：

1. **自由创作模式**：用户填写 Brief，由系统生成创意与分镜
2. **剧本驱动模式**：用户直接粘贴完整剧本，由系统进行结构化拆解

两种模式均支持上传参考图片。

### 5.2–5.4 输入 / 默认项 / 输出

详见仓库内 Gradio 表单与 `contracts` 定义。P0 默认值：产品宣传片、科技未来、16:9、5 秒、首尾帧生视频。尚未验证的能力应标注“实验性”。

---

## 6. 总体技术架构

```
Gradio 用户界面
        ↓
FastAPI 业务入口
        ↓
LangGraph 主 Agent 状态工作流
        ├── DeepSeek API
        ├── creative-storyboard / flux-image-production / h3-video-production Skills
        ├── FLUX 推理服务（GPU 2）
        ├── H3 推理服务（GPU 0、1）
        ├── OpenCLIP 与确定性质量检查
        └── FFmpeg 后期处理
        ↓
共享模型盘、项目素材目录和运行清单
```

### 6.1 单主 Agent 状态图

```
RECEIVE_INPUT → PLAN_CREATIVE → BUILD_STORYBOARD → PREPARE_IMAGE_PROMPT
→ GENERATE_IMAGE → CHECK_IMAGE → PREPARE_VIDEO_PROMPT → GENERATE_VIDEO
→ CHECK_VIDEO → POSTPROCESS → COMPLETE
```

### 6.2 职责边界

- **LangGraph**：下一步、状态、失败分支
- **FastAPI**：稳定网络接口
- **Gradio**：表单、上传、预览
- **模型服务**：GPU 推理
- **Skill**：场景方法、结构、工具选择

---

## 7. 模型选型

| 角色 | 选型 | 状态 |
|------|------|------|
| 文本 | DeepSeek API（`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`） | 计划实施 |
| 图像 | FLUX.2 Klein 9B | 待实测确认 |
| 视频 | MiniMax-H3 Base FL2VA（本地 768p） | 待实测确认 |
| 检查 | OpenCLIP + 确定性文件检查 | 计划实施 |

官方资源：

- FLUX：https://github.com/black-forest-labs/flux2 / https://huggingface.co/black-forest-labs/FLUX.2-klein-9B
- H3：https://github.com/MiniMax-AI/MiniMax-H3 / https://huggingface.co/MiniMaxAI/MiniMax-H3

注意：不得写成已支持本地 2K；P0 不做商业授权声明。

---

## 8–10. Skill / 工具 / 重试

三个 Skill：`creative-storyboard`、`flux-image-production`、`h3-video-production`。

P0 仅暴露三个工具：`generate_image`、`generate_video`、`get_generation_job`（异步 job_id）。

每个生成阶段最多重试 2 次。质量阈值必须通过真实样本校准，文档现阶段不填写虚构数值。

---

## 11. 服务器目标配置

- 目标：单机 3×48GB（H3 占 GPU 0/1 INT8，FLUX 占 GPU 2）
- 降级：2×48GB 错峰
- GPU 优先级：L40S → RTX 6000 Ada → L40 → A6000 → A40
- 本项均为目标配置，不代表已获得或实测

---

## 12–14. Docker / 数据 / 代码结构

权重不进镜像，挂载 `/data/models/*`。先原生调通再 Docker。每次运行独立 `runs/project_xxx/` 目录。代码结构见仓库根目录。

---

## 15. 实施路线

| 阶段 | 内容 | 状态 |
|------|------|------|
| A | 本地 Mock，不租 GPU | 进行中 |
| B | FLUX 云端部署 | 未开始 |
| C | H3 云端部署 | 未开始 |
| D | 端到端集成 | 未开始 |
| E | 稳定与容器化 | 未开始 |

---

## 16–18. 验收 / 风险 / 状态清单

详见原文第 16–18 节要点：功能、工程、质量验收；模型环境、多卡、显存、自动质量、成本、许可证风险。

### 18.1 已确认的设计

项目名、自托管图/视频、P0 全自动 5 秒宣传镜头、LangGraph + FastAPI + Gradio、单主 Agent、DeepSeek、FLUX.2 Klein 9B、H3 Base FL2VA、三个自有 Skill、OpenCLIP 检查、H3 原生音频策略、目标 3×48GB、先原生后 Docker。

### 18.2 尚未完成

本地 Mock 代码、DeepSeek 结构化输出测试、云服务器、FLUX/H3 真实部署、联调、阈值校准、Docker、真实成片与性能数据。

### 18.3 待实测确认

云平台、GPU 型号、H3 2×48GB INT8 兼容与速度、FLUX 显存、三卡稳定性、耗时/内存/成功率/成本、检查阈值。

---

## 19. 下一步立即行动

1. 新建 SLMAgent 代码仓库
2. 建立 Gradio、FastAPI、LangGraph 和 Mock 服务骨架
3. 定义 Brief、Storyboard、ImageJob、VideoJob 和 Manifest 结构
4. 接入 DeepSeek API，验证 Brief → 合法 JSON
5. 使用假图片和假视频完成端到端 Mock
6. 按服务器检查表筛选 3×48GB 实例
7. 优先部署 H3 官方最小示例
8. 再部署 FLUX 并封装服务
9. 完成一个 5 秒智影宣传镜头
10. 记录真实数据，回填本文档并决定是否进入 P1

---

## 20. 后续可扩展方向

9B KV、H3 Ref2VA、多模态审片、资产库、15 秒多镜头、字幕/TTS/配乐/Remotion、短剧漫剧模板、专业 Agent 拆分、成本与可复现实验导出、比赛展示材料。

本文档是当前决策基线。后续任何模型、服务器、Skill、接口和流程变化，都应同步更新「已确认、待完成、待实测」三类状态，避免计划被误写为成果。
