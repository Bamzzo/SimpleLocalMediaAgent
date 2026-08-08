# 资产归档、恢复与部署指南

## 先区分两类资产

本仓库中的压缩包是工程证据和恢复线索，不是完整模型镜像：

| 资产 | 用途 | 不能替代 |
|---|---|---|
| archives/p10_evidence_20260808_090019_AIGC_f25501.tar | 复核 P10 的云端媒体、日志、PID 与环境摘要 | 本地源码、完整模型服务 |
| slmagent-h3-cloud-adaptation-20260807.tar.gz | 复核 H3 原生验证、版本 pin、脚本和烟测证据 | 约 144 GB H3 权重、CUDA、完整 Python 环境 |

不要将模型权重、HF 缓存、完整虚拟环境、.env、API Key、SSH 私钥、shell history 或 IDE 会话文件上传到 GitHub。

## 下载后先校验

Linux/macOS：

~~~bash
sha256sum -c archives/p10_evidence_20260808_090019_AIGC_f25501.tar.sha256
sha256sum -c slmagent-h3-cloud-adaptation-20260807.tar.gz.sha256
~~~

Windows PowerShell：

~~~powershell
Get-FileHash archives\\p10_evidence_20260808_090019_AIGC_f25501.tar -Algorithm SHA256
Get-FileHash slmagent-h3-cloud-adaptation-20260807.tar.gz -Algorithm SHA256
~~~

预期 P10 tar 哈希：

~~~text
fad70402b3e9d90140a6a8a51535c933d8b6bfe82315daf1ef627fd237b43611
~~~

## 解压并检查证据包

建议解压到仓库外的审计目录，避免把二进制媒体混入源码工作区：

~~~bash
mkdir -p ../slmagent-audit/p10
tar -C ../slmagent-audit/p10 -xf archives/p10_evidence_20260808_090019_AIGC_f25501.tar
cd ../slmagent-audit/p10/p10_evidence_20260808_090019_AIGC_f25501
sha256sum -c MANIFEST.sha256
~~~

P10 包中应包括两张 PNG、一个 H3 MP4、FLUX/H3 日志和 PID、运行快照、接口契约与依赖摘要。它不包含本地 final_manifest.json；该文件保留在本地项目 run 目录。

## 本地应用部署（Mock）

~~~powershell
git clone https://github.com/Bamzzo/SimpleLocalMediaAgent.git
Set-Location SimpleLocalMediaAgent
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
python -m pytest -q
~~~

启动服务：

~~~powershell
# Terminal A
python -m uvicorn slmagent.api.main:app --host 127.0.0.1 --port 8000

# Terminal B
python -m slmagent.apps.gradio_app
~~~

浏览器打开 http://127.0.0.1:7860。该模式默认是 Mock，不依赖云端 GPU。

## 恢复真实媒体服务的前提

真实模式不能只靠两个归档包恢复。恢复前应具备：

1. 有足够存储和 GPU 的受控 Linux 实例。
2. 按 H3 归档中的 pin、脚本与上游官方文档重新获得模型权重、CUDA toolkit、SGLang 和 Python 环境。
3. 独立验证 H3 原生 FL2VA 与 FLUX 原生图像生成。
4. 让云端服务仅监听 127.0.0.1。
5. 在本地建立 SSH 隧道，不公开模型端口。
6. 确认 FFmpeg/ffprobe 可用，再执行视频任务。

归档中记录的是一次已验证实例的路径、版本和参数，不能假设在其他 GPU、驱动、CUDA 或上游版本上无需调整。

## 真实模式的本地配置

服务健康后，在本地启动 API 与 Gradio 的 PowerShell 会话中设置：

~~~powershell
$env:GENERATION_BACKEND = "live"
$env:FLUX_SERVICE_URL = "http://127.0.0.1:18001"
$env:H3_SERVICE_URL = "http://127.0.0.1:13011"
$env:API_PIPELINE_TIMEOUT_SEC = "1800"
$env:LIVE_VIDEO_TIMEOUT_SEC = "1800"
$env:NO_PROXY = "127.0.0.1,localhost"
$env:no_proxy = "127.0.0.1,localhost"
~~~

18001 和 13011 是本地转发端口；云端工作器仍应是 127.0.0.1:8001（FLUX）和 127.0.0.1:30010（H3）。端口被占用时应选择新本地端口并同步更新环境变量。

在提交生成任务前，分别验证：

~~~powershell
Invoke-RestMethod http://127.0.0.1:18001/health
Invoke-RestMethod http://127.0.0.1:13011/health
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/docs
~~~

## 运行、归档与停服顺序

1. 仅提交一次 P10 风格的单镜头任务。
2. 保留本地 runs/<project_id>/，其中的 final_manifest.json 是本地编排事实来源。
3. 在云端复制媒体、日志、PID、运行快照和哈希到一个小型证据目录。
4. 校验 tar 自身哈希和内部 MANIFEST.sha256。
5. 将 tar 下载到本地并再次校验。
6. 使用活跃 PID 文件向 FLUX、H3 发送 SIGTERM，确认端口关闭和 GPU 释放。
7. 确认云服务商的关机/释放计费语义后，再停止或释放实例。

不要用宽泛的 pkill -9 -f python；不要在本地证据未校验前释放云端实例。
