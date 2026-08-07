# h3-video-production

选择文生视频 / 首帧 / 首尾帧模式，构造动作与运镜描述，提交异步 H3 任务。

## 工具
- generate_video
- get_generation_job

## P0 约束
- 默认 5 秒、16:9、768p、首尾帧生视频
- 不得宣称支持本地 2K
- 单阶段最多重试 2 次
