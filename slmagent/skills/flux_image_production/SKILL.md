# flux-image-production

将结构化分镜转换为 FLUX 提示词，生成首帧与尾帧，管理候选与有限重试。

## 工具
- generate_image
- get_generation_job

## P0 约束
- 默认首尾帧
- 保存种子、参数与输出路径
- 单阶段最多重试 2 次
