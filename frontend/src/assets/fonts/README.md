# 本地界面字体

`noto-sans-sc-ui.woff2` 是 Noto Sans SC 的项目子集，真实可变字重为 **400–700**，大小约 **1.81 MiB**（1,894,084 字节），包含 7,741 个 Unicode 字符。字体随前端本地提供，无需访问外部字体服务。

## 来源与许可

- 源文件：本机 `C:/Windows/Fonts/NotoSansSC-VF.ttf`，字体元数据版本为 `2.04;241114210130;non-release`。
- 上游项目：[Noto CJK](https://github.com/notofonts/noto-cjk)。本机安装包的来源未另作验证。
- 版权：© 2014–2021 Adobe，保留字体名为 `Source`。项目子集保留源字体版权及许可元数据。
- 许可：SIL Open Font License 1.1；完整官方原文与版权见 [OFL.txt](./OFL.txt)。许可原文于 2026-09-09 从[官方仓库](https://github.com/notofonts/noto-cjk/blob/main/Sans/LICENSE)取得。

## 覆盖与更新

子集覆盖源字体支持的 GB2312 字符、ASCII、常用通用标点、货币符号、中日韩标点、全角字符，以及 `frontend/src/`、`backend/app/` 当前源码中的文字。生僻字和其他语言仍由 CSS 中的系统字体补齐。移除字体 hinting，保留布局及可变字重信息。

新增界面文案后，在仓库根目录运行：

```powershell
python frontend/src/assets/fonts/build_subset.py --source C:/Windows/Fonts/NotoSansSC-VF.ttf
```

生成工具需要 Python 的 `fontTools` 和 `brotli`，不属于应用运行时依赖。脚本同时将许可证复制到 `frontend/public/fonts/OFL.txt`，确保构建产物附带许可。请保留源字体及许可，确认输出大小和浏览器显示，再提交更新后的 WOFF2。若更换原字体，重新核对版权、许可证及字重范围。
