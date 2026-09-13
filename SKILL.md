---
name: youzan-github-release
description: Independently package and publish the Youzan AIGC video plugin to its GitHub update repository without the legacy one-click publisher.
metadata:
  short-description: 独立发布有赞视频插件
---

# 有赞插件独立发布

用于发布本地有赞 AIGC 视频插件的新版本。插件通常位于 E:\字字动画\_internal\plugins\video_plugins\video_plugin_youzan_aigc；更新仓库为 609335334-rgb/youzan-aigc-plugin-updates。

不要调用、修改或依赖 release_plugin.py、.release-tools 或 一键发布新版本.bat。

## 发布流程

1. 读取 main.py 与 info.json 的版本，确认目标语义版本更高。
2. 运行 prepare_release.py prepare。它在临时目录测试、构建 ZIP、生成 SHA-256 和 manifest.json，不修改插件源码。
3. 上传公开仓库前，明确确认将上传 ZIP、main.py、info.json、README.md（如有）和 manifest.json。
4. 使用已登录的 GitHub 浏览器会话上传，先提交 ZIP 与版本化源文件，最后提交 manifest.json。
5. 核验远端 manifest、下载包和 SHA-256 后，才运行 finalize 同步本地 main.py、info.json 与测试版本断言。

## 构建命令

~~~powershell
& 'E:\字字动画\_internal\python-3.12\python.exe' \
  'C:\Users\ASUS\.codex\skills\youzan-github-release\prepare_release.py' \
  prepare --plugin-dir 'E:\字字动画\_internal\plugins\video_plugins\video_plugin_youzan_aigc' \
  --version <version> --changelog <changelog>
~~~

## 约束

- 拒绝重复或降低版本。
- 更新说明为 ... 时，公开发布前要求真实更新说明。
- 不保存或上传 GitHub Token、密码或凭据。
- 上传或远端核验失败时，不执行 finalize。
