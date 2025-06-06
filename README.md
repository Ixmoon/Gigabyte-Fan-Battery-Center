# FanBatteryControl (风扇与电池控制)

## English / 英语

### What is this project for? What problems does it solve?
FanBatteryControl is a lightweight application designed to provide advanced fan and battery control capabilities for Gigabyte laptops, particularly those where the default manufacturer software might be cumbersome or resource-intensive. It aims to address common issues faced by users, such as:
- **Limited Fan Control:** Default fan curves may not be optimal for all use cases (e.g., silent operation during light tasks, maximum cooling during gaming). This tool allows users to define custom fan curves based on CPU and GPU temperatures.
- **Battery Longevity:** Many laptops suffer from reduced battery lifespan due to constant charging to 100%. This application enables users to set a custom charge limit (e.g., 80%), prolonging battery health, especially for devices frequently used while plugged in.
- **Bloatware Replacement:** It offers a streamlined alternative to pre-installed manufacturer software, which often consumes significant system resources and may lack granular control options.
- **System Monitoring:** Provides real-time display of CPU/GPU temperatures, fan RPMs, and battery status directly within the GUI.

### How to Use
1.  **Download & Run:** Download the latest release executable from the [Releases page](link_to_releases_page_here).
2.  **Administrator Privileges:** The application requires administrator privileges to interact with WMI (Windows Management Instrumentation) for fan and battery control. It will automatically prompt for elevation if not run as administrator.
3.  **User Interface:**
    *   **Status Info Panel:** Displays current CPU/GPU temperatures, fan speeds (RPM), and battery charging status.
    *   **Fan Control Panel:**
        *   **Auto Mode:** The application will automatically adjust fan speeds based on defined temperature curves.
        *   **Manual Mode:** Allows setting a fixed fan speed percentage.
    *   **Battery Control Panel:**
        *   **Standard Policy:** Uses the manufacturer's default battery charging behavior.
        *   **Custom Policy:** Enables setting a custom maximum charge threshold (e.g., 60-100%).
    *   **Curve Control Panel:**
        *   **CPU/GPU Curve:** Select to view and edit the fan curve for the respective component.
        *   **Profiles:** Create and manage multiple configuration profiles (e.g., "Silent," "Gaming," "Balanced") with different fan curves and battery settings.
            *   **Left-Click Profile Button:** Activate a profile.
            *   **Right-Click Profile Button:** Save current settings to that profile.
            *   **Double-Click Profile Button:** Rename a profile.
        *   **Start on Boot:** Enable/disable automatic startup with Windows (uses Task Scheduler).
        *   **Reset Curve:** Reset the currently selected fan curve to its default values.
    *   **Curve Canvas:** An interactive graph where you can:
        *   **Drag Points:** Adjust existing temperature-to-fan-speed points.
        *   **Double-Click:** Add new points to the curve.
        *   **Right-Click Point:** Delete a point.
    *   **Settings Panel:** Change application language.
4.  **Tray Icon:** The application runs in the system tray when minimized or closed (by default).
    *   **Left-Click/Double-Click:** Show/hide the main window.
    *   **Right-Click:** Access a menu to show/hide or quit the application.

### Scope of Application
This application is primarily designed for **Gigabyte laptops** that support WMI-based fan and battery control. It leverages specific Gigabyte WMI methods, so compatibility with other brands or older/newer Gigabyte models is not guaranteed but may work if WMI interfaces are similar. It runs on **Windows operating systems**.

### Target Audience
-   **Gigabyte Laptop Owners:** Especially those who find the official control software lacking or too resource-intensive.
-   **Power Users & Gamers:** Who want fine-tuned control over their laptop's cooling performance for optimal thermal management and noise levels.
-   **Users Concerned with Battery Health:** Who wish to extend their laptop's battery lifespan by limiting the maximum charge percentage.
-   **Minimalists:** Who prefer lightweight, focused tools over bundled software.

---

## 简体中文 / Chinese (Simplified)

### 这个项目有什么用？解决什么问题？
FanBatteryControl 是一个轻量级应用程序，旨在为技嘉笔记本电脑提供高级风扇和电池控制功能，特别是那些默认制造商软件可能笨重或占用大量资源的情况。它旨在解决用户面临的常见问题，例如：
-   **风扇控制受限：** 默认风扇曲线可能不适用于所有使用场景（例如，轻度任务时的静音运行，游戏时的最大散热）。此工具允许用户根据 CPU 和 GPU 温度定义自定义风扇曲线。
-   **延长电池寿命：** 许多笔记本电脑由于持续充电到 100% 而导致电池寿命缩短。此应用程序使用户能够设置自定义充电限制（例如 80%），从而延长电池寿命，特别是对于经常插电使用的设备。
-   **替代臃肿软件：** 它提供了一个精简的替代方案，取代预装的制造商软件，这些软件通常会占用大量系统资源，并且可能缺乏精细的控制选项。
-   **系统监控：** 直接在图形用户界面中实时显示 CPU/GPU 温度、风扇转速 (RPM) 和电池状态。

### 如何使用
1.  **下载与运行：** 从 [Releases 页面](link_to_releases_page_here) 下载最新版本的可执行文件。
2.  **管理员权限：** 应用程序需要管理员权限才能与 WMI (Windows Management Instrumentation) 交互以进行风扇和电池控制。如果未以管理员身份运行，它将自动提示提升权限。
3.  **用户界面：**
    *   **状态信息面板：** 显示当前的 CPU/GPU 温度、风扇转速和电池充电状态。
    *   **风扇控制面板：**
        *   **自动模式：** 应用程序将根据定义的温度曲线自动调整风扇速度。
        *   **手动模式：** 允许设置固定的风扇速度百分比。
    *   **电池控制面板：**
        *   **标准策略：** 使用制造商的默认电池充电行为。
        *   **自定义策略：** 启用设置自定义最大充电阈值（例如 60-100%）。
    *   **曲线控制面板：**
        *   **CPU/GPU 曲线：** 选择以查看和编辑相应组件的风扇曲线。
        *   **配置文件：** 创建和管理多个配置配置文件（例如“静音”、“游戏”、“平衡”），其中包含不同的风扇曲线和电池设置。
            *   **左键单击配置文件按钮：** 激活配置文件。
            *   **右键单击配置文件按钮：** 将当前设置保存到该配置文件。
            *   **双击配置文件按钮：** 重命名配置文件。
        *   **开机启动：** 启用/禁用随 Windows 自动启动（使用任务计划程序）。
        *   **重置曲线：** 将当前选定的风扇曲线重置为默认值。
    *   **曲线画布：** 一个交互式图形，您可以在其中：
        *   **拖动点：** 调整现有的温度-风扇速度点。
        *   **双击：** 向曲线添加新点。
        *   **右键单击点：** 删除一个点。
    *   **设置面板：** 更改应用程序语言。
4.  **托盘图标：** 应用程序在最小化或关闭时（默认情况下）在系统托盘中运行。
    *   **左键单击/双击：** 显示/隐藏主窗口。
    *   **右键单击：** 访问菜单以显示/隐藏或退出应用程序。

### 适用范围
此应用程序主要为**技嘉笔记本电脑**设计，这些笔记本电脑支持基于 WMI 的风扇和电池控制。它利用了特定的技嘉 WMI 方法，因此不保证与其他品牌或旧/新技嘉型号的兼容性，但如果 WMI 接口相似，则可能有效。它在 **Windows 操作系统**上运行。

### 适用人群
-   **技嘉笔记本电脑用户：** 特别是那些认为官方控制软件功能不足或占用资源过多的用户。
-   **高级用户和游戏玩家：** 希望对笔记本电脑的散热性能进行精细控制，以实现最佳散热管理和噪音水平。
-   **关注电池健康的用户：** 希望通过限制最大充电百分比来延长笔记本电脑电池寿命的用户。
-   **极简主义者：** 喜欢轻量级、专注的工具而不是捆绑软件的用户。