# 第三方组件

本项目自身的源代码采用 MIT License，详见仓库根目录的 `LICENSE`。以下许可适用于项目使用或分发的第三方组件，不因本项目采用 MIT License 而改变。

此工具采用 Python、PySide6 / Qt 和 PyInstaller 构建。

- Python：Python Software Foundation License，https://docs.python.org/3/license.html
- PySide6 / Shiboken6：LGPLv3 / GPLv3 / 商业许可证，https://doc.qt.io/qtforpython-6/licenses.html
- Qt：使用动态链接的 Qt Core、Gui、Widgets 及其运行时插件，依相应 LGPLv3 条款，https://www.qt.io/licensing/open-source-lgpl-obligations
- PyInstaller：GPLv2-or-later，包含允许分发生成程序的引导程序例外，https://pyinstaller.org/en/stable/license.html

源码和构建脚本随工程提供，可用兼容的修改版 Qt / PySide6 重建应用。用于调试此类修改的逆向工程不受本工具额外限制。运行时未将 Qt 静态链接入程序。

具体版本见 requirements.txt。分发目录的 licenses 文件夹包含构建环境中各组件提供的许可证文本。PySide6 源码及对应版本可从 https://code.qt.io/pyside/pyside-setup.git 获取；Qt 源码见 https://code.qt.io/qt/qtbase.git 。
