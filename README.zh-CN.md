# PageVoice

[English](README.md) | **简体中文**

使用 [Kokoro](https://github.com/hexgrad/kokoro) 或 [Pocket TTS](https://github.com/kyutai-labs/pocket-tts) 朗读网页 —— 一个可自托管的
神经网络文本转语音服务器，搭配一个跨浏览器扩展，从服务器流式获取音频，并以
卡拉 OK 式的高亮跟随朗读进度。

这是一个包含两个部分的 monorepo（单一代码仓库）：

| 目录 | 简介 |
| --- | --- |
| [`server/`](server) | 共享的 FastAPI 服务器，支持 Kokoro（美式/英式英语，可调语速）与 Pocket TTS（CPU 推理、英语预置语音）。 |
| [`extension/`](extension) | 一个 Chrome（MV3）/ Firefox（MV2）扩展，可朗读页面正文、点击的元素，或从某处开始到页尾的内容 —— 既可经由服务器（Kokoro 或 Pocket TTS），也可使用零配置的 Google 翻译作为后备方案。 |

扩展的 Kokoro 和 Pocket TTS 引擎需要服务器在运行；Google 翻译引擎不需要。

![演示：朗读正文，卡拉 OK 式高亮跟随朗读进度。](docs/demo.gif)

## 快速开始

> **最简单的安装方式 —— Windows，无需命令行。** 从最新的
> [release](https://github.com/davuses/pagevoice/releases) 下载：
>
> 1. 运行 **`pagevoice-server-setup.exe`**。它会自动完成全部安装配置（首次运行需
>    下载几百 MB，耗时数分钟），随后以**系统托盘图标**的方式在后台运行服务器，也
>    可设置为登录时自动启动。
> 2. 解压 **`pagevoice-extension-chrome.zip`**，打开 `chrome://extensions`，启用
>    *开发者模式*，再**加载已解压的扩展程序**，选择解压后的文件夹。
> 3. 点击扩展图标，选择 Kokoro 或 Pocket TTS 引擎和语音，使用朗读按钮即可。
>
> 下面的步骤适用于 macOS/Linux 以及开发者。

**1. 运行服务器**（详见 [`server/README.md`](server/README.md)）：

不熟悉命令行？直接双击 `server/` 文件夹中对应你系统的启动器即可，无需运行下面的
命令 —— `start-server.bat`（Windows）、`start-server.command`（macOS）或
`start-server.sh`（Linux）。首次运行时它会自动完成所有安装配置。

```bash
cd server
uv sync
uv run uvicorn server:app --host 127.0.0.1 --port 18001
```

每个引擎在首次请求时加载并缓存模型与语音，首次使用需要联网下载权重。
Kokoro 优先使用 GPU；Pocket 使用 CPU。两者都支持流式播放、句子高亮、自动滚动、
跳句和 WAV 下载。Pocket 提供 12 种预设语音，暂不支持语速调整。

macOS 源码支持以 Apple Silicon、macOS 14+、Python 3.12 和 CPU 推理为目标。
Apple Silicon CI 会检查依赖安装、服务器及真实语音生成，并提供 WAV 测试产物。
Finder 启动、浏览器播放及休眠恢复仍需真实 Mac 验证；目前没有签名的 `.app`/`.dmg`，
暂不支持 Intel Mac。Windows/Linux 的 NVIDIA 加速保持可用。

**2. 构建并加载扩展**（详见 [`extension/README.md`](extension/README.md)）：

```bash
cd extension
npm install
npm run build:chrome     # 或 build:firefox
```

然后在浏览器中加载已解压的 `dist-chrome/`（或 `dist-firefox/`），在弹出窗口中
选择一个 Kokoro 语音，再通过弹出窗口中的朗读按钮或右键菜单开始朗读。

## 隐私与安全速览

- 用 **Kokoro 或 Pocket TTS** 朗读的文字只会发送到你自己运行的服务器。
- 用 **Google 翻译** 朗读的文字会发送到 Google 的公共 TTS 接口。详见
  [`extension/PRIVACY.md`](extension/PRIVACY.md)。
- 服务器**没有鉴权或限流** —— 除非你打算共享它，否则请将其绑定到
  `127.0.0.1`。详见服务器 README 中的安全说明。

## 许可证

[Apache-2.0](LICENSE)。Kokoro 使用 Apache-2.0，Pocket TTS 使用 MIT；预置语音遵循各自的上游许可证。

## 从 kokoro-read-aloud 升级

项目已更名为 PageVoice，仓库地址为 [davuses/pagevoice](https://github.com/davuses/pagevoice)，从 v3.0.2 起发布文件使用 `pagevoice-*` 名称。使用 Pocket 需要同时
更新服务器与扩展。现有语音、服务器地址和播放设置会保留。Windows 安装目录、
安装器 AppId、GPU 偏好和日志位置不变；升级后首次启动会更新依赖。
安装前请退出旧的托盘服务器，安装后重新启动，使新代码生效。
