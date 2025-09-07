# Gigabyte/Aorus Fan Battery control center

### Highlights & Features
- **Lightweight & Efficient:** A minimal footprint application with extremely low CPU usage. When minimized and not in Auto-Fan mode, it consumes **zero CPU**, ensuring no impact on performance or battery life.
- **Advanced Fan Control:** Go beyond stock settings. Create multiple profiles with custom, smooth fan curves for both CPU and GPU, or set a fixed fan speed for specific tasks.
- **Intelligent Curve Editing:** The interactive curve canvas features **smart cascading adjustments**. Drag any point freely, and the rest of the curve will intelligently adjust to maintain a logical, monotonic profile, providing a seamless editing experience.
- **Battery Health Protection:** Extend your battery's lifespan by setting a custom charge limit (e.g., 80%). Ideal for users who are frequently plugged in.
- **Robust & Safe:** Includes a **crash-safe mechanism**. If the application crashes while in Auto-Fan mode, it will automatically set the fans to a safe, high speed (80%) to prevent overheating.
- **Clean & Modern UI:** A responsive, intuitive interface that provides all necessary information and controls without unnecessary clutter.

### Special Thanks
[The alfc project by s-h-a-d-o-w](https://github.com/s-h-a-d-o-w/alfc) for its support and assistance.

## Compatibility

| Model | System | 
|--------------|---------------|
| Aorus 15P XD | Windows 10/11 | 

### What is this project for? What problems does it solve?
GFBC is a lightweight yet powerful utility designed for Gigabyte laptops, offering granular control over fan behavior and battery charging. It serves as a high-performance alternative to manufacturer software, addressing key user needs:
- **Limited Fan Control:** Default fan curves are often a one-size-fits-all solution. This tool empowers you to create unlimited profiles with distinct fan curves, perfectly tailored for silent work, balanced daily use, or maximum cooling during intense gaming sessions.
- **Battery Longevity:** Constant charging to 100% degrades battery health over time. This application allows you to set a custom charge limit, significantly prolonging your battery's lifespan.
- **Bloatware Replacement:** It provides a streamlined, resource-friendly alternative to bulky pre-installed software, freeing up system resources while offering superior control.
- **Real-time System Monitoring:** The UI offers an at-a-glance view of critical system metrics, including CPU/GPU temperatures, fan RPMs, and detailed battery status.

### How to Use
1.  **Download & Run:** Download the latest release from the Releases page. No installation is required.
2.  **Administrator Privileges:** The application needs administrator rights to communicate with the hardware via WMI. It will automatically request elevation on startup if needed.
3.  **User Interface:**
    *   **Status Info Panel:** Displays real-time CPU/GPU temperatures, fan speeds (RPM), applied fan targets, and current battery policy/limit.
    *   **Fan Control Panel:**
        *   **BIOS Mode:** Returns all fan control to the system's hardware/BIOS.
        *   **Auto Mode:** Automatically adjusts fan speeds based on the active temperature curves.
        *   **Custom Mode:** Locks the fans to a fixed speed percentage set by the slider.
    *   **Battery Control Panel:**
        *   **BIOS Policy:** Uses the manufacturer's default charging behavior (typically charges to 100%).
        *   **Custom Policy:** Enforces the custom maximum charge threshold set by the slider (e.g., 60-100%).
    *   **Curve & Profile Panel:**
        *   **CPU/GPU Curve Buttons:** Toggle between viewing and editing the fan curve for each component.
        *   **Profile Buttons:** Manage your settings profiles.
            *   **Left-Click:** Activate a profile.
            *   **Right-Click:** Instantly save the current fan and battery settings to that profile.
            *   **Double-Click:** Open a dialog to rename or delete the profile.
        *   **"+" Button:** Create a new profile based on the currently active one.
        *   **Start on Boot:** If checked, the application will automatically start with Windows (via Task Scheduler).
        *   **Reset Curve:** Resets the currently selected fan curve (CPU or GPU) to its default points.
    *   **Curve Canvas:** The interactive graph for editing fan curves.
        *   **Drag Points:** Click and drag points to adjust the temperature-to-fan-speed mapping. The curve will intelligently adjust to prevent illogical configurations.
        *   **Double-Click:** Add a new point on the curve.
        *   **Right-Click a Point:** Delete a point.
    *   **Language Selector:** Change the application's display language on the fly.
4.  **Tray Icon:** The application minimizes to the system tray to run unobtrusively in the background.
    *   **Left-Click/Double-Click:** Show or hide the main window.
    *   **Right-Click:** Access a context menu to show/hide or quit the application.

### Scope of Application
This application is primarily designed for **Gigabyte laptops** that expose fan and battery controls through their WMI interface. While it may work on other brands or models with similar WMI implementations, compatibility is not guaranteed. It is built for **Windows operating systems**.

### Target Audience
-   **Gigabyte Laptop Owners:** Seeking a more powerful, efficient, and reliable alternative to the stock control software.
-   **Power Users & Gamers:** Who demand precise control over their system's thermal performance and acoustics.
-   **Users Concerned with Battery Health:** Who want to proactively manage and extend their laptop's battery lifespan.
-   **Minimalists:** Who prefer clean, focused, and resource-friendly utilities.

---

# 技嘉风扇与电池控制中心

### 亮点与特性
- **轻量高效:** 一个占用极小的应用程序，拥有极低的CPU使用率。当窗口最小化且不处于“自动温控”模式时，它会实现 **后台零CPU占用**，确保对系统性能和电池续航毫无影响。
- **高级风扇控制:** 超越原生设置。为CPU和GPU创建多个配置文件和自定义的平滑风扇曲线，或为特定任务设置固定的风扇转速。
- **智能曲线编辑:** 交互式曲线画布拥有 **“智能联动调整”** 特性。您可以自由拖动任何一个点，曲线上的其他点会自动智能调整，以始终维持逻辑正确的单调曲线，提供无与伦比的流畅编辑体验。
- **电池健康保护:** 通过设置自定义充电上限（例如 80%）来延长电池的生命周期，尤其适合经常连接电源使用的用户。
- **健壮与安全:** 内置 **崩溃安全机制**。如果程序在“自动温控”模式下意外崩溃，它会自动将风扇设定到一个安全的转速（80%），以防止硬件过热。
- **简洁的现代界面:** 一个响应迅速、直观的界面，提供所有必要的信息和控制选项，没有任何多余的元素。

### 特别感谢
[s-h-a-d-o-w 的 alfc 项目](https://github.com/s-h-a-d-o-w/alfc) 提供的支持与帮助。  

## 兼容性

| 型号 | 系统 | 
|--------------|---------------|
| Aorus 15P XD | Windows 10/11 | 

### 这个项目有什么用？解决什么问题？
GFBC 是一个为技嘉笔记本设计的轻量而强大的工具，提供对风扇行为和电池充电的精细化控制。它是一个高性能的官方软件替代品，旨在解决用户的核心痛点：
- **风扇控制受限:** 默认的风扇策略往往是“一刀切”的方案。本工具让您能创建不限数量的配置文件，每个文件都可以有独特的风扇曲线，完美适应静音办公、均衡日用或高强度游戏下的最大散热需求。
- **延长电池寿命:** 长期将电池充电到100%会随时间推移损害电池健康。本应用允许您设定一个自定义的充电上限，从而显著延长电池的生命周期。
- **替代臃肿软件:** 它提供了一个精简、资源友好的替代方案，取代了臃肿的预装软件，在提供更强控制力的同时，释放宝贵的系统资源。
- **实时系统监控:** UI界面让您能一目了然地看到关键系统指标，包括CPU/GPU温度、风扇RPM转速以及详细的电池策略状态。

### 如何使用
1.  **下载与运行:** 从 Releases 页面 下载最新版本的程序。无需安装，直接运行。
2.  **管理员权限:** 本程序需要管理员权限才能通过WMI与硬件通信。如果需要，它会在启动时自动请求提权。
3.  **用户界面:**
    *   **状态信息面板:** 实时显示CPU/GPU温度、风扇转速(RPM)、当前风扇目标以及电池策略/上限。
    *   **风扇控制面板:**
        *   **BIOS 模式:** 将所有风扇控制权交还给系统硬件/BIOS。
        *   **自动 模式:** 根据当前激活的温度曲线自动调节风扇转速。
        *   **自定义 模式:** 将风扇锁定在滑块设定的固定转速百分比。
    *   **电池控制面板:**
        *   **BIOS 策略:** 使用制造商默认的充电行为（通常会充到100%）。
        *   **自定义 策略:** 强制执行由滑块设定的自定义充电上限（例如 60-100%）。
    *   **曲线与配置文件面板:**
        *   **CPU/GPU 曲线按钮:** 切换查看和编辑对应组件的风扇曲线。
        *   **配置文件按钮:** 管理您的配置方案。
            *   **左键单击:** 激活一个配置文件。
            *   **右键单击:** 将当前的各项设置（风扇、电池）立即保存到该配置文件。
            *   **双击:** 打开对话框以重命名或删除该配置文件。
        *   **“+” 按钮:** 基于当前配置创建一个新的配置文件。
        *   **开机启动:** 勾选后，程序将通过“任务计划程序”实现开机自启。
        *   **重置曲线:** 将当前选中的曲线（CPU或GPU）恢复为默认设定。
    *   **曲线画布:** 用于编辑风扇曲线的交互式图表。
        *   **拖动点:** 单击并拖动控制点以调整温度与风扇转速的对应关系。曲线会自动联动调整以防止出现不合逻辑的设定。
        *   **双击:** 在画布的空白处双击以添加一个新的控制点。
        *   **右键单击一个点:** 删除该控制点。
    *   **语言选择器:** 在标题栏可以随时切换程序的显示语言。
4.  **托盘图标:** 程序会最小化到系统托盘，在后台安静运行。
    *   **左键单击/双击:** 显示或隐藏主窗口。
    *   **右键单击:** 访问上下文菜单，以显示/隐藏窗口或退出程序。

### 适用范围
此应用程序主要为支持通过WMI接口进行风扇和电池控制的**技嘉笔记本电脑**设计。尽管它可能也适用于具有相似WMI实现的其他品牌或型号，但这并非官方支持或保证。本程序仅在**Windows操作系统**上运行。

### 适用人群
-   **技嘉笔记本用户:** 正在寻找比官方控制软件更强大、高效、可靠的替代方案的用户。
-   **高级用户和游戏玩家:** 渴望对系统的散热性能和噪音水平进行精确控制的用户。
-   **关注电池健康的用户:** 希望主动管理并延长其笔记本电池寿命的用户。
-   **极简主义者:** 偏爱功能专注、资源友好型工具的用户。

---

### Advanced Setup: Using Without Gigabyte Control Center

This section is for advanced users who wish to completely uninstall the official Gigabyte Control Center (GCC) but still use this application. The official software is responsible for registering the necessary WMI provider (`acpimof.dll`) with Windows. Without it, this tool cannot communicate with the hardware. The following steps manually register this provider.

**DISCLAIMER: Modifying the Windows Registry is risky and can cause system instability if done incorrectly. It is highly recommended to back up your registry before proceeding.**

1.  **Obtain WMI Provider:** Find the Gigabyte Control Center installer package and extract its contents. Locate the `acpimof.dll` file within the extracted files.
2.  **Place the DLL:** Copy the `acpimof.dll` file to the `C:\Windows\SysWOW64` directory.
3.  **Open Registry Editor:** Press `Win + R`, type `regedit`, and press Enter.
4.  **Navigate to the Key:** In the Registry Editor, navigate to the following path:
    `Computer\HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\WmiAcpi`
5.  **Create String Value:** In the right-hand pane, right-click on an empty space, select `New` -> `String Value`.
6.  **Name the Value:** Name the new value exactly `MofImagePath`.
7.  **Set the Value Data:** Double-click `MofImagePath` and set its value data to the full path of the DLL: `C:\Windows\SysWOW64\acpimof.dll`.
8.  **Reboot:** Restart your computer for the changes to take effect.
9.  **Verify:** After rebooting, run GFBC. If it starts without any WMI initialization errors, the configuration was successful.

---

### 高级设置：在无官方软件环境下使用

本节适用于希望**完全卸载**技嘉官方控制中心（GCC）但仍要使用本程序的高级用户。官方软件负责向Windows系统注册必要的WMI硬件接口库（`acpimof.dll`）。如果缺少这一步，本工具将无法与硬件通信。以下步骤将手动完成此注册过程。

**免责声明：修改Windows注册表存在风险，操作不当可能导致系统不稳定。强烈建议在继续操作前备份您的注册表。**

1.  **获取WMI接口库：** 找到技嘉控制中心的安装包并解压其内容。在解压出的文件中找到 `acpimof.dll`。
2.  **放置DLL文件：** 将 `acpimof.dll` 文件复制到 `C:\Windows\SysWOW64` 目录下。
3.  **打开注册表编辑器：** 按下 `Win + R` 键，输入 `regedit`，然后按回车。
4.  **导航到指定路径：** 在注册表编辑器中，定位到以下路径：
    `计算机\HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\WmiAcpi`
5.  **创建字符串值：** 在右侧窗格的空白处单击右键，选择 `新建` -> `字符串值`。
6.  **命名键值：** 将新创建的值精确命名为 `MofImagePath`。
7.  **设置键值数据：** 双击 `MofImagePath`，并将其“数值数据”设置为DLL文件的完整路径：`C:\Windows\SysWOW64\acpimof.dll`。
8.  **重启电脑：** 重启计算机以使更改生效。
9.  **验证：** 重启后，运行 GFBC。如果程序启动时没有出现任何WMI初始化错误，则代表配置成功。