# creative-storyboard

将 Brief 或完整剧本转化为可执行创意方案与单镜头分镜（P0：仅 1 个 5 秒镜头）。

## 适用条件
- 自由创作模式或剧本驱动模式
- 输出必须为严格 JSON，供后续节点解析

## 输出
- CreativePlan
- Storyboard（shots 长度=1）

## 工具
本 Skill 主要驱动 LLM 结构化生成，不直接调用 generate_image/generate_video。
